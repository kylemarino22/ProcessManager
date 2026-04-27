import os
import logging
import json

from datetime import datetime
from abc import ABC, abstractmethod
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .logger_setup import get_logger
from ..config import Config

from .emailing import send_mail_msg

class Job(ABC):

    _TZ_SUFFIXES = frozenset({"et", "est", "edt", "pst", "pdt", "cst", "cdt", "mst", "mdt", "utc"})
    _DAY_NAMES   = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    _TZ_MAP = {
        "et":  "America/New_York",
        "est": "America/New_York",
        "edt": "America/New_York",
        "pst": "America/Los_Angeles",
        "pdt": "America/Los_Angeles",
        "cst": "America/Chicago",
        "cdt": "America/Chicago",
        "mst": "America/Denver",
        "mdt": "America/Denver",
        "utc": "UTC",
    }

    def __init__(self, schedule, config: Config):

        # Store config in case it's needed somewhere later
        self.config = config

        # Parse common info from schedule
        self.name = schedule.get('name')

        # Status file path for recording PID, time started, and num_retries.
        self.status_file = f"{config.status_dir}/{self.name}.json"

        # Child logger for job. Used to categorize job-specific messages
        self.job_logger = get_logger(self.name)

        # Log file for subprocess output
        self.log_file = f"{config.log_dir}/{self.name}.log"

        # Scheduling: when this job is allowed to run.
        # Accepts keys: start / start_time, end / end_time / stop, days.
        start_str = schedule.get('start') or schedule.get('start_time')
        end_str   = schedule.get('end')   or schedule.get('end_time') or schedule.get('stop')

        self.schedule_start = self.parse_time_str(start_str) if start_str else None
        self.schedule_end   = self.parse_time_str(end_str)   if end_str   else None
        self.days           = schedule.get('days', None)
        self.schedule_tz    = self._parse_tz(start_str or end_str)


    def _parse_tz(self, time_str):
        if not time_str:
            return None
        parts = time_str.strip().split()
        if parts and parts[-1].lower() in self._TZ_SUFFIXES:
            tz_name = self._TZ_MAP.get(parts[-1].lower())
            if tz_name:
                try:
                    return ZoneInfo(tz_name)
                except ZoneInfoNotFoundError:
                    self.job_logger.warning(f"tzdata not installed; ignoring timezone '{parts[-1]}'")
        return None

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
        # Strip a trailing timezone token (e.g. "9:20 AM ET", "5:30 pm pst").
        cleaned = time_str.strip()
        parts = cleaned.split()
        if parts and parts[-1].lower() in self._TZ_SUFFIXES:
            cleaned = " ".join(parts[:-1])
        try:
            return datetime.strptime(cleaned, "%H:%M").time()
        except ValueError:
            try:
                return datetime.strptime(cleaned, "%I:%M %p").time()
            except Exception as e:
                self.job_logger.error(f"Error parsing time string '{time_str}': {e}")
                return None

    def within_schedule(self):
        now_dt = datetime.now(self.schedule_tz) if self.schedule_tz else datetime.now()
        if self.days:
            today = self._DAY_NAMES[now_dt.weekday()]
            if today not in self.days:
                return False
        if self.schedule_start is None or self.schedule_end is None:
            return True
        return self.schedule_start <= now_dt.time() <= self.schedule_end


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