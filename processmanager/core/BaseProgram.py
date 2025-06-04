# program_base.py
import subprocess
import threading
import time
import os
import json
import logging

from datetime import datetime
from abc import ABC, abstractmethod
from .Job import Job
from functools import wraps
# from .logger_setup import setup_logger 
from ..config import Config

class BaseProgram(Job):
    
    def __init__(self, schedule, config: Config):

        """
        Program base which handles schedule parsing, status updates,
        and logging. Status and logging dirs are set globally in the 
        config object.
        """ 

        super().__init__(schedule, config)

        # Parse program specific info from schedule
        self.keep_alive = schedule.get('keep_alive', False)
        self.check_alive_freq = self.parse_frequency(schedule.get('check_alive_freq', '1 m'))
        self.max_retries = schedule.get('max_retries', 0)
        self.run_on_start = schedule.get('run_on_start', False)

        # Optional schedule times for programs.
        start_str = schedule.get('start_time') or schedule.get('start')
        end_str = schedule.get('end_time') or schedule.get('end')

        self.schedule_start = self.parse_time_str(start_str) if start_str else None
        self.schedule_end = self.parse_time_str(end_str) if end_str else None

        # Set the default monitor function.
        self.monitor_func = self.default_monitor

        self.retries = 0
        self.process = None


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

    def disable_restart(self, bool):
        status = self.read_status()
        status['disable_restart'] = bool 
        self.write_status(status)
        
    @staticmethod
    def record_start(func):
        """
        Decorator for start() methods.
        Before starting, checks if there's an active PID in the status file.
        If found, it kills that process.
        After a successful start (i.e. a PID is returned), writes the status JSON
        file with pid, time_started, and num_retries.
        Also updates shared state if available.
        """
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            # Check if a status file exists with an active pid.
            status = self.read_status()
            if status and status.get("pid", 0):
                old_pid = status.get("pid")
                try:
                    os.kill(old_pid, 9)  # Force kill the old process.
                    self.job_logger.info(
                        f"Program {self.name} killed existing process with PID {old_pid} before starting new process."
                    )
                except Exception as e:
                    self.job_logger.error(
                        f"Error killing process {old_pid} for program {self.name}: {e}"
                    )
            pid = func(self, *args, **kwargs)
            if pid:
                new_status = {
                    "pid": pid,
                    "time_started": datetime.now().isoformat(sep=' ', timespec='seconds'),
                    "num_retries": self.retries,
                    "status": "running"
                }
                self.write_status(new_status)
            return pid
        return wrapper

    @staticmethod
    def record_stop(func):
        """
        Decorator for stop() methods.
        After stopping, update the status JSON file to set pid to 0 and status to 'stopped'.
        Also updates shared state if available.
        """
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            status = {
                "pid": 0,
                "time_started": None,
                "num_retries": self.retries,
                "status": "stopped"
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
            # Read the current status from the status file.
            current_status = self.read_status() or {}
            
            # Check for disable flag before proceeding.
            if current_status.get("disable_restart", False):
                self.job_logger.info(f"Program '{self.name}' is disabled. Skipping monitor loop.")
                time.sleep(self.check_alive_freq)
                continue

            current_status["last_checkup"] = datetime.now().isoformat(sep=' ', timespec='seconds')
            self.write_status(current_status)

            if not self.within_schedule():
                if self.process and self.process.poll() is None:
                    self.job_logger.info(f"Program '{self.name}' is outside its scheduled time. Stopping.")
                    self.stop()
                time.sleep(self.check_alive_freq)
                continue

            if self.monitor_func():
                self.job_logger.warning(f"Program '{self.name}' needs restart.")
                if not self.keep_alive:
                    self.job_logger.info(f"Keep alive flag is false for '{self.name}'. Ending monitor loop.")
                    break
                self.retries += 1
                if self.retries <= self.max_retries:
                    self.job_logger.info(f"Restarting program '{self.name}', attempt {self.retries}.")
                    self.start()
                    self.notify_restart(additional_info="Restarted by monitor loop.")
                else:
                    self.job_logger.error(f"Max retries reached for '{self.name}'. No further attempts will be made.")
                    self.notify_failure(additional_info="Exceeded max retries.")
                    break
            else:
                self.job_logger.debug(f"Program '{self.name}' is running fine.")
                self.retries = 0

            time.sleep(self.check_alive_freq)


