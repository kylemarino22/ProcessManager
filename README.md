# ProcessManager: A System-Wide Program and Task Scheduler

## 1. Introduction

ProcessManager is a Python-based application designed to schedule, run, and monitor system-wide programs and tasks. It provides a robust framework for managing long-running services and cron-like jobs, with features for ensuring reliability and providing visibility into their status.

The system is built to be managed by a process supervisor like `supervisor`, ensuring that the core scheduler is always running. It uses a command-line interface, `schedulerctl`, for easy interaction and management of the scheduled jobs.

## 2. Core Concepts

The ProcessManager distinguishes between two primary types of jobs: **Programs** and **Tasks**.

### 2.1. Programs

Programs are long-running processes that are expected to be continuously active. The ProcessManager can monitor these programs and restart them if they fail.

* **Keep-Alive**: Programs can be configured with a `keep_alive` flag, which tells the scheduler to automatically restart them if they terminate unexpectedly.

* **Monitoring**: The system includes both a default process monitor and the ability to define custom monitoring functions for more complex health checks.

* **Scheduling**: Programs can be scheduled to run only within specific time windows.

### 2.2. Tasks

Tasks are scripts or functions that are executed at specific times or intervals. They are not expected to run continuously.

* **Time-Based Scheduling**: Tasks can be scheduled to run at a specific time of day (e.g., "11:59 pm pst").

* **Frequency-Based Scheduling**: Tasks can also be configured to run at regular intervals (e.g., "1 h").

* **Dependencies**: Tasks can be configured to trigger other tasks upon completion, allowing for the creation of simple workflows.

## 3. Features

* **Program and Task Scheduling**: Supports both long-running programs and scheduled tasks.

* **Process Monitoring and Keep-Alive**: Automatically restarts failed programs to ensure they are always running.

* **Command-Line Interface (`schedulerctl`)**: Provides a user-friendly CLI for managing and monitoring jobs. The CLI supports the following commands:

  * `list`: Displays the status of all configured programs and tasks.

  * `start`: Manually starts a program.

  * `stop`: Manually stops a program.

  * `run`: Manually triggers a task.

  * `reload`: Reloads the supervisor configuration.

* **Flexible Scheduling**: Supports scheduling by start time, frequency, and specific days of the week.

* **Dependency Management**: Allows tasks to trigger other tasks upon successful completion.

* **Logging**: Provides detailed logging for both the core scheduler and individual jobs. It includes a `TruncatingFileHandler` to manage log file sizes.

* **Email Notifications**: Can send email notifications for job restarts and failures.

## 4. Getting Started

### 4.1. Installation

The project is packaged with `setuptools`, and can be installed via the `setup.py` script. This will also install the `schedulerctl` command-line tool.

```bash
python setup.py install
```

### 4.2. Configuration

The ProcessManager requires a configuration file (`config.py`) to specify the paths for schedules, status files, and logs.

**`processmanager/config.py`**:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Config:
    schedule_file: Path
    status_dir:    Path
    log_dir:       Path

config = Config(
    schedule_file=Path("/home/kyle/ProcessManager/schedules/full_schedule.json"),
    status_dir=   Path("/home/kyle/ProcessManager/statuses"),
    log_dir=      Path("/home/kyle/ProcessManager/logs"),
)
```

### 4.3. Creating Schedules

Schedules are defined in a JSON file, as specified by the `schedule_file` path in the configuration. This file contains a list of all programs and tasks to be managed.

**Example `full_schedule.json`**:

```json
{
    "schedules": [
    {
        "type": "program",
        "name": "nas-monitor",
        "program_class": "processmanager.programs.nas_program.NASProgram",
        "keep_alive": true,
        "check_alive_freq": "10 m",
        "max_retries": 10
    },
    {
        "type": "task",
        "name": "do-backups",
        "main_path": "/home/kyle/ProcessManager/processmanager/tasks/backup_and_reboot.py",
        "start": "11:59 pm pst"
    },
    {
        "type": "task",
        "name": "update-sampled-contracts",
        "main_path" : "/home/kyle/ProcessManager/processmanager/tasks/update_sampled_contracts.py",
        "start": "07:00 am pst",
        "run_on_complete": ["update-fx-data"]

    },
    {
        "type": "task",
        "name": "update-fx-data",
        "main_path" : "/home/kyle/ProcessManager/processmanager/tasks/update_fx_prices.py",
        "run_on_complete": ["download-asia-prices"]
    }
  ]
}
```

### 4.4. Running the Scheduler

The main entry point of the scheduler is `processmanager/main.py`. This script is intended to be run by a process supervisor like `supervisor` to ensure it is always running.

```python
if __name__ == '__main__':
    scheduler = Scheduler(config, logging.INFO)
    scheduler.run()
```

## 5. Usage

The `schedulerctl` command-line tool is the primary way to interact with the ProcessManager.

* **List Status**: View the status of all programs and tasks.

  ```bash
  schedulerctl list
  ```

* **Start a Program**: Manually start a program.

  ```bash
  schedulerctl start <program_name>
  ```

* **Stop a Program**: Manually stop a program.

  ```bash
  schedulerctl stop <program_name>
  ```

* **Run a Task**: Manually trigger a task to run.

  ```bash
  schedulerctl run <task_name>
  ```

* **Reload Supervisor**: Reload the supervisor configuration.

  ```bash
  schedulerctl reload
  ```

## 6. Project Structure

```
processmanager/
├── cli.py                     # Command-line interface logic
├── config.py                  # Configuration for file paths
├── main.py                    # Main entry point for the scheduler
├── core/
│   ├── BaseProgram.py         # Base class for all program types
│   ├── Job.py                 # Base class for all jobs (programs and tasks)
│   ├── Scheduler.py           # Core scheduling logic
│   ├── Task.py                # Class for managing tasks
│   └── utils.py               # Utility functions
├── programs/                  # Implementations of specific programs
│   ├── nas_program.py
│   └── ...
├── tasks/                     # Implementations of specific tasks
│   ├── backup_and_reboot.py
│   └── ...
├── schedules/                 # JSON files defining the schedules
│   └── full_schedule.json
└── statuses/                  # JSON files for storing the status of each job
    └── nas-monitor.json
