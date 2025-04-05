# scheduler.py
import json
import time
import importlib
from logger_setup import setup_process_manager_logger
from program_base import BaseProgram
from task import Task  # assuming Task is defined elsewhere
from datetime import datetime
import os
import sys
import threading
import traceback

programs_dir = os.path.join(os.path.dirname(__file__), "../programs")
if programs_dir not in sys.path:
    sys.path.insert(0, programs_dir)

class Scheduler:
    instance = None  # Global reference

    def __init__(self, schedules_file='schedules.json', statuses_file='statuses.json'):
        self.logger = setup_process_manager_logger()
        self.schedules_file = schedules_file
        self.statuses_file = statuses_file
        self.programs = []
        self.tasks = []
        self.unsorted_task_queue = []
        self.sorted_task_queue = []
        self.task_dict = {}

    def load_schedules(self):
        self.logger.debug("Loading schedules")
        try:
            with open(self.schedules_file, 'r') as f:
                data = json.load(f)
                return data.get('schedules', [])
        except Exception as e:
            self.logger.error(f"Error loading schedules: {e}")
            return []

    def load_statuses(self):
        self.logger.debug("Loading statuses")
        try:
            with open(self.statuses_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Error loading statuses: {e}")
            return {}

    def initialize(self):
        schedules = self.load_schedules()
        for job in schedules:
            if job.get('type') == 'program':
                program_class_path = job.get('program_class')
                if program_class_path:
                    try:
                        module_name, class_name = program_class_path.rsplit('.', 1)
                        module = importlib.import_module(module_name)
                        cls = getattr(module, class_name)
                        # Ensure the loaded class extends BaseProgram.
                        assert issubclass(cls, BaseProgram), f"{class_name} must extend BaseProgram"
                        self.programs.append(cls(job))
                    except Exception as e:
                        self.logger.error(f"Error loading program class '{program_class_path}': {e}")
                        self.logger.error(traceback.format_exc())
                else:
                    self.logger.error("No 'program_class' specified for a program job")
            elif job.get('type') == 'task':
                from task import Task  # if not already imported
                task = Task(job)
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
        Scheduler.instance = self
        self.logger.debug("Initialization complete with %d programs and %d tasks",
                          len(self.programs), len(self.tasks))

    def schedule_tasks(self):
        self.logger.info("Scheduling tasks")
        if self.sorted_task_queue:
            for task in self.sorted_task_queue:
                task.schedule()

    def run(self):
        self.logger.info("Scheduler starting")
        self.initialize()
        # Instead of blindly starting all programs, spawn a monitor thread for each.
        for prog in self.programs:
            threading.Thread(target=prog.monitor, daemon=True).start()
        self.schedule_tasks()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Scheduler shutting down")
