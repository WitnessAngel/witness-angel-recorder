import os
from pathlib import Path

if __name__ == "__main__":
    # We play it safe and ensure service is started only once
    os.environ["WA_SERVICE_SCRIPT"] = str(Path(__file__).resolve().parent.joinpath("resurrect_service.py"))
    from waguilib.launcher import launch_app_or_service_with_crash_handler
    launch_app_or_service_with_crash_handler("wanvr.app", client_type="APPLICATION")
