import subprocess
import threading
import time
from logger_setup import setup_logger

class Program:
    def __init__(self, config):
        self.name = config.get('name')
        self.command = config.get('command')
        self.output_file = config.get('output_file')
        self.keep_alive = config.get('keep_alive', False)
        self.check_alive_freq = self.parse_frequency(config.get('check_alive_freq', '1 m'))
        self.max_retries = config.get('max_retries', 0)
        self.retries = 0
        self.process = None
        self.logger = setup_logger(self.name, f"{self.name}.log")

    def parse_frequency(self, freq_str):
        """
        Parse a frequency string (e.g., '1 m') and return the interval in seconds.
        """
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
            self.logger.error(f"Error parsing frequency '{freq_str}': {e}")
        return 60  # default interval

    def start(self):
        self.logger.debug("Starting program")
        try:
            # If an output file is defined, redirect the output.
            outfile = open(self.output_file, 'a') if self.output_file else None
            self.process = subprocess.Popen(self.command, stdout=outfile, stderr=subprocess.STDOUT)
            self.logger.info(f"Started program '{self.name}' with PID {self.process.pid}")
            if self.keep_alive:
                threading.Thread(target=self.monitor, daemon=True).start()
        except Exception as e:
            self.logger.error(f"Failed to start program '{self.name}': {e}")

    def monitor(self):
        """
        Periodically check if the process is alive. If it is not, attempt to restart it.
        """
        while True:
            time.sleep(self.check_alive_freq)
            if self.process.poll() is not None:  # Process has ended
                self.logger.warning(f"Program '{self.name}' is not running. Attempting restart.")
                self.retries += 1
                if self.retries <= self.max_retries:
                    self.start()
                else:
                    self.logger.error(f"Max retries reached for '{self.name}'. No further attempts will be made.")
                    break
