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
        except Exception as e:
            self.job_logger.error(f"Failed to start TWS program '{self.name}': {e}")


    def stop(self):
        """
        Stops the TWS program.
        """
        self.job_logger.debug(f"Stopping TWS program: {self.name}")
        if self.process:
            try:
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

        # This is needed to attach ib to event loop

        import asyncio
        # Create or get an event loop for the current thread
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # First, check the basic process status.
        # TWS is started with a script which opens an xterm window, so we expect the actual process
        # to be "xterm" and not the script name.

        # if self.default_monitor(program):
        #     print("Process not running, restarting...")
        #     return True

        # If IB operating hours are not valid, stop the process.
        if not check_ib_valid_time():
            # self.stop()
            self.job_logger.debug("[TWS monitor] Outside IB operating hours, stopping process.")
            return False  # Signal that a restart is needed when valid time resumes.

        try:
            self.data = dataBlob()
            self.job_logger.debug("[TWS monitor] Creating IB conn through dataBroker ...")

            # 1) Manually create the executor
            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future   = executor.submit(dataBroker, self.data)

            try:
                # 2) Wait up to 3 seconds
                broker_data = future.result(timeout=3)
                self.job_logger.debug("[TWS monitor] Fetching broker data succeeded")
            except concurrent.futures.TimeoutError:
                # 3) Shutdown without waiting for the thread to finish
                #    (Python 3.9+ allows cancel_futures=True)
                executor.shutdown(wait=False, cancel_futures=True)
                self.job_logger.error("[TWS monitor] dataBroker() timed out after 3 seconds")
                # 4) Now re-raise so your outer except sees it
                raise RuntimeError("Failed to get broker_data in time")
            else:
                # If we got broker_data, we can still tear down the pool
                executor.shutdown(wait=False)


            _ = broker_data.get_total_capital_value_in_base_currency()
            # Disconnect IB here
            self.data.close()
            
            return False # No restart needed.

        except Exception as e:
            self.job_logger.error(f"[TWS monitor] Error fetching broker data: {e}")

            return True
