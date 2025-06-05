# scheduler.py
import json
import time
import importlib
from .logger_setup import setup_pm_logging, get_logger
from .BaseProgram import BaseProgram
from .Task import Task
from .utils import load_schedules
from datetime import datetime
import os
import sys
import threading
import traceback
import hashlib
from ..config import Config
import syslogging
import logging

class Scheduler:
    # instance = None  # Global reference

    def __init__(self, config: Config, log_level=logging.INFO):

        self.config = config
        self.programs = []
        self.tasks = []
        self.unsorted_task_queue = []
        self.sorted_task_queue = []
        self.task_dict = {}

        # Probably don't need mark restart anymore, but I'll keep it since I prob don't need to remove
        setup_pm_logging(config.log_dir, level=log_level, mark_restart=True)        

        self.pm_logger = get_logger("process-manager")
        

    def initialize(self):
        
        schedules, _ = load_schedules(self.config.schedule_file, write_hash=True)

        for job_sched in schedules:

            if job_sched.get('type') == 'program':
                program_class_path = job_sched.get('program_class')
                
                if program_class_path:
                    try:
                        module_name, class_name = program_class_path.rsplit('.', 1)
                        module = importlib.import_module(module_name)
                        cls = getattr(module, class_name)
                        # Ensure the loaded class extends BaseProgram.
                        self.pm_logger.debug(f"Loading program class '{program_class_path}'")
                        assert issubclass(cls, BaseProgram), f"{class_name} must extend BaseProgram"
                        self.programs.append(cls(job_sched, self.config))

                    except Exception as e:
                        self.pm_logger.error(f"Error loading program class '{program_class_path}': {e}")
                        self.pm_logger.error(traceback.format_exc())
                        
                else:
                    self.pm_logger.error("No 'program_class' specified for a program job_sched")

            elif job_sched.get('type') == 'task':
                task = Task(job_sched, self.config)
                self.tasks.append(task)
                self.unsorted_task_queue.append(task)

        # Sort tasks with start times.
        start_time_tasks = [t for t in self.tasks if t.start_time_str]
        if start_time_tasks:
            self.sorted_task_queue = sorted(
                start_time_tasks,
                key=lambda t: t.get_target_datetime(t.start_time_str, datetime.now().date()).timestamp()
            )
            
        else:
            self.sorted_task_queue = None

        self.task_dict = {task.name: task for task in self.tasks}
        # Scheduler.instance = self
        self.pm_logger.info("Initialization complete with %d programs and %d tasks",
                          len(self.programs), len(self.tasks))

    def schedule_tasks(self):
        self.pm_logger.info("Scheduling tasks")
        if self.sorted_task_queue:
            for task in self.sorted_task_queue:
                task.schedule()

    def run(self):

        # Initialize scheduler.log pm_logger here.        
        self.pm_logger.info("Scheduler starting")
        self.initialize()

        # Start all programs.
        for prog in self.programs:
            try:
                if prog.run_on_start and prog.within_schedule():
                    self.pm_logger.info(f"Starting program '{prog.name}' on startup")
                    prog.start()

            except Exception as e:
                self.pm_logger.error(f"Error starting program '{prog.name}': {e}")
                self.pm_logger.error(traceback.format_exc())


        # Instead of blindly starting all programs, spawn a monitor thread for each.
        for prog in self.programs:
            threading.Thread(target=prog.monitor, daemon=True).start()

        self.schedule_tasks()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.pm_logger.info("Scheduler shutting down")
