import subprocess
import threading
import time
import importlib
from logger_setup import setup_process_manager_logger

class Program:
    def __init__(self, config):
        self.name = config.get('name')
        self.command = config.get('command')
        self.status_logger = setup_process_manager_logger()
        self.output_file = config.get('output_file', f"{self.name}_output.log")
        self.keep_alive = config.get('keep_alive', False)
        self.check_alive_freq = self.parse_frequency(config.get('check_alive_freq', '1 m'))
        self.max_retries = config.get('max_retries', 0)
        self.retries = 0
        self.process = None

        # Load custom monitor function if provided.
        monitor_func_str = config.get('monitor_func')
        if monitor_func_str:
            try:
                module_name, func_name = monitor_func_str.rsplit('.', 1)
                module = importlib.import_module(module_name)
                self.monitor_func = getattr(module, func_name)
            except Exception as e:
                self.status_logger.error(f"Error loading monitor function '{monitor_func_str}': {e}")
                self.monitor_func = None
        else:
            self.monitor_func = None

    def parse_frequency(self, freq_str):
        try:
            value, unit = freq_str.split()
            value = int(value)
            if unit.lower().startswith('m'):
                return value * 60
            elif unit.lower().startswith('s'):
                return value
            elif unit.lower().startswith('h'):
                return value * 3600
        except Exception as e:
            self.status_logger.error(f"Error parsing frequency '{freq_str}': {e}")
        return 60  # default interval

    def start(self):
        self.status_logger.debug("Starting program")
        try:
            # Redirect stdout and stderr to the output file.
            with open(self.output_file, 'a') as outfile:
                self.process = subprocess.Popen(self.command, stdout=outfile, stderr=subprocess.STDOUT)
            self.status_logger.info(f"Started program '{self.name}' with PID {self.process.pid}")
            if self.keep_alive:
                threading.Thread(target=self.monitor, daemon=True).start()
        except Exception as e:
            self.status_logger.error(f"Failed to start program '{self.name}': {e}")

    def monitor(self):
        while True:
            time.sleep(self.check_alive_freq)
            # Use custom monitor function if available; otherwise, use default check.
            if self.monitor_func:
                restart_needed = self.monitor_func(self)
            else:
                restart_needed = (self.process.poll() is not None)
            if restart_needed:
                self.status_logger.warning(f"Program '{self.name}' needs restart. Attempting restart.")
                self.retries += 1
                if self.retries <= self.max_retries:
                    self.start()
                else:
                    self.status_logger.error(f"Max retries reached for '{self.name}'. No further attempts will be made.")
                    break
