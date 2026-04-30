import sys
import os
import threading
import subprocess
import logging
import math
from pathlib import Path
from datetime import datetime, timedelta
from .utils import get_job_sched
from ..config import Config
from .Job import Job


class Task(Job):
    def __init__(self, schedule, config: Config):

        """
        Task class handles calling of all scheduled functions, aka tasks.
        Since a task only does a single function call, I don't think
        there's a need to make this have a task defintion per task like
        with the programs.
        """        
        
        super().__init__(schedule, config)

        self.cmd = schedule.get('cmd')
        self.start_time_str = schedule.get('start')
        self.freq_str = schedule.get('freq', None)
        self.stop_time_str = schedule.get('stop', None)
        self.run_on_complete = schedule.get('run_on_complete', [])

        self.task_log_dir = Path(config.log_dir) / self.name


    # Utility methods
    def get_target_datetime(self, time_str, date_obj):
        """
        Convert a time string (e.g., '9:00 am ET') into a datetime object on the given date.
        """
        cleaned = time_str.strip()
        raw_parts = cleaned.split()
        if raw_parts and raw_parts[-1].lower() in self._TZ_SUFFIXES:
            cleaned = " ".join(raw_parts[:-1])
        parts = cleaned.lower().split()
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
            self.job_logger.error(f"Error parsing frequency '{freq_str}': {e}")
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

    def schedule(self):
        """
        Schedule the task to run at the next appropriate time based on its start time,
        frequency, and allowed days. When it's time, call run_threaded().
        """
        # Guard clause: Dependent tasks with no start time don't need scheduling logic
        if not self.start_time_str:
            self.job_logger.debug(f"Task '{self.name}' has no start time; skipping automatic scheduling.")
            return

        now = datetime.now()
        candidate_date = now.date()
        start_dt, stop_dt = self.get_day_window(candidate_date)

        # If today is not allowed or we've passed today’s window, advance to next allowed date
        if now.weekday() not in self.get_allowed_days() or now >= stop_dt:
            candidate_date = self.get_next_allowed_date(now.date(), days_ahead=1)
            start_dt, stop_dt = self.get_day_window(candidate_date)

        freq_seconds = self.parse_frequency(self.freq_str) if self.freq_str else None

        if freq_seconds and start_dt <= now < stop_dt:
            elapsed = (now - start_dt).total_seconds()
            
            # --- FIX: Use floor + 1 here to match _schedule_next_run and prevent drift ---
            n = math.floor(elapsed / freq_seconds) + 1
            next_run = start_dt + timedelta(seconds=n * freq_seconds)
            
            if next_run > stop_dt:
                candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
                start_dt, stop_dt = self.get_day_window(candidate_date)
                next_run = start_dt
        elif now < start_dt:
            next_run = start_dt
        else:
            # No frequency specified or current time >= stop time
            candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
            start_dt, stop_dt = self.get_day_window(candidate_date)
            next_run = start_dt

        delay = (next_run - datetime.now()).total_seconds()
        
        # Failsafe
        if delay < 0:
            delay = 1.0
            
        self.job_logger.info(
            f"Scheduling task '{self.name}' to run in {delay:.0f} seconds (next run at {next_run})"
        )
        timer = threading.Timer(delay, self.run_threaded)
        timer.daemon = True
        timer.start()

    def run_threaded(self):
        """
        Launch this task in a separate Python process. While that process runs,
        its stdout/stderr are appended to self.log_file. Once it exits, we update
        status, schedule the next run, and trigger dependents.
        """
        def _worker():
            # 1) Build the subprocess command
            cmd = self.cmd

            # 2) Open a fresh timestamped log file for this run
            try:
                log_fh = self._open_log_file()
            except Exception as e:
                self.job_logger.error(f"Cannot open log file for '{self.name}': {e}")
                return

            # 3) Launch the subprocess, redirecting stdout+stderr → log_fh
            self.job_logger.info(f"Starting subprocess for task '{self.name}': {cmd}")
            proc = subprocess.Popen(
                cmd,
                stdout=log_fh,
                stderr=subprocess.STDOUT,
            )

            exit_code = None
            try:
                # 4) Wait for it to finish
                exit_code = proc.wait()
            except Exception as e:
                self.job_logger.error(f"Error while waiting for subprocess '{self.name}': {e}")
            finally:
                log_fh.close()

            # 5) Update status based on exit code
            status = self.read_status()
            if exit_code == 0:
                self.job_logger.info(f"Task '{self.name}' subprocess exited cleanly (code 0)")
                status['last-ran'] = datetime.now().isoformat(sep=' ', timespec='seconds')
            else:
                self.job_logger.error(
                    f"Task '{self.name}' subprocess exited with code {exit_code}"
                )
                status['last-err'] = datetime.now().isoformat(sep=' ', timespec='seconds')

            self.write_status(status)

            # 6) Trigger any dependent tasks once completed
            self._trigger_dependents()

        # Start the worker thread
        thread = threading.Thread(target=_worker, name=f"task-{self.name}")
        thread.daemon = True
        thread.start()
        
        # 7) Now schedule the next run IMMEDIATELY and independently of how long the subprocess takes.
        # This prevents the scheduler from stalling if the subprocess hangs.
        self._schedule_next_run()

        return thread


    def _schedule_next_run(self):
            """
            Calculates the next run datetime snapped to the frequency grid 
            to prevent execution-time drift. Then starts a Timer.
            """
            # Guard clause: Do not attempt to schedule next run if there is no start_time defined
            if not self.start_time_str:
                return

            now = datetime.now()
            candidate_date = now.date()
            start_dt, stop_dt = self.get_day_window(candidate_date)

            if self.freq_str:
                freq_seconds = self.parse_frequency(self.freq_str)
                
                # Align the next run to the exact frequency grid relative to start_dt
                if start_dt <= now < stop_dt:
                    elapsed = (now - start_dt).total_seconds()
                    
                    # Floor + 1 ensures we always target the *strictly next* grid interval
                    n = math.floor(elapsed / freq_seconds) + 1
                    next_run = start_dt + timedelta(seconds=n * freq_seconds)
                    
                    # If the grid calculation pushes us past stop_dt, rollover to next day
                    if next_run > stop_dt:
                        candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
                        start_dt, stop_dt = self.get_day_window(candidate_date)
                        next_run = start_dt
                        
                else:
                    # If we are past stop_dt (or before start_dt), find the next allowed start_dt
                    if now >= stop_dt:
                        candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
                        start_dt, stop_dt = self.get_day_window(candidate_date)
                    next_run = start_dt
                    
            else:
                if now >= start_dt:
                    candidate_date = self.get_next_allowed_date(candidate_date, days_ahead=1)
                    start_dt, stop_dt = self.get_day_window(candidate_date)
                next_run = start_dt

            delay = (next_run - datetime.now()).total_seconds()
            
            # Failsafe: if delay is somehow negative, run in 1 second
            if delay < 0:
                delay = 1.0 
                
            self.job_logger.debug(
                f"Rescheduling task '{self.name}' to run again in {delay:.0f} seconds (next run at {next_run})"
            )
            timer = threading.Timer(delay, self.run_threaded)
            timer.daemon = True
            timer.start()

    def _open_log_file(self, keep: int = 10):
        """
        Create a new timestamped log file under task_log_dir and return an open
        file handle for appending. Deletes the oldest files if more than keep exist.
        """
        self.task_log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        log_path = self.task_log_dir / f"{ts}.log"
        existing = sorted(self.task_log_dir.glob("*.log"))
        for old in existing[:max(0, len(existing) - keep + 1)]:
            try:
                old.unlink()
            except Exception:
                pass
        return open(log_path, "w")

    def _trigger_dependents(self):
        for dep in self.run_on_complete:
            self.job_logger.debug(f"Task '{self.name}' completed, triggering '{dep}'")
            
            # This returns a raw dictionary from the JSON
            dependent_config = get_job_sched(dep, "task", self.config.schedule_file)

            if dependent_config:
                dependent_task = Task(dependent_config, self.config)

                if not dependent_task.start_time_str:
                    self.job_logger.debug(f"Dependent '{dep}' has no start time; running immediately.")
                    threading.Thread(target=dependent_task.run_threaded, daemon=True).start()
                else:
                    self.job_logger.debug(f"Dependent '{dep}' has a start time; scheduling it.")
                    dependent_task.schedule()
            else:
                self.job_logger.error(f"Dependent task '{dep}' not found in scheduler.")