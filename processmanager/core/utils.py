import importlib
from datetime import datetime
import subprocess
import json
import hashlib
import os
from .logger_setup import get_logger
from pathlib import Path

# logger = logging.getLogger(__name__)


def load_json(filename):
    with open(filename, 'r') as f:
        return json.load(f)

        
def get_job_sched(job_name, type, schedule_file: Path) -> dict:

    schedules, _ = load_schedules(schedule_file)

    job_sched = None
    for schedule in schedules:
        if schedule.get("type") == type and schedule.get("name") == job_name:
            job_sched = schedule 
            break
    if not job_sched:
        raise ValueError(f"No schedule found for program '{job_name}'")
    
    return job_sched

        
def load_schedules(schedule_file: Path, write_hash=False):
    """Load schedules, validate or write a hash, and return (schedules, valid_hash)."""
    # logger.debug("Loading schedules")
    
    logger = get_logger("utils")

    try:
        with open(schedule_file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading schedules: {e}")
        return [], False

    schedules = data.get('schedules', [])

    # 1. Serialize in a stable way
    canonical = json.dumps(schedules, sort_keys=True, separators=(',', ':'))

    # 2. Compute SHA-256 hash
    digest = hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    # 3. Determine hash file path
    base, _ext = os.path.splitext(os.path.basename(schedule_file))
    hash_filename = f"{base}.hash"
    hash_path = os.path.join(os.path.dirname(schedule_file), hash_filename)

    # 4. Read existing hash (if any) and compare
    old_digest = None
    if os.path.exists(hash_path):
        try:
            with open(hash_path, 'r') as hf:
                old_digest = hf.read().strip()
        except Exception as e:
            logger.warning(f"Could not read existing hash file: {e}")

    valid_hash = (old_digest == digest) if old_digest is not None else False

    # 5. Optionally write out the new hash
    if write_hash:
        try:
            with open(hash_path, 'w') as hf:
                hf.write(digest)
            logger.debug(f"Wrote schedules hash to {hash_path}")
        except Exception as e:
            logger.error(f"Error writing hash file: {e}")

    return schedules, valid_hash

    
    
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
    logger = get_logger("utils")

    try:
        result = subprocess.run(['ps', '-e', '-o', 'pid,comm'], stdout=subprocess.PIPE, text=True)
        processes = result.stdout.splitlines()
        for line in processes:
            parts = line.split(None, 1)
            if len(parts) == 2:
                pid, command = parts
                if command == process_name:
                    logger.debug(f"Found process '{process_name}' with PID {pid}. Killing it...")
                    subprocess.run(['kill', '-9', pid])
                    logger.debug(f"Process '{process_name}' with PID {pid} has been killed.")
                    return
        logger.debug(f"Process '{process_name}' is not running.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
