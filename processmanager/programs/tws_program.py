# tws_program.py
from ..core.BaseProgram import BaseProgram
from ..core.utils import check_ib_valid_time, list_and_kill_process
from datetime import datetime
import os
import signal
import subprocess
from ..config import Config

class TWS_Program(BaseProgram):
    def __init__(self, schedule, config: Config):
        super().__init__(schedule, config)
        # Override the monitor function with a custom one.
        self.monitor_func = self.custom_monitor
        self.is_down = True

    @BaseProgram.record_start
    def start(self):
        self.job_logger.debug(f"Starting TWS program: {self.name}")
        if not check_ib_valid_time():
            self.job_logger.info("Current time is not valid for starting TWS.")
            return

        list_and_kill_process("ibcstart.sh")
        list_and_kill_process("xterm")

        try:
            env = os.environ.copy()

            # Hard-set these; don't depend on .bashrc
            env["DISPLAY"] = env.get("DISPLAY", ":1")  # or hardcode ":1"
            env["XAUTHORITY"] = env.get("XAUTHORITY", "/home/kyle/.Xauthority")

            # Make sure conda + ibc are on PATH if needed
            env["PATH"] = "/home/kyle/miniconda3/condabin:/home/kyle/miniconda3/bin:" + env.get("PATH", "")

            command = f"nohup /opt/ibc/twsstart.sh >> {self.log_file} 2>&1 &"

            proc = subprocess.Popen(
                ["bash", "-lc", command],
                preexec_fn=os.setsid,
                env=env,
            )
            self.job_logger.info(f"Started TWS program '{self.name}' with PID {proc.pid}")
            return proc.pid

        except Exception as e:
            self.job_logger.error(f"Failed to start TWS program '{self.name}': {e}")
            return None

    @BaseProgram.record_stop
    def stop(self):
        """
        Stops the TWS program.
        """
        self.job_logger.debug(f"Stopping TWS program: {self.name}")
        
        try:
            if self.pid:
                try:
                    os.kill(self.pid, signal.SIGTERM)
                except OSError:
                    pass
            list_and_kill_process("ibcstart.sh")
            list_and_kill_process("xterm")

            self.job_logger.info(f"TWS program '{self.name}' terminated.")
        except Exception as e:
            self.job_logger.error(f"Error stopping TWS program '{self.name}': {e}")

    def custom_monitor(self):
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        from ib_insync import IB

        if not check_ib_valid_time():
            self.job_logger.debug("Outside IB operating hours, stopping process.")
            return False

        try:
            ib = IB()

            host = getattr(self.config, "ib_host", "127.0.0.1")
            port = getattr(self.config, "ib_port", 7497)
            client_id = getattr(self.config, "ib_client_id", 987)
            timeout = getattr(self.config, "ib_timeout", 5)

            ib.connect(host, port, clientId=client_id, timeout=timeout)

            summary = ib.accountSummary()
            netliq = next((x for x in summary if x.tag == "NetLiquidation"), None) \
                    or next((x for x in summary if x.tag == "TotalCashValue"), None)

            if netliq is None:
                raise RuntimeError("Connected to IB but accountSummary missing NetLiquidation/TotalCashValue")

            self.job_logger.debug(f"IB online. {netliq.tag}={netliq.value} {netliq.currency}")

            ib.disconnect()

            if self.is_down:
                self.is_down = False
                return "NOTIFY_SUCCESS"

            return "SUCCESS"

        except Exception as e:
            self.job_logger.error(f"Error fetching broker data: {e}")

            if not self.is_down:
                self.is_down = True
                return "RESTART"

            return "SILENT_RESTART"