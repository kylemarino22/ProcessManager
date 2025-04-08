import importlib
from datetime import datetime
import subprocess

def load_json(filename):
    import json
    with open(filename, 'r') as f:
        return json.load(f)
    
def dynamic_import(func_path):
    """
    Dynamically import a function from a module.
    For example, given "path.to.module.func_name", it returns the function object.
    """
    module_path, func_name = func_path.rsplit('.', 1)
    module = importlib.import_module(module_path)
    return getattr(module, func_name)

def check_ib_valid_time():
    """
    Check if the current time is outside the valid IB operating window.
    Returns True if the current time is before the start time or after the end time.
    """
    start_time = datetime.strptime("20:30", "%H:%M").time()  # 20:20
    end_time = datetime.strptime("21:30", "%H:%M").time()    # 21:45
    current_time = datetime.now().time()
    return start_time >= current_time or current_time >= end_time

def list_and_kill_process(process_name):
    """
    Lists running processes and kills any process matching the given name.
    """
    try:
        result = subprocess.run(['ps', '-e', '-o', 'pid,comm'], stdout=subprocess.PIPE, text=True)
        processes = result.stdout.splitlines()
        for line in processes:
            parts = line.split(None, 1)
            if len(parts) == 2:
                pid, command = parts
                if command == process_name:
                    print(f"Found process '{process_name}' with PID {pid}. Killing it...")
                    subprocess.run(['kill', '-9', pid])
                    print(f"Process '{process_name}' with PID {pid} has been killed.")
                    return
        print(f"Process '{process_name}' is not running.")
    except Exception as e:
        print(f"An error occurred: {e}")
