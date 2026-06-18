"""
OpenXR diagnostic probe — no rendering, no GlyphViz scene. Answers one
question: does this PC + headset + runtime actually give Python a working
OpenXR instance?

For the Quest 3 path: install the Meta Quest Link app, connect via USB-C
Link cable or Air Link, and make sure "Link" is active on the headset
(not just the Quest's own Home) before running this — that's what
registers the OpenXR runtime this probe looks for.

Usage:
    C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe tools\\openxr_probe.py
"""
import sys


def main() -> int:
    try:
        import xr
    except ImportError:
        print(
            "pyopenxr is not installed. Run:\n"
            "  C:\\Users\\jsale\\anaconda3\\envs\\glyphviz\\python.exe -m pip install -r requirements-xr.txt"
        )
        return 1

    print(f"pyopenxr import OK (xr module at {xr.__file__})")

    try:
        instance = xr.create_instance(
            create_info=xr.InstanceCreateInfo(
                application_info=xr.ApplicationInfo(
                    application_name="GlyphViz OpenXR Probe",
                    application_version=1,
                    engine_name="GlyphViz",
                    engine_version=1,
                    api_version=xr.XR_CURRENT_API_VERSION,
                ),
            ),
        )
    except Exception as e:
        print(f"FAILED to create an OpenXR instance: {type(e).__name__}: {e}")
        print(
            "This usually means no OpenXR runtime is registered on this PC right "
            "now - for Quest 3, make sure the Meta Quest Link app is running and "
            "'Link' (not just Home) is active on the headset, then try again."
        )
        return 1

    try:
        props = xr.get_instance_properties(instance)
        print(f"Runtime name:    {props.runtime_name.decode('utf-8', 'replace')}")
        print(f"Runtime version: {xr.Version(props.runtime_version)}")

        try:
            system_id = xr.get_system(
                instance,
                xr.SystemGetInfo(form_factor=xr.FormFactor.HEAD_MOUNTED_DISPLAY),
            )
        except Exception as e:
            print(f"No HMD system available: {type(e).__name__}: {e}")
            print(
                "The runtime loaded, but no headset is currently reachable through "
                "it - confirm the Quest 3 shows 'Link' as active, not just connected."
            )
            return 1

        sys_props = xr.get_system_properties(instance, system_id)
        print(f"System name:     {sys_props.system_name.decode('utf-8', 'replace')}")

        view_configs = xr.enumerate_view_configurations(instance, system_id)
        print(f"View configurations available: {list(view_configs)}")

        print("\nSUCCESS - OpenXR instance, system, and view configuration all resolved.")
        return 0
    finally:
        xr.destroy_instance(instance)


if __name__ == "__main__":
    sys.exit(main())
