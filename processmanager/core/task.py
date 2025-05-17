import threading
import time
import io
import contextlib
import math
from datetime import datetime, timedelta
from .logger_setup import setup_process_manager_logger
from .utils import dynamic_import

class Task:
    def __init__(self, config):
        self.name = config.get('name')
        self.func_path = config.get('func')
        self.start_time_str = config.get('start')
        self.freq_str = config.get('freq', None)
        self.stop_time_str = config.get('stop', None)
        self.run_on_complete = config.get('run_on_complete', [])
        self.dependencies = config.get('dependencies', [])
        self.days = config.get('days', None)
        self.status_logger = setup_process_manager_logger()
        self.output_file = config.get('log_path', f"{self.name}_output.log")
        self.func = None
        if self.func_path:
            try:
                self.func = dynamic_import(self.func_path)
            except Exception as e:
                self.status_logger.error(f"Error importing function '{self.func_path}': {e}")

    # Utility methods
    def get_target_datetime(self, time_str, date_obj):
        """
        Convert a time string (e.g., '9:00 am') into a datetime object on the given date.
        """
        parts = time_str.lower().replace('pst', '').strip().split()
        time_part = parts[0]
        if ':' in time_part:
            hour_str, minute_str = time_part.split(':')
            hour = int(hour_str)
            minute = int(minute_str)
        else:
            hour = int(time_part)
            minute = 0
        meridiem = parts[1]
        if meridiem == 'pm' and hour != 12:
            hour += 12
        elif meridiem == 'am' and hour == 12:
            hour = 0
        return datetime.combine(date_obj, datetime.min.time()).replace(hour=hour, minute=minute, second=0, microsecond=0)

    def parse_frequency(self, freq_str):
        """
        Parse a frequency string like '5m', '30s', or '1h' and return the frequency in seconds.
        """
        try:
            if freq_str.endswith('m'):
                return int(freq_str[:-1]) * 60
            elif freq_str.endswith('s'):
                return int(freq_str[:-1])
            elif freq_str.endswith('h'):
                return int(freq_str[:-1]) * 3600
        except Exception as e:
            self.status_logger.error(f"Error parsing frequency '{freq_str}': {e}")
        return None

    def get_allowed_days(self):
        """
        Return a list of allowed weekdays (0=Monday, 6=Sunday) based on self.days.
        If no days are specified, all days are allowed.
        """
        mapping = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
        if self.days:
            return [mapping[d.lower()] for d in self.days if d.lower() in mapping]
        return list(range(7))

    def get_day_window(self, candidate_date):
        """
        Return the start and stop datetimes for a given candidate date based on the task's start and stop time strings.
        """
        start_dt = self.get_target_datetime(self.start_time_str, candidate_date)
        if self.stop_time_str:
            stop_dt = self.get_target_datetime(self.stop_time_str, candidate_date)
        else:
            stop_dt = datetime.combine(candidate_date, datetime.min.time()).replace(hour=23, minute=59, second=59, microsecond=0)
        return start_dt, stop_dt

    def get_next_allowed_date(self, current_date, days_ahead=1):
        """
        Return the next allowed date (as a date object) after current_date based on the allowed days.
        """
        allowed_days = self.get_allowed_days()
        while True:
            next_date = current_date + timedelta(days=days_ahead)
            if next_date.weekday() in allowed_days:
                return next_date
            days_ahead += 1

    # Scheduling methods
    def schedule(self):
        """
        Schedule the task to run at the next appropriate time based on its start time, frequency, and allowed days.
        """
        now = datetime.now()
        candidate_date = now.date()
        start_dt, stop_dt = self.get_day_window(candidate_date)

        # If today is not allowed or we've passed today's window, move to the next allowed date.
        if now.weekday() not in self.get_allowed_days() or now >= stop_dt:
            candidate_date = self.get_next_allowed_date(now.date(), days_ahead=1)
            start_dt, stop_dt = self.get_day_window(candidate_date)

        freq_seconds = self.parse_frequency(self.freq_str) if self.freq_str else None

        if freq_seconds and now >= start_dt and now < stop_dt:
            elapsed = (now - start_dt).total_seconds()
            n = math.ceil(elapsed / freq_seconds)
            next_run = start_dt + timedelta(seconds=n * freq_seconds)
            if next_run > stop_dt:
                candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
                start_dt, stop_dt = self.get_day_window(candidate_date)
                next_run = start_dt
        elif now < start_dt:
            next_run = start_dt
        else:
            # No frequency specified or current time is past stop time.
            candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
            start_dt, stop_dt = self.get_day_window(candidate_date)
            next_run = start_dt

        delay = (next_run - datetime.now()).total_seconds()
        self.status_logger.debug(f"Scheduling task '{self.name}' to run in {delay:.0f} seconds (next run at {next_run})")
        timer = threading.Timer(delay, self.run)
        timer.start()

    def run(self):
        """
        Execute the task, log its output, reschedule it based on its frequency or next start time,
        and trigger any dependent tasks.
        """
        self.status_logger.info(f"Running task '{self.name}'")
        try:
            with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                self.func()
                output = buf.getvalue()
            if output:
                with open(self.output_file, 'a') as f:
                    f.write(output)
            self.status_logger.info(f"Task '{self.name}' completed successfully")
        except Exception as e:
            self.status_logger.error(f"Error executing task '{self.name}': {e}")

        # Rescheduling logic after run
        now = datetime.now()
        candidate_date = now.date()
        start_dt, stop_dt = self.get_day_window(candidate_date)
        allowed_days = self.get_allowed_days()

        if self.freq_str:
            freq_seconds = self.parse_frequency(self.freq_str)
            if freq_seconds:
                next_run = now + timedelta(seconds=freq_seconds)
                if now >= stop_dt or next_run > stop_dt:
                    candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
                    start_dt, stop_dt = self.get_day_window(candidate_date)
                    next_run = start_dt
        else:
            # No frequency specified; schedule at the next valid day's start if we've passed today's scheduled start.
            if now >= start_dt:
                candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
            start_dt, stop_dt = self.get_day_window(candidate_date)
            next_run = start_dt

        delay = (next_run - datetime.now()).total_seconds()
        self.status_logger.debug(f"Rescheduling task '{self.name}' to run again in {delay:.0f} seconds (next run at {next_run})")
        timer = threading.Timer(delay, self.run)
        timer.start()

        # Trigger dependent tasks.
        from scheduler import Scheduler  # local import to avoid circular dependency
        for dep in self.run_on_complete:
            self.status_logger.debug(f"Task '{self.name}' completed, triggering dependent task '{dep}'")
            dependent_task = Scheduler.instance.task_dict.get(dep)
            if dependent_task:
                if not dependent_task.start_time_str:
                    self.status_logger.debug(f"Dependent task '{dep}' has no start time; running immediately.")
                    threading.Thread(target=dependent_task.run).start()
                else:
                    self.status_logger.debug(f"Dependent task '{dep}' has a start time; scheduling it.")
                    dependent_task.schedule()
            else:
                self.status_logger.error(f"Dependent task '{dep}' not found in scheduler.")
