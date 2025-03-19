import json
import time
from logger_setup import setup_logger
from program import Program
from task import Task
from datetime import datetime

class Scheduler:
    instance = None  # Will hold a reference to the current Scheduler instance

    def __init__(self, schedules_file='schedules.json', statuses_file='statuses.json'):
        self.logger = setup_logger("Scheduler", "scheduler.log")
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
                # Assume the file structure is: { "schedules": [ ... ] }
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
                self.programs.append(Program(job))
            elif job.get('type') == 'task':
                task = Task(job)
                self.tasks.append(task)
                self.unsorted_task_queue.append(task)

        # Filter tasks with start times.
        start_time_tasks = [t for t in self.tasks if t.start_time_str]

        if start_time_tasks:
            self.sorted_task_queue = sorted(
                start_time_tasks,
                key=lambda t: t.get_target_datetime(t.start_time_str, datetime.now().date()).timestamp()
            )
        else:
            self.sorted_task_queue = None

        # Create a dictionary of tasks for dependency lookups.
        self.task_dict = {task.name: task for task in self.tasks}
        # Set the global scheduler instance.
        Scheduler.instance = self

        self.logger.debug("Initialization complete with %d programs and %d tasks",
                          len(self.programs), len(self.tasks))

    def start_programs(self):
        self.logger.info("Starting all programs")
        for prog in self.programs:
            prog.start()

    def schedule_tasks(self):
        self.logger.info("Scheduling tasks")
        if self.sorted_task_queue:
            for task in self.sorted_task_queue:
                task.schedule()

    def run(self):
        self.logger.info("Scheduler starting")
        self.initialize()
        self.start_programs()
        self.schedule_tasks()
        # Keep the scheduler running.
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Scheduler shutting down")
