#!/home/kyle/anaconda3/envs/pysystemenv/bin/python
import argparse
import json
import importlib
import os
import sys
import contextlib
import logging

# Early disable asyncio logging.
asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.setLevel(logging.CRITICAL)
asyncio_logger.disabled = True

programs_dir = "/home/kyle/ProcessManager/programs"

if programs_dir not in sys.path:
    sys.path.insert(0, programs_dir)

def load_schedules(file_path="schedules/full_schedule.json"):
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
            return data.get("schedules", [])
    except Exception as e:
        print(f"Error loading schedules: {e}")
        return []

def list_status():
    schedules = load_schedules()
    print("Programs:")
    for job in schedules:
        if job.get("type") != "program":
            continue
        name = job.get("name")
        class_path = job.get("program_class")
        if not class_path:
            print(f"  {name}: No program_class provided")
            continue

        try:
            module_name, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            # Instantiate the program using its config.
            program_instance = cls(job)
            # Call the custom_monitor function without printing any output.
            if hasattr(program_instance, "custom_monitor"):
                logging.disable(logging.CRITICAL + 1)

                with open(os.devnull, "w") as devnull:
                    with contextlib.redirect_stdout(devnull), contextlib.redirect_stderr(devnull):
                        monitor_status = program_instance.custom_monitor()
                logging.disable(logging.NOTSET)

                status_str = "stopped" if monitor_status else "running"
            else:
                status_str = "unknown (custom_monitor not implemented)"
            print(f"  {name} ({class_path}): {status_str}")
        except Exception as e:
            print(f"Error processing program '{name}' with class '{class_path}': {e}")

    print("\nTasks:")
    for job in schedules:
        if job.get("type") != "task":
            continue
        name = job.get("name")
        print(f"  {name}: (task status not implemented)")

def stop_program(program_name):
    """
    Finds the schedule for a given program, instantiates its class,
    calls its stop() method, and updates its status file to set disable_restart = True.
    """
    schedules = load_schedules()
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

def start_program(program_name):
    """
    Finds the schedule for a given program, instantiates its class,
    calls its start() method, and updates its status file to set disable_restart = False.
    """
    schedules = load_schedules()
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["list", "stop", "start"])
    parser.add_argument("program_name", nargs="?", default=None, help="Name of the program for stop command")
    args = parser.parse_args()

    if args.command == "list":
        list_status()
    elif args.command == "stop":
        if args.program_name is None:
            print("Please specify a program name to stop.")
        else:
            stop_program(args.program_name)
    elif args.command == "start":
        if args.program_name is None:
            print("Please specify a program name to start.")
        else:
            start_program(args.program_name)