# tws_program.py
from ..core.BaseProgram import BaseProgram
from ..core.utils import check_ib_valid_time, list_and_kill_process
from datetime import datetime
import os
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
        """
        Starts the TWS program using a predefined command.
        Only starts if within both the schedule (if provided) and valid IB operating hours.
        """
        self.job_logger.debug(f"Starting TWS program: {self.name}")
        if not check_ib_valid_time():
            self.job_logger.info("Current time is not valid for starting TWS.")
            return

        list_and_kill_process("ibcstart.sh")
        list_and_kill_process("xterm")

        try:
            command = f"nohup /opt/ibc/twsstart.sh >> {self.log_file} 2>&1 &"

            self.process = subprocess.Popen(
                ["bash", "-c", command],
                preexec_fn=os.setsid,
            )
            self.job_logger.info(f"Started TWS program '{self.name}' with PID {self.process.pid}")
            return self.process.pid

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
            if self.process:
                self.process.terminate()
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