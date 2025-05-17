# nas_program.py
from ..core.program_base import BaseProgram
import subprocess
import os

class NASProgram(BaseProgram):
    def __init__(self, config):
        super().__init__(config)
        # Override the monitor function with our custom monitor.
        self.monitor_func = self.custom_monitor

    @BaseProgram.record_start
    def start(self):
        """
        Starts the NAS mounting process.
        It first pings readynas.local to trigger DNS resolution,
        then mounts the NFS share from readynas.local:/data/market_data to /mnt/nas.
        Returns the PID of the mounting process.
        """
        # self.status_logger.error("NAS Program does not have start function due to mount requiring sudo.")

        self.status_logger.debug(f"Starting NAS Program: {self.name}")
        try:
            # Step 1: Check if readynas.local resolves and is reachable
            ping_command = ["ping", "-c", "1", "-W", "3", "readynas.local"]  # -W is timeout in seconds (Linux)
            ping_result = subprocess.run(ping_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            if ping_result.returncode != 0:
                self.status_logger.error(f"NAS ping failed: {ping_result.stderr.decode().strip()}")
                return None

            # Step 2: Mount in a detached process
            self.process = subprocess.Popen(
                ["mount", "/mnt/nas"],  # Use sudo if needed and configured with NOPASSWD
                stdout=open(self.output_file, "a"),
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid
            )
            self.status_logger.info(f"Started NAS Program '{self.name}' with PID {self.process.pid}")
            return self.process.pid

        except subprocess.TimeoutExpired:
            self.status_logger.error("Ping to NAS timed out.")
            return None
        except Exception as e:
            self.status_logger.error(f"Failed to start NAS Program '{self.name}': {e}")
            return None

    def stop(self):
        """
        NAS Program does not require a stop function.
        """
        self.status_logger.info(f"NAS Program '{self.name}' stop() called. No action taken as stop is not needed.")

    def custom_monitor(self):
        """
        Custom monitoring function for the NAS mount.
        Lists the contents of /mnt/nas and checks that there are at least two directories.
        If fewer than two directories are found, it attempts to re-mount by calling start().
        Returns True if a restart was triggered, False otherwise.
        """
        try:
            items = os.listdir("/mnt/nas")
            # Filter to include only directories.
            dirs = [item for item in items if os.path.isdir(os.path.join("/mnt/nas", item))]
            self.status_logger.info(f"NASProgram.custom_monitor: Directories found in /mnt/nas: {dirs}")
            if len(dirs) < 2:
                self.status_logger.warning("NAS mount check failed: fewer than 2 directories found. Attempting restart.")
                return True
            else:
                self.status_logger.info("NAS mount appears healthy.")
                return False
        except Exception as e:
            self.status_logger.error(f"Error checking NAS mount: {e}")
            return True
