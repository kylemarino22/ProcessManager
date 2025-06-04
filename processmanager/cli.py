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
from processmanager.core.logger_setup import setup_pm_logging, get_logger
from processmanager.core.supervisor_manager import reload_supervisor
from processmanager.config import Config, config # Import class def and object
from processmanager.core.Task import Task

def list_status(config: Config):
    """Lists the status of configured programs and tasks in three separate tables."""
    schedules, valid_hash = load_schedules(config.schedule_file)
    pm_logger = get_logger("process_manager")


    # ── 1) Schedule Valid table ───────────────────────────────────────────────
    field_table = [["Schedule Valid", str(valid_hash)]]
    print(tabulate(field_table,
                   tablefmt="rounded_outline"))
    print()  # blank line between tables

    # ── 2) Programs table ────────────────────────────────────────────────────
    prog_rows = []
    for schedule in schedules:
        
        if schedule.get("type") != "program":
            continue

        name       = schedule.get("name", "")
        class_path = schedule.get("program_class", "")
        start_time = None
        last_checkup = None
        disable_restart = None

        try:
            # split into full module path + class
            mod_name, cls_name = class_path.rsplit(".", 1)

            # derive the "short" module (last segment) + class
            short_mod = mod_name.split(".")[-1]
            short_path = f"{short_mod}.{cls_name}"


            module = importlib.import_module(mod_name)
            cls    = getattr(module, cls_name)
            prog   = cls(schedule, config)

            pm_logger.debug(f"Program type: {type(prog)}, instance: {prog}")

            # Run monitor func for program to check status
            if hasattr(prog, "custom_monitor"):
                # silence all output
                # pm_logger.info(f"Running monitor for program '{name}'")
                print(f"Running {name} monitor", end="\r", flush=True)
                # logging.disable(logging.CRITICAL + 1)

                is_stopped = prog.custom_monitor()

                # logging.disable(logging.NOTSET)
                program_status = "stopped" if is_stopped else "running"
                pm_logger.debug(f"Program '{name}' status: {program_status}")
            else:
                program_status = "unknown (no custom_monitor)"
            

            status_dict = prog.read_status() 

            start_time      = status_dict.get('time_started')
            last_checkup    = status_dict.get('last_checkup')
            disable_restart = status_dict.get('disable_restart', False)

        except Exception as e:
            print(f"Error: {e}")

        # Load in status dict
        prog_rows.append([name, short_path, program_status, 
                          start_time, last_checkup, disable_restart])

    print(" " * 30, end="\r")

    print(tabulate(prog_rows,
                   headers=["Name", "Class Path", "Status", "Started", "Last Checkup", "Disable Restart"],
                   tablefmt="rounded_outline"))
    print()

    # ── 3) Tasks table ───────────────────────────────────────────────────────
    task_rows = []
    for schedule in schedules:
        if schedule.get("type") != "task":
            continue
        name      = schedule.get("name", "")
        func_path = schedule.get("func", "")
        start     = schedule.get("start", "")
        freq      = schedule.get("freq", "")

        # derive the "short" module (last segment) + class
        mod_name, cls_name = func_path.rsplit(".", 1)
        short_mod = mod_name.split(".")[-1]
        short_path = f"{short_mod}.{cls_name}"

        # if the function path begins with "processmanager", use the short version
        display_path = short_path if func_path.startswith("processmanager") else func_path

        task = Task(schedule, config)
        status_dict = task.read_status()
        last_ran = status_dict.get("last-ran", "")
        last_err = status_dict.get("last-err", "")

        task_rows.append([name, display_path, start, freq, last_ran, last_err])

    print(tabulate(
        task_rows,
        headers=["Name", "Function Path", "Start", "Freq", "Last Ran", "Last Err"],
        tablefmt="rounded_outline"
    ))



def stop_program(program_name, config: Config):
    """
    Finds the schedule for a given program, instantiates its class,
    calls its stop() method, and updates its status file to set disable_restart = True.
    """
    pm_logger = get_logger("process_manager")

    schedules, valid_hash = load_schedules(config.schedule_file)
    prog_sched = None
    for schedule in schedules:
        if schedule.get("type") == "program" and schedule.get("name") == program_name:
            prog_sched = schedule 
            break
    if not prog_sched:
        pm_logger.error(f"No schedule found for program '{program_name}'")
        return

    class_path = prog_sched.get("program_class")
    if not class_path:
        pm_logger.error(f"No program_class provided for '{program_name}'")
        return

    try:
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        # Instantiate the program using its config.
        prog = cls(prog_sched, config)

        prog.stop()

        prog.disable_restart(True)

        pm_logger.info(f"Program '{program_name}' stopped and disable_restart set to True.")
    except Exception as e:
        pm_logger.error(f"Error stopping program '{program_name}': {e}")

def start_program(program_name, config: Config):
    """
    Finds the schedule for a given program, instantiates its class,
    calls its start() method, and updates its status file to set disable_restart = False.
    """

    pm_logger = get_logger("process_manager")

    schedules, _ = load_schedules(config.schedule_file)
    prog_sched = None
    for schedule in schedules:
        if schedule.get("type") == "program" and schedule.get("name") == program_name:
            prog_sched = schedule 
            break

    if not prog_sched:
        pm_logger.error(f"No schedule found for program '{program_name}'")
        return

    class_path = prog_sched.get("program_class")
    if not class_path:
        pm_logger.error(f"No program_class provided for '{program_name}'")
        return

    try:
        module_name, class_name = class_path.rsplit(".", 1)
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        prog = cls(prog_sched, config)

        # Call program start, discard result
        prog.start()

        prog.disable_restart(False)

        pm_logger.debug(f"Program '{program_name}' started and disable restart set to False.")
    except Exception as e:
        pm_logger.debug(f"Error starting program '{program_name}': {e}")
        

        
def main():
    """Main entry point for the command-line script."""
    parser = argparse.ArgumentParser(description="Simple Process Manager CLI")
    parser.add_argument("command", choices=["list", "stop", "start", "reload"],
                        help="Command to perform: list program/task status, stop a program, or start a program.")
    parser.add_argument("program_name", nargs="?", default=None,
                        help="Name of the program for stop/start commands.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable verbose (debug) logging.")

    args = parser.parse_args()

    # Set logging level based on verbose flag
    level = logging.DEBUG if args.verbose else logging.INFO
    setup_pm_logging(config.log_dir, level, mark_restart=False)
    # pm_logger = setup_logger("process_manager", config.log_dir, level=level)
    # pm_logger.info("Starting process manager CLI")

    if args.command == "list":
        list_status(config)

    elif args.command == "stop":
        if args.program_name is None:
            print("Error: Please specify a program name to stop.")
        else:
            stop_program(args.program_name, config)

    elif args.command == "start":
        if args.program_name is None:
            print("Error: Please specify a program name to start.")
        else:
            start_program(args.program_name, config)

    elif args.command == "reload":
        reload_supervisor()


if __name__ == "__main__":
    main()