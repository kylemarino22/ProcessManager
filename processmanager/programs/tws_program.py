# tws_program.py
from ..core.BaseProgram import BaseProgram
from sysdata.data_blob import dataBlob
from sysproduction.data.broker import dataBroker
from ..core.utils import check_ib_valid_time, list_and_kill_process
from datetime import datetime
import json
import os
import subprocess
import time
import threading
from ..config import Config
import concurrent.futures


class TWS_Program(BaseProgram):
    def __init__(self, schedule, config: Config):
        super().__init__(schedule, config)
        # Override the monitor function with a custom one.
        self.monitor_func = self.custom_monitor

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
        # Kill any existing IB-related processes.
        list_and_kill_process("ibcstart.sh")
        list_and_kill_process("xterm")
        try:
            command = f"nohup /opt/ibc/twsstart.sh >> {self.log_file} 2>&1 &"
            self.process = subprocess.Popen(
                ["bash", "-c", command],
                preexec_fn=os.setsid
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
        """
        Custom monitoring function for the TWS program.
        Calls the base default monitor and adds additional checks.
        Returns True if the program should be restarted.
        """

        import asyncio

        # 1) Get or create the asyncio loop for this thread.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 2) If outside IB hours, indicate no restart now.
        if not check_ib_valid_time():
            self.job_logger.debug("Outside IB operating hours, stopping process.")
            return False  # "no restart needed until hours resume"

        try:
            self.data = dataBlob()
            self.job_logger.debug("Creating IB conn through dataBroker ...")

            # 3) **Run dataBroker(...) with a 3s timeout on the same loop**.
            #    This assumes that dataBroker(...) is defined as:
            #        async def dataBroker(data_blob): ...
            #
            #    If dataBroker is NOT already async, you’d first have to wrap it in a coroutine.
            #

            broker_data = dataBroker(self.data)
            self.job_logger.debug("Created data broker")
            
            # coro = dataBroker(self.data)
            # try:
            #     broker_data = loop.run_until_complete(
            #         asyncio.wait_for(coro, timeout=3.0)
            #     )
            #     self.job_logger.debug("[TWS monitor] Fetching broker data succeeded")
            # except asyncio.TimeoutError:
            #     self.job_logger.error("[TWS monitor] dataBroker() timed out after 3 seconds")
            #     return True   # signal “failed/timeout → restart needed”
            # except Exception as exc:
            #     self.job_logger.error(f"[TWS monitor] dataBroker raised: {exc}")
            #     return True

            # 4) If we got here, broker_data is available.
            total_capital = broker_data.get_total_capital_value_in_base_currency()

            #    Disconnect from IB cleanly
            self.data.close()

            self.job_logger.debug(f"IB online. Total capital: {total_capital}")

            return False  # no restart needed

        except Exception as e:
            self.job_logger.error(f"Error fetching broker data: {e}")
            return True