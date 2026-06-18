"""OpenXR session/swapchain plumbing: the hidden-window GL context provider
GeoRenderer's fixed-function GL needs, and the per-eye view/swapchain loop."""


def make_compat_gl_context_provider(glfw):
    """Hidden GLFW window/context with NO core-profile hint: GeoRenderer
    relies on fixed-function GL (display lists, glBegin/End, GLU quadrics),
    which requires a compatibility-profile context. Takes the `glfw` module
    as a parameter rather than importing it at module level, so this module
    stays importable without the optional XR dependencies installed."""
    from xr.utils import GraphicsContextProvider

    class _CompatGLContextProvider(GraphicsContextProvider):
        def __init__(self):
            if not glfw.init():
                raise RuntimeError("Failed to initialize GLFW")
            glfw.window_hint(glfw.VISIBLE, False)
            glfw.window_hint(glfw.DOUBLEBUFFER, False)
            self._window = glfw.create_window(1, 1, "", None, None)
            if self._window is None:
                glfw.terminate()
                raise RuntimeError("Failed to create hidden GLFW window")
            glfw.make_context_current(self._window)
            glfw.swap_interval(0)

        def make_current(self) -> None:
            glfw.make_context_current(self._window)

        def done_current(self) -> None:
            glfw.make_context_current(None)

        def destroy(self) -> None:
            if self._window is not None:
                glfw.destroy_window(self._window)
                glfw.terminate()
                self._window = None

    return _CompatGLContextProvider()


def view_loop_output_swapped(ctx, frame_state, swap_eyes: bool):
    """Drop-in replacement for xr.utils.gl.ContextObject.view_loop that
    routes each view's (pose, fov, rendered content) — kept self-consistent
    as a triple — to a physical swapchain slot. `swap_eyes` controls whether
    that slot is the view's own (normal) or the other one.

    A previous session observed the physical eyes seeing each other's image
    and added the swap as a fix, on the theory it was a swapchain-routing
    quirk independent of the view-matrix bugs fixed in that same session.
    Re-confirmed 2026-06-18 still necessary: disabling it reproduces the
    original symptom and makes overlap worse."""
    import xr
    from ctypes import byref, cast, POINTER

    if not frame_state.should_render:
        return
    layer = xr.CompositionLayerProjection(space=ctx.space)
    view_state, views = xr.locate_views(
        session=ctx.session,
        view_locate_info=xr.ViewLocateInfo(
            view_configuration_type=ctx.view_configuration_type,
            display_time=frame_state.predicted_display_time,
            space=ctx.space,
        ),
    )
    num_views = len(views)
    projection_layer_views = tuple(xr.CompositionLayerProjectionView() for _ in range(num_views))

    vsf = view_state.view_state_flags
    if (vsf & xr.VIEW_STATE_POSITION_VALID_BIT == 0
            or vsf & xr.VIEW_STATE_ORIENTATION_VALID_BIT == 0):
        return
    for view_index, view in enumerate(views):
        output_index = (num_views - 1 - view_index) if swap_eyes else view_index
        view_swapchain = ctx.swapchains[output_index]
        swapchain_image_index = xr.acquire_swapchain_image(
            swapchain=view_swapchain.handle,
            acquire_info=xr.SwapchainImageAcquireInfo(),
        )
        xr.wait_swapchain_image(
            swapchain=view_swapchain.handle,
            wait_info=xr.SwapchainImageWaitInfo(timeout=xr.INFINITE_DURATION),
        )
        layer_view = projection_layer_views[output_index]
        layer_view.pose = view.pose
        layer_view.fov = view.fov
        layer_view.sub_image.swapchain = view_swapchain.handle
        layer_view.sub_image.image_rect.offset[:] = [0, 0]
        layer_view.sub_image.image_rect.extent[:] = [
            view_swapchain.width, view_swapchain.height, ]
        swapchain_image_ptr = ctx.swapchain_image_ptr_buffers[output_index][swapchain_image_index]
        swapchain_image = cast(swapchain_image_ptr, POINTER(xr.SwapchainImageOpenGLKHR)).contents
        color_texture = swapchain_image.image
        ctx.graphics.begin_frame(layer_view, color_texture)

        yield view

        ctx.graphics.end_frame()
        xr.release_swapchain_image(
            swapchain=view_swapchain.handle,
            release_info=xr.SwapchainImageReleaseInfo(),
        )
    layer.views = projection_layer_views
    ctx.render_layers.append(byref(layer))
