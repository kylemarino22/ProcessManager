# nas_program.py
from program_base import BaseProgram
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
        self.status_logger.debug(f"Starting NAS Program: {self.name}")
        try:
            # Combine the two commands in one bash invocation.
            command = ("ping -c 4 readynas.local && "
                       "sudo mount -t nfs readynas.local:/data/market_data /mnt/nas")
            self.process = subprocess.Popen(
                ["bash", "-c", command],
                stdout=open(self.output_file, "a"),
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid  # Detach the process from the parent.
            )
            self.status_logger.info(f"Started NAS Program '{self.name}' with PID {self.process.pid}")
            return self.process.pid
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
