"""Quest Touch controller navigation and picking via the OpenXR action system."""
import time
from math import radians

import numpy as np

from glyphviz_core.node import NODE_TYPE_LINK, NON_VISUAL_TYPES
from glyphviz_core.scene import node_world_matrix
from glyphviz_gl.geometry import GeoRenderer

from .render import draw_controller_marker
from .transforms import rig_inverse_matrix


class ControllerNav:
    """Quest Touch controller navigation via the OpenXR action system:
    thumbstick fly (left stick = move relative to real head-look direction,
    right stick = yaw turn + vertical) and grip-squeeze grab-drag (translate
    only, single-hand), plus trigger-based ray picking against scene nodes.
    Maintains nav_position/nav_yaw, the accumulated virtual offset consumed
    by rig_inverse(); see transforms.rig_inverse_matrix's docstring for why
    a separate "rig" transform is needed at all instead of just moving the
    diorama's fixed placement."""

    TOUCH_CONTROLLER_PROFILE = "/interaction_profiles/oculus/touch_controller"
    MOVE_SPEED = 3.0       # m/s at full stick deflection
    TURN_SPEED = radians(90)  # rad/s at full stick deflection
    GRAB_ON_THRESHOLD = 0.6
    GRAB_OFF_THRESHOLD = 0.4
    TRIGGER_THRESHOLD = 0.5

    def __init__(self, ctx):
        import xr
        self._xr = xr
        self.session = ctx.session
        self.base_space = ctx.space
        instance = ctx.instance

        self.action_set = xr.create_action_set(
            instance, xr.ActionSetCreateInfo(
                action_set_name="navigation", localized_action_set_name="Navigation"))
        # ContextObject.frame_loop() does its own xr.attach_session_action_sets()
        # call (lazily, on first iteration) covering everything in
        # ctx.action_sets — OpenXR only allows one attach call per session
        # ever, so we register here instead of attaching separately ourselves.
        ctx.action_sets.append(self.action_set)
        self.hand_paths = {
            "left": xr.string_to_path(instance, "/user/hand/left"),
            "right": xr.string_to_path(instance, "/user/hand/right"),
        }
        sub_paths = list(self.hand_paths.values())

        self.grip_pose_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="grip_pose", localized_action_name="Grip Pose",
            action_type=xr.ActionType.POSE_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))
        self.aim_pose_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="aim_pose", localized_action_name="Aim Pose",
            action_type=xr.ActionType.POSE_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))
        self.thumbstick_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="thumbstick", localized_action_name="Thumbstick",
            action_type=xr.ActionType.VECTOR2F_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))
        self.squeeze_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="squeeze", localized_action_name="Squeeze",
            action_type=xr.ActionType.FLOAT_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))
        self.trigger_action = xr.create_action(self.action_set, xr.ActionCreateInfo(
            action_name="trigger", localized_action_name="Trigger",
            action_type=xr.ActionType.FLOAT_INPUT,
            count_subaction_paths=len(sub_paths), subaction_paths=sub_paths))

        bindings = []
        for hand in self.hand_paths:
            bindings.append(xr.ActionSuggestedBinding(
                action=self.grip_pose_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/grip/pose")))
            bindings.append(xr.ActionSuggestedBinding(
                action=self.aim_pose_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/aim/pose")))
            bindings.append(xr.ActionSuggestedBinding(
                action=self.thumbstick_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/thumbstick")))
            bindings.append(xr.ActionSuggestedBinding(
                action=self.squeeze_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/squeeze/value")))
            bindings.append(xr.ActionSuggestedBinding(
                action=self.trigger_action,
                binding=xr.string_to_path(instance, f"/user/hand/{hand}/input/trigger/value")))
        xr.suggest_interaction_profile_bindings(instance, xr.InteractionProfileSuggestedBinding(
            interaction_profile=xr.string_to_path(instance, self.TOUCH_CONTROLLER_PROFILE),
            count_suggested_bindings=len(bindings), suggested_bindings=bindings))

        # Action spaces deferred to first update() call: some runtimes
        # require the owning action set to actually be attached first, which
        # (per the comment above) only happens once ctx.frame_loop() starts.
        self.grip_spaces = None
        self.aim_spaces = None

        self.nav_position = np.zeros(3)
        self.nav_yaw = 0.0
        self._grab_hand = None
        self._grab_anchor_grip_pos = None
        self._grab_anchor_nav_position = None
        self._last_time = time.perf_counter()
        self.controller_draws = []  # [(position, forward_dir, color), ...] for this frame
        self.selected_node = None
        self._prev_trigger = {"left": 0.0, "right": 0.0}

    def _thumbstick(self, hand):
        xr = self._xr
        state = xr.get_action_state_vector2f(self.session, xr.ActionStateGetInfo(
            action=self.thumbstick_action, subaction_path=self.hand_paths[hand]))
        return state.current_state.x, state.current_state.y

    def _squeeze(self, hand):
        xr = self._xr
        state = xr.get_action_state_float(self.session, xr.ActionStateGetInfo(
            action=self.squeeze_action, subaction_path=self.hand_paths[hand]))
        return state.current_state

    def _trigger(self, hand):
        xr = self._xr
        state = xr.get_action_state_float(self.session, xr.ActionStateGetInfo(
            action=self.trigger_action, subaction_path=self.hand_paths[hand]))
        return state.current_state

    def _locate(self, space, display_time):
        xr = self._xr
        location = xr.locate_space(space, self.base_space, display_time)
        flags = location.location_flags
        if (flags & xr.SPACE_LOCATION_POSITION_VALID_BIT == 0
                or flags & xr.SPACE_LOCATION_ORIENTATION_VALID_BIT == 0):
            return None
        return location.pose

    def _grip_pose(self, hand, display_time):
        return self._locate(self.grip_spaces[hand], display_time)

    def _aim_pose(self, hand, display_time):
        return self._locate(self.aim_spaces[hand], display_time)

    def update(self, head_orientation, display_time, scene, diorama_transform, scale):
        """Call once per real frame (not per eye). head_orientation is any
        eye's pose.orientation for that frame — both eyes share the same
        orientation (confirmed on-headset 2026-06-18), so either works for
        deriving the head-relative forward/right directions used by the
        left thumbstick. scene/diorama_transform/scale are needed for
        trigger-based ray picking against the actual node positions."""
        xr = self._xr
        if self.grip_spaces is None:
            self.grip_spaces = {
                hand: xr.create_action_space(self.session, xr.ActionSpaceCreateInfo(
                    action=self.grip_pose_action, subaction_path=path))
                for hand, path in self.hand_paths.items()
            }
            self.aim_spaces = {
                hand: xr.create_action_space(self.session, xr.ActionSpaceCreateInfo(
                    action=self.aim_pose_action, subaction_path=path))
                for hand, path in self.hand_paths.items()
            }
        xr.sync_actions(self.session, xr.ActionsSyncInfo(
            count_active_action_sets=1,
            active_action_sets=[xr.ActiveActionSet(action_set=self.action_set,
                                                    subaction_path=xr.NULL_PATH)]))

        now = time.perf_counter()
        dt = now - self._last_time
        self._last_time = now

        from xr.utils import rotation_from_quaternionf
        r_inv = np.asarray(rotation_from_quaternionf(head_orientation), dtype=np.float64)
        r_fwd = r_inv.T
        forward = r_fwd @ np.array([0.0, 0.0, -1.0])
        right = r_fwd @ np.array([1.0, 0.0, 0.0])
        forward[1] = 0.0
        right[1] = 0.0
        forward = forward / max(np.linalg.norm(forward), 1e-6)
        right = right / max(np.linalg.norm(right), 1e-6)

        grip_poses = {}
        for hand in self.hand_paths:
            pose = self._grip_pose(hand, display_time)
            if pose is not None:
                grip_poses[hand] = pose

        # Grab-drag takes over from whichever hand is squeezing past the
        # threshold; thumbstick fly is suppressed for that hand while held
        # rather than fighting it for control of nav_position.
        for hand in self.hand_paths:
            squeeze = self._squeeze(hand)
            pose = grip_poses.get(hand)
            if pose is None:
                continue
            grip_pos = np.array([pose.position.x, pose.position.y, pose.position.z])
            if self._grab_hand is None and squeeze > self.GRAB_ON_THRESHOLD:
                self._grab_hand = hand
                self._grab_anchor_grip_pos = grip_pos
                self._grab_anchor_nav_position = self.nav_position.copy()
            elif self._grab_hand == hand and squeeze < self.GRAB_OFF_THRESHOLD:
                self._grab_hand = None
            elif self._grab_hand == hand:
                delta = grip_pos - self._grab_anchor_grip_pos
                self.nav_position = self._grab_anchor_nav_position - delta

        if self._grab_hand is None:
            lx, ly = self._thumbstick("left")
            rx, ry = self._thumbstick("right")
            self.nav_position = self.nav_position + (right * lx + forward * ly) * self.MOVE_SPEED * dt
            self.nav_position[1] += ry * self.MOVE_SPEED * dt
            self.nav_yaw += -rx * self.TURN_SPEED * dt

        self.controller_draws = []
        aim_poses = {}
        for hand, pose in grip_poses.items():
            pos = np.array([pose.position.x, pose.position.y, pose.position.z])
            # Ray direction comes from the *aim* pose, not grip: grip's local
            # -Z axis is oriented for holding the controller, not for where
            # it visually points — using it for the ray made the line
            # segment point up instead of forward (confirmed on-headset
            # 2026-06-18). Aim pose is OpenXR's purpose-built pointing pose.
            aim_pose = self._aim_pose(hand, display_time)
            aim_poses[hand] = aim_pose
            ray_pose = aim_pose if aim_pose is not None else pose
            r_inv_hand = np.asarray(rotation_from_quaternionf(ray_pose.orientation), dtype=np.float64)
            hand_forward = r_inv_hand.T @ np.array([0.0, 0.0, -1.0])
            color = (0.2, 0.8, 1.0) if hand == "left" else (1.0, 0.6, 0.2)
            self.controller_draws.append((pos, hand_forward, color))

        self._pick(scene, diorama_transform, scale, aim_poses)

    def _pick(self, scene, diorama_transform, scale, aim_poses):
        """Trigger rising-edge on either hand casts that hand's aim ray
        against a bounding-sphere approximation of every visible node
        (radius from the mean column norm of its world matrix's 3x3 part),
        in the same real/tracked LOCAL space the controller poses live in —
        node centers get mapped there via diorama_transform then
        rig_inverse(), the inverse of how render.draw_scene/the rig transform
        place them for rendering. Closest hit along the ray wins."""
        fired_hand = None
        for hand in self.hand_paths:
            trigger = self._trigger(hand)
            prev = self._prev_trigger[hand]
            self._prev_trigger[hand] = trigger
            if prev < self.TRIGGER_THRESHOLD <= trigger:
                fired_hand = hand
        if fired_hand is None:
            return
        pose = aim_poses.get(fired_hand)
        if pose is None:
            return

        from xr.utils import rotation_from_quaternionf
        ray_origin = np.array([pose.position.x, pose.position.y, pose.position.z])
        r_inv = np.asarray(rotation_from_quaternionf(pose.orientation), dtype=np.float64)
        ray_dir = r_inv.T @ np.array([0.0, 0.0, -1.0])
        ray_dir = ray_dir / max(np.linalg.norm(ray_dir), 1e-9)

        rig_inv = self.rig_inverse()
        best_node, best_dist = None, None
        for node in scene.nodes:
            if node.type in NON_VISUAL_TYPES or node.type == NODE_TYPE_LINK:
                continue
            M = node_world_matrix(node, scene)
            center_diorama = diorama_transform @ M[:, 3]
            center_real = (rig_inv @ center_diorama)[:3]
            radius = (sum(np.linalg.norm(M[:3, i]) for i in range(3)) / 3.0) * scale

            oc = center_real - ray_origin
            proj_len = np.dot(oc, ray_dir)
            if proj_len < 0:
                continue
            closest = ray_origin + ray_dir * proj_len
            if np.linalg.norm(center_real - closest) <= radius:
                if best_dist is None or proj_len < best_dist:
                    best_dist, best_node = proj_len, node

        self.selected_node = best_node

    def rig_inverse(self) -> np.ndarray:
        return rig_inverse_matrix(self.nav_position, self.nav_yaw)

    def draw_controllers(self, geo: GeoRenderer):
        for position, forward_dir, color in self.controller_draws:
            draw_controller_marker(geo, position, forward_dir, color)
