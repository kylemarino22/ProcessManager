import os
import logging
import json

from datetime import datetime
from abc import ABC, abstractmethod
from .logger_setup import get_logger
from ..config import Config

from syslogdiag.emailing import send_mail_msg 

class Job(ABC):
    
    def __init__(self, schedule, config: Config):
        
        # Store config in case it's needed somewhere later
        self.config = config
        
        # Parse common info from schedule
        self.name = schedule.get('name')

        # Status file path for recording PID, time started, and num_retries.
        self.status_file = f"{config.status_dir}/{self.name}.json"
        
        # Gets global logger setup earlier, or sets up if not yet done
        # self.pm_logger = logging.getLogger("process-manager")

        # Child logger for job. Used to categorize job-specific messages
        self.job_logger = get_logger(self.name)

        # Log file for subprocess output
        self.log_file = f"{config.log_dir}/{self.name}.log"


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
            self.job_logger.error(f"Error parsing frequency '{freq_str}': {e}")
        return 60  # default interval

    def parse_time_str(self, time_str):
        try:
            return datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            try:
                return datetime.strptime(time_str, "%I:%M %p").time()
            except Exception as e:
                self.job_logger.error(f"Error parsing time string '{time_str}': {e}")
                return None


    def within_schedule(self):
        if self.schedule_start is None or self.schedule_end is None:
            return True
        now = datetime.now().time()
        return self.schedule_start <= now <= self.schedule_end


    def write_status(self, status_dict):
        try:
            os.makedirs(os.path.dirname(self.status_file), exist_ok=True)
            with open(self.status_file, "w") as f:
                json.dump(status_dict, f)
        except Exception as e:
            self.job_logger.error(f"Error writing status file: {e}")

    def read_status(self):

        if not os.path.exists(self.status_file):
            return {}
        
        try:
            with open(self.status_file, "r") as f:
                return json.load(f)
        except Exception as e:
            self.job_logger.error(f"Error reading status file: {e}")
            return None

            
    def notify_down(self, additional_info=""):
        """
        Notifies via email that the script has died and was successfully restarted.
        """
        subject = f"Script Down: {self.name}"
        body = f"The script '{self.name}' has died \
            at {datetime.now().isoformat(sep=' ', timespec='seconds')}.\n"
        if additional_info:
            body += f"\nAdditional Info: {additional_info}"
        send_mail_msg(body, subject)

    def notify_up(self, additional_info=""):
        """
        Notifies via email that the is back up.
        """
        subject = f"Script Up: {self.name}"
        body = f"The script '{self.name}' is back up \
            at {datetime.now().isoformat(sep=' ', timespec='seconds')}.\n"
        if additional_info:
            body += f"\nAdditional Info: {additional_info}"
        send_mail_msg(body, subject)        

    def notify_failure(self, additional_info=""):
        """
        Notifies urgently via email that the script has failed more than allowed times.
        """
        subject = f"URGENT: Script {self.name} failed more than allowed times"
        body = f"The script '{self.name}' has failed {self.retries} times as of \
            {datetime.now().isoformat(sep=' ', timespec='seconds')}.\nImmediate action is required."
        if additional_info:
            body += f"\nAdditional Info: {additional_info}"
        send_mail_msg(body, subject)