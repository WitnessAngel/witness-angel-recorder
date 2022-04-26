import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.append(str(Path(__file__).parent.joinpath("src")))  # register SRC/ folder just in case

    from wacomponents.launcher import launch_app_or_resurrect_service_with_crash_handler
    launch_app_or_resurrect_service_with_crash_handler(
        app_module="wanvr.wanvr_gui", service_module="wanvr.wanvr_service",
        main_file=__file__, sys_argv=sys.argv)
