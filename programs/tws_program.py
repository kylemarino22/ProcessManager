# tws_program.py
from program_base import BaseProgram
from sysdata.data_blob import dataBlob
from sysproduction.data.broker import dataBroker
from utils import check_ib_valid_time, list_and_kill_process
from datetime import datetime
import json
import os
import subprocess
import time
import threading

class TWS_Program(BaseProgram):
    def __init__(self, config):
        super().__init__(config)
        # Override the monitor function with a custom one.
        self.monitor_func = self.custom_monitor

    def start(self):
        """
        Starts the TWS program using a predefined command.
        Only starts if within both the schedule (if provided) and valid IB operating hours.
        """
        self.status_logger.debug(f"Starting TWS program: {self.name}")
        if not check_ib_valid_time():
            self.status_logger.info("Current time is not valid for starting TWS.")
            return
        # Kill any existing IB-related processes.
        list_and_kill_process("ibcstart.sh")
        list_and_kill_process("xterm")
        try:
            self.process = subprocess.Popen(
                ["bash", "-c", "nohup /opt/ibc/twsstart.sh >> /home/kyle/echos/IBC_log.txt 2>&1 &"],
                preexec_fn=os.setsid
            )
            self.status_logger.info(f"Started TWS program '{self.name}' with PID {self.process.pid}")

        except Exception as e:
            self.status_logger.error(f"Failed to start TWS program '{self.name}': {e}")


    def stop(self):
        """
        Stops the TWS program.
        """
        self.status_logger.debug(f"Stopping TWS program: {self.name}")
        if self.process:
            try:
                self.process.terminate()
                list_and_kill_process("ibcstart.sh")
                list_and_kill_process("xterm")
                
                self.status_logger.info(f"TWS program '{self.name}' terminated.")
            except Exception as e:
                self.status_logger.error(f"Error stopping TWS program '{self.name}': {e}")

    def custom_monitor(self):
        """
        Custom monitoring function for the TWS program.
        Calls the base default monitor and adds additional checks.
        Returns True if the program should be restarted.
        """

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

        print("asdfasdf")

        # If IB operating hours are not valid, stop the process.
        if not check_ib_valid_time():
            # self.stop()
            print("Outside IB operating hours, stopping process.")
            return True  # Signal that a restart is needed when valid time resumes.

        # Wait briefly before further checking.
        # time.sleep(20)

        ib_online = True
        total_account_value_in_base_currency = None
        try:
            self.data = dataBlob()
            broker_data = dataBroker(self.data)
            total_account_value_in_base_currency = broker_data.get_total_capital_value_in_base_currency()

            # Disconnect IB here
            self.data.close()
        except Exception as e:
            self.status_logger.error(f"Error fetching broker data: {e}")
            ib_online = False

        datetime_string = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_file_path = self.status_file
        status = {}
        if os.path.exists(status_file_path):
            try:
                with open(status_file_path, "r") as file:
                    status = json.load(file)
            except Exception:
                status = {}

        failed_logins = status.get('failed_logins', 0)
        if not ib_online:
            failed_logins += 1
            self.status_logger.info("Retrying IB login")
            # self.start()  # Attempt a restart.
            return True
        else:
            failed_logins = 0

        status = {
            'ib_online': ib_online,
            'account_value': total_account_value_in_base_currency,
            'last_updated': datetime_string,
            'failed_logins': failed_logins
        }
        try:
            with open(status_file_path, "w") as file:
                file.write(json.dumps(status))
        except Exception as e:
            self.status_logger.error(f"Error writing IB status: {e}")

        return False
