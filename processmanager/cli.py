#!/home/kyle/anaconda3/envs/pysystemenv/bin/python
import argparse
import json
import importlib
import os
import sys
import contextlib
import logging
from pathlib import Path
from tabulate import tabulate
from processmanager.core.utils import load_schedules
from .main import SCHEDULE_FILE_PATH
from .core.supervisor_manager import reload_supervisor

# Early disable asyncio logging.
asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.setLevel(logging.CRITICAL)
asyncio_logger.disabled = True


def list_status(schedule_filename):
    """Lists the status of configured programs and tasks in a neat, grouped table."""
    schedules, valid_hash = load_schedules(schedule_filename)

    
    print(f"\nSchedule Valid: {valid_hash}")


    # 1️⃣ Collect program- and task-rows separately
    program_rows = []
    task_rows    = []

    for job in schedules:
        typ        = job.get("type")
        name       = job.get("name", "")
        class_path = job.get("program_class", "") if typ == "program" else ""
        status     = ""

        if typ == "program":
            if not class_path:
                status = "No program_class provided"
            else:
                try:
                    mod_name, cls_name = class_path.rsplit(".", 1)
                    module = importlib.import_module(mod_name)
                    cls    = getattr(module, cls_name)
                    inst   = cls(job)

                    if hasattr(inst, "custom_monitor"):
                        logging.disable(logging.CRITICAL + 1)
                        with open(os.devnull, "w") as devnull, \
                             contextlib.redirect_stdout(devnull), \
                             contextlib.redirect_stderr(devnull):
                            is_stopped = inst.custom_monitor()
                        logging.disable(logging.NOTSET)
                        status = "stopped" if is_stopped else "running"
                    else:
                        status = "unknown (no custom_monitor)"
                except Exception as e:
                    status = f"ERROR: {e}"
            program_rows.append([name, class_path, status])

        elif typ == "task":
            status = "(task status N/A)"
            # leave class_path blank for tasks
            task_rows.append([name, "", status])

    # 2️⃣ Define headers
    headers = ["Name", "Class Path", "Status"]

    # 3️⃣ Compute column widths for our separator
    #    We need the max width of each column across all rows + headers
    all_rows = program_rows + task_rows
    col_widths = []
    for col_idx in range(len(headers)):
        max_w = len(headers[col_idx])
        for row in all_rows:
            max_w = max(max_w, len(row[col_idx]))
        col_widths.append(max_w)

    # 4️⃣ Build a “separator” row of box-drawing dashes
    sep_row = ["─" * w for w in col_widths]

    # 5️⃣ Stitch everything together
    combined = []
    if program_rows:
        combined.extend(program_rows)
    # insert separator only if both groups exist
    if program_rows and task_rows:
        combined.append(sep_row)
    if task_rows:
        combined.extend(task_rows)

    # 6️⃣ Print via tabulate
    print(tabulate(combined, headers=headers, tablefmt="rounded_outline"))


def stop_program(program_name, schedule_filename):
    """
    Finds the schedule for a given program, instantiates its class,
    calls its stop() method, and updates its status file to set disable_restart = True.
    """
    schedules, valid_hash = load_schedules(schedule_filename)
    program_config = None
    for job in schedules:
        if job.get("type") == "program" and job.get("name") == program_name:
            program_config = job
            break
    if not program_config:
        print(f"No schedule found for program '{program_name}'")
        return

    class_path = program_config.get("program_class")
    if not class_path:
        print(f"No program_class provided for '{program_name}'")
        return

    try:
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        # Instantiate the program using its config.
        program_instance = cls(program_config)
        # Call its stop() method.
        # (This assumes the stop() method will kill the running process
        #  by reading the stored PID from its status file.)

        # logging.disable(logging.CRITICAL + 1)
        # with open(os.devnull, "w") as devnull:
        #     with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
        stop_result = program_instance.stop()
        # logging.disable(logging.NOTSET)

        # Update the status file to include disable_restart.
        status_file = program_config.get("status_file", f"statuses/{program_name}.json")
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                status_data = json.load(f)
        else:
            status_data = {}
        status_data["disable_restart"] = True
        with open(status_file, "w") as f:
            json.dump(status_data, f)
        print(f"Program '{program_name}' stopped and disable_restart set to True.")
    except Exception as e:
        print(f"Error stopping program '{program_name}': {e}")

def start_program(program_name, schedule_filename):
    """
    Finds the schedule for a given program, instantiates its class,
    calls its start() method, and updates its status file to set disable_restart = False.
    """
    schedules, valid_hash = load_schedules(schedule_filename)
    program_config = None
    for job in schedules:
        if job.get("type") == "program" and job.get("name") == program_name:
            program_config = job
            break
    if not program_config:
        print(f"No schedule found for program '{program_name}'")
        return

    class_path = program_config.get("program_class")
    if not class_path:
        print(f"No program_class provided for '{program_name}'")
        return

    try:
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        # Instantiate the program using its config.
        program_instance = cls(program_config)
        # Call its start() method.
        start_result = program_instance.start()
        # Update the status file to include disable_restart set to False.
        status_file = program_config.get("status_file", f"statuses/{program_name}.json")
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                status_data = json.load(f)
        else:
            status_data = {}
        status_data["disable_restart"] = False
        with open(status_file, "w") as f:
            json.dump(status_data, f)
        print(f"Program '{program_name}' started and disable_restart set to False.")
    except Exception as e:
        print(f"Error starting program '{program_name}': {e}")
        

        
def main():
    """Main entry point for the command-line script."""
    parser = argparse.ArgumentParser(description="Simple Process Manager CLI") # Added description
    parser.add_argument("command", choices=["list", "stop", "start", "reload"],
                        help="Command to perform: list program/task status, stop a program, or start a program.") # Added help
    parser.add_argument("program_name", nargs="?", default=None,
                        help="Name of the program for stop/start commands.") # Added help

    args = parser.parse_args()

    if args.command == "list":
        list_status(SCHEDULE_FILE_PATH)

    elif args.command == "stop":
        if args.program_name is None:
            print("Error: Please specify a program name to stop.") # Changed print to include Error

        else:
            stop_program(args.program_name, SCHEDULE_FILE_PATH)

    elif args.command == "start":
        if args.program_name is None:
            print("Error: Please specify a program name to start.") # Changed print to include Error

        else:
            start_program(args.program_name, SCHEDULE_FILE_PATH)

    elif args.command == "reload":
        reload_supervisor()


if __name__ == "__main__":
    main()