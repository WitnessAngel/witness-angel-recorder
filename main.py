import sys
from pathlib import Path

if __name__ == "__main__":
    from wacomponents.launcher import launch_app_or_resurrect_service_with_crash_handler
    launch_app_or_resurrect_service_with_crash_handler(
        app_module="warecorder.warecorder_gui",
        service_module="warecorder.warecorder_service",
        main_file=__file__, sys_argv=sys.argv)
