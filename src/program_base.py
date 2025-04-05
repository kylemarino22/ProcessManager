# program_base.py
import subprocess
import threading
import time
import os
import json
from datetime import datetime
from abc import ABC, abstractmethod
from functools import wraps
from logger_setup import setup_process_manager_logger
from syslogdiag.email_via_db_interface import send_production_mail_msg
from syslogdiag.emailing import send_mail_msg


class BaseProgram(ABC):
    def __init__(self, config):
        self.name = config.get('name')
        self.status_logger = setup_process_manager_logger()
        self.output_file = config.get('output_file', f"{self.name}_output.log")
        self.keep_alive = config.get('keep_alive', False)
        self.check_alive_freq = self.parse_frequency(config.get('check_alive_freq', '1 m'))
        self.max_retries = config.get('max_retries', 0)
        self.retries = 0
        self.process = None

        # Optional schedule times for programs.
        self.schedule_start = None
        self.schedule_end = None
        start_str = config.get('start_time') or config.get('start')
        end_str = config.get('end_time') or config.get('end')
        if start_str:
            self.schedule_start = self.parse_time_str(start_str)
        if end_str:
            self.schedule_end = self.parse_time_str(end_str)

        # Status file path for recording PID, time started, and num_retries.
        # Default to statuses/<program_name>.json unless provided in config.
        self.status_file = config.get("status_file", f"statuses/{self.name}.json")
        # Set the default monitor function.
        self.monitor_func = self.default_monitor

    def parse_frequency(self, freq_str):
        try:
            value, unit = freq_str.split()
            value = int(value)
            if unit.lower().startswith('m'):
                return value * 60
            elif unit.lower().startswith('s'):
                return value
            elif unit.lower().startswith('h'):
                return value * 3600
        except Exception as e:
            self.status_logger.error(f"Error parsing frequency '{freq_str}': {e}")
        return 60  # default interval

    def parse_time_str(self, time_str):
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            try:
                return datetime.strptime(time_str, "%I:%M %p").time()
            except Exception as e:
                self.status_logger.error(f"Error parsing time string '{time_str}': {e}")
                return None

    def within_schedule(self):
        if self.schedule_start is None or self.schedule_end is None:
            return True
        now = datetime.now().time()
        return self.schedule_start <= now <= self.schedule_end

    def default_monitor(self):
        # Check if the process is running by reading the status file.
        pid_running = False
        status = self.read_status()
        if status and status.get("pid", 0):
            pid = status.get("pid")
            try:
                os.kill(pid, 0)  # Signal 0: check for existence.
                pid_running = True
            except OSError:
                pid_running = False
        else:
            pid_running = False

        return pid_running

    def write_status(self, status_dict):
        try:
            os.makedirs(os.path.dirname(self.status_file), exist_ok=True)
            with open(self.status_file, "w") as f:
                json.dump(status_dict, f)
        except Exception as e:
            self.status_logger.error(f"Error writing status file: {e}")

    def read_status(self):
        if not os.path.exists(self.status_file):
            return None
        try:
            with open(self.status_file, "r") as f:
                return json.load(f)
        except Exception as e:
            self.status_logger.error(f"Error reading status file: {e}")
            return None

    @staticmethod
    def record_start(func):
        """
        Decorator for start() methods.
        Before starting, checks if there's an active PID in the status file.
        If found, it kills that process.
        After a successful start (i.e. a PID is returned), writes the status JSON
        file with pid, time_started, and num_retries.
        """
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Check if a status file exists with an active pid.
            status = self.read_status()
            if status and status.get("pid", 0):
                old_pid = status.get("pid")
                try:
                    os.kill(old_pid, 9)  # Force kill the old process.
                    self.status_logger.info(
                        f"Killed existing process with PID {old_pid} before starting new process."
                    )
                except Exception as e:
                    self.status_logger.error(
                        f"Error killing existing process with PID {old_pid}: {e}"
                    )
            pid = func(self, *args, **kwargs)
            if pid:
                new_status = {
                    "pid": pid,
                    "time_started": datetime.now().isoformat(),
                    "num_retries": self.retries
                }
                self.write_status(new_status)
            return pid
        return wrapper

    @staticmethod
    def record_stop(func):
        """
        Decorator for stop() methods.
        After stopping, update the status JSON file to set pid to 0.
        """
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            status = {
                "pid": 0,
                "time_started": None,
                "num_retries": self.retries
            }
            self.write_status(status)
            return result
        return wrapper

    @abstractmethod
    def start(self):
        """
        Abstract method for starting the program.
        Child classes must override start() with the actual start logic.
        The returned value should be the PID of the spawned process.
        """
        pass

    @abstractmethod
    def stop(self):
        """
        Abstract method for stopping the program.
        Child classes must override stop() with the actual stop logic.
        """
        pass

    def monitor(self):
        """
        Repeatedly checks whether the program needs a restart.
        If the current time is outside the scheduled window, the program is stopped.
        Otherwise, if the monitor function signals a restart and keep_alive is True, the program is restarted.
        If keep_alive is False, the monitor loop ends.
        """
        while True:
            if not self.within_schedule():
                if self.process and self.process.poll() is None:
                    self.status_logger.info(f"Program '{self.name}' is outside its scheduled time. Stopping.")
                    self.stop()
                continue

            if self.monitor_func():
                self.status_logger.warning(f"Program '{self.name}' needs restart.")
                if not self.keep_alive:
                    self.status_logger.info(f"Keep alive flag is false for '{self.name}'. Ending monitor loop.")
                    break
                self.retries += 1
                if self.retries <= self.max_retries:
                    self.status_logger.info(f"Restarting program '{self.name}', attempt {self.retries}.")
                    self.start()
                    self.notify_restart(additional_info="Restarted by monitor loop.")
                else:
                    self.status_logger.error(f"Max retries reached for '{self.name}'. No further attempts will be made.")
                    self.notify_failure(additional_info="Exceeded max retries.")
                    break
            else:
                self.status_logger.debug(f"Program '{self.name}' is running fine.")
                self.retries = 0

            time.sleep(self.check_alive_freq)

    def notify_restart(self, additional_info=""):
        """
        Notifies via email that the script has died and was successfully restarted.
        """
        subject = f"Script Restarted: {self.name}"
        body = f"The script '{self.name}' has died and was successfully restarted at {datetime.now().isoformat()}.\n"
        if additional_info:
            body += f"\nAdditional Info: {additional_info}"
        send_mail_msg(body, subject)

    def notify_failure(self, additional_info=""):
        """
        Notifies urgently via email that the script has failed more than 10 times.
        """
        subject = f"URGENT: Script {self.name} failed more than 10 times"
        body = f"The script '{self.name}' has failed {self.retries} times as of {datetime.now().isoformat()}.\nImmediate action is required."
        if additional_info:
            body += f"\nAdditional Info: {additional_info}"
        send_mail_msg(body, subject)