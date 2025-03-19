import threading
import time
import io
import contextlib
import math
from datetime import datetime, timedelta
from logger_setup import setup_logger
from utils import dynamic_import

class Task:
    def __init__(self, config):
        self.name = config.get('name')
        self.func_path = config.get('func')
        self.start_time_str = config.get('start')
        self.freq_str = config.get('freq', None)
        self.stop_time_str = config.get('stop', None)
        self.run_on_complete = config.get('run_on_complete', [])
        self.dependencies = config.get('dependencies', [])
        # New: Optional days field (e.g. ["Mon", "Tue", "Wed", "Thu", "Fri"])
        self.days = config.get('days', None)
        # Use the custom log_path if provided, otherwise default to "<task_name>.log"
        log_path = config.get('log_path', f"{self.name}.log")
        self.logger = setup_logger(self.name, log_path)
        self.func = None
        if self.func_path:
            try:
                self.func = dynamic_import(self.func_path)
            except Exception as e:
                self.logger.error(f"Error importing function '{self.func_path}': {e}")

    def get_target_datetime(self, time_str, date_obj):
        """
        Given a time string like '11:06 am pst' and a date (a datetime.date object),
        return a datetime object for that date with the specified time.
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
        # Combine the provided date with the parsed time.
        return datetime.combine(date_obj, datetime.min.time()).replace(hour=hour, minute=minute, second=0, microsecond=0)

    def parse_frequency(self, freq_str):
        """
        Parse a frequency string like '7m' and return seconds.
        """
        try:
            if freq_str.endswith('m'):
                return int(freq_str[:-1]) * 60
            elif freq_str.endswith('s'):
                return int(freq_str[:-1])
            elif freq_str.endswith('h'):
                return int(freq_str[:-1]) * 3600
        except Exception as e:
            self.logger.error(f"Error parsing frequency '{freq_str}': {e}")
        return None

    def schedule(self):
        """
        Schedule this task to run.
        
        The scheduling logic:
        1. Determine the allowed days based on an optional "days" config (e.g., ["Mon", "Tue", ...]).
           If not provided, all days are allowed.
        2. For a given day, compute the start and stop datetimes. If no stop time is provided,
           default to the end of the day (11:59:59 PM).
        3. If the current time is within the window and a frequency is set, compute the next run time
           as multiples of the frequency from the start time. If that falls after the stop time,
           or if the current day isn’t allowed (or already past the window), find the next allowed day
           and schedule at its start time.
        """
        now = datetime.now()

        # Determine allowed days as integers: Monday=0, Tuesday=1, … Sunday=6.
        if self.days:
            mapping = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
            allowed_days = [mapping[d.lower()] for d in self.days if d.lower() in mapping]
        else:
            allowed_days = [0, 1, 2, 3, 4, 5, 6]

        # Helper: given a candidate date, return start and stop datetime for that day.
        def get_day_window(candidate_date):
            start_dt = self.get_target_datetime(self.start_time_str, candidate_date)
            if self.stop_time_str:
                stop_dt = self.get_target_datetime(self.stop_time_str, candidate_date)
            else:
                # Default stop time: end of day.
                stop_dt = datetime.combine(candidate_date, datetime.min.time()).replace(hour=23, minute=59, second=59, microsecond=0)
            return start_dt, stop_dt

        # Find the next allowed day and its start/stop window.
        candidate_date = now.date()
        start_dt, stop_dt = get_day_window(candidate_date)

        # If today's weekday is not allowed or we've passed the stop time, search for the next allowed day.
        if now.weekday() not in allowed_days or now >= stop_dt:
            days_ahead = 1
            while True:
                next_date = now.date() + timedelta(days=days_ahead)
                if next_date.weekday() in allowed_days:
                    candidate_date = next_date
                    start_dt, stop_dt = get_day_window(candidate_date)
                    break
                days_ahead += 1

        # Now, schedule based on current time relative to the window.
        # Case A: Current time is within the window and a frequency is set.
        freq_seconds = self.parse_frequency(self.freq_str) if self.freq_str else None
        if now >= start_dt and now < stop_dt and freq_seconds:
            elapsed = (now - start_dt).total_seconds()
            n = math.ceil(elapsed / freq_seconds)
            next_run = start_dt + timedelta(seconds=n * freq_seconds)
            if next_run > stop_dt:
                # If the computed next run exceeds today's window, schedule for the next allowed day.
                days_ahead = 1
                while True:
                    next_date = candidate_date + timedelta(days=days_ahead)
                    if next_date.weekday() in allowed_days:
                        candidate_date = next_date
                        start_dt, stop_dt = get_day_window(candidate_date)
                        next_run = start_dt  # start at the beginning of the window on the next allowed day
                        break
                    days_ahead += 1
            delay = (next_run - now).total_seconds()
            self.logger.debug(f"Scheduling task '{self.name}' to run next in {delay:.0f} seconds (within window)")
            timer = threading.Timer(delay, self.run)
            timer.start()

        # Case B: Current time is before the window.
        elif now < start_dt:
            delay = (start_dt - now).total_seconds()
            self.logger.debug(f"Scheduling task '{self.name}' to run at start time in {delay:.0f} seconds")
            timer = threading.Timer(delay, self.run)
            timer.start()
        else:
            # Otherwise, no scheduling is done.
            self.logger.debug(f"Current time is not within a valid window for task '{self.name}'; no scheduling done.")

    def run(self):
        self.logger.info(f"Running task '{self.name}'")
        try:
            if self.func:
                # Capture function output so that any prints go to the log file.
                with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                    self.func()
                    output = buf.getvalue()
                if output:
                    self.logger.info(f"Task '{self.name}' output: {output.strip()}")
                self.logger.info(f"Task '{self.name}' completed successfully")
            else:
                self.logger.error(f"No function defined for task '{self.name}'")
        except Exception as e:
            self.logger.error(f"Error executing task '{self.name}': {e}")

        # Reschedule if a frequency is set.
        if self.freq_str:
            freq_seconds = self.parse_frequency(self.freq_str)
            if freq_seconds:
                next_run = datetime.now() + timedelta(seconds=freq_seconds)
                # Determine today's window (or the next allowed day's window if needed)
                now = datetime.now()
                candidate_date = now.date()
                mapping = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
                if self.days:
                    allowed_days = [mapping[d.lower()] for d in self.days if d.lower() in mapping]
                else:
                    allowed_days = [0, 1, 2, 3, 4, 5, 6]
                def get_day_window(candidate_date):
                    start_dt = self.get_target_datetime(self.start_time_str, candidate_date)
                    if self.stop_time_str:
                        stop_dt = self.get_target_datetime(self.stop_time_str, candidate_date)
                    else:
                        stop_dt = datetime.combine(candidate_date, datetime.min.time()).replace(hour=23, minute=59, second=59, microsecond=0)
                    return start_dt, stop_dt
                start_dt, stop_dt = get_day_window(candidate_date)
                if now >= stop_dt:
                    # If we're past today's window, schedule next allowed day's start.
                    days_ahead = 1
                    while True:
                        next_date = candidate_date + timedelta(days=days_ahead)
                        if next_date.weekday() in allowed_days:
                            candidate_date = next_date
                            start_dt, stop_dt = get_day_window(candidate_date)
                            next_run = start_dt
                            break
                        days_ahead += 1
                elif next_run > stop_dt:
                    # If the next run goes beyond today's window, schedule the next allowed day's start.
                    days_ahead = 1
                    while True:
                        next_date = candidate_date + timedelta(days=days_ahead)
                        if next_date.weekday() in allowed_days:
                            candidate_date = next_date
                            start_dt, stop_dt = get_day_window(candidate_date)
                            next_run = start_dt
                            break
                        days_ahead += 1
                delay = (next_run - datetime.now()).total_seconds()
                self.logger.debug(f"Rescheduling task '{self.name}' to run again in {delay:.0f} seconds")
                timer = threading.Timer(delay, self.run)
                timer.start()

        # Trigger dependent tasks if any.
        from scheduler import Scheduler  # import the Scheduler class
        for dep in self.run_on_complete:
            self.logger.debug(f"Task '{self.name}' completed, triggering dependent task '{dep}'")
            dependent_task = Scheduler.instance.task_dict.get(dep)
            if dependent_task:
                if not dependent_task.start_time_str:
                    # If no start time is set, run it immediately in a separate thread.
                    self.logger.debug(f"Dependent task '{dep}' has no start time; running immediately.")
                    threading.Thread(target=dependent_task.run).start()
                else:
                    # Otherwise, schedule the task as per its configuration.
                    self.logger.debug(f"Dependent task '{dep}' has a start time; scheduling it.")
                    dependent_task.schedule()
            else:
                self.logger.error(f"Dependent task '{dep}' not found in scheduler.")


