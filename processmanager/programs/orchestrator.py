# orchestrator_program.py
from ..core.BaseProgram import BaseProgram
import subprocess
import os
import time
import signal
from ..config import Config

class OrchestratorProgram(BaseProgram):
    """
    Program class for managing the Futures System data pipeline orchestrator.

    This class handles the starting, stopping, and monitoring of the main
    orchestrator script, making it compatible with the process manager.
    """
    def __init__(self, schedule, config: Config):
        """
        Initializes the OrchestratorProgram.

        Args:
            schedule (dict): The schedule configuration for this program.
            config (Config): The global configuration object.
        """
        super().__init__(schedule, config)
        # This program will use the default PID-based monitor from BaseProgram.
        # No custom monitor is needed as it's a simple script, not a server.

    @BaseProgram.record_start
    def start(self):
        """
        Starts the orchestrator script in a new process group and returns its PID.
        Logs are redirected to the file specified in the configuration.
        """
        self.job_logger.debug(f"Starting Orchestrator Program: {self.name}")
        try:
            # Define the paths for the python executable and the orchestrator script
            python_executable = "/home/kyle/anaconda3/envs/futures_env/bin/python"
            script_path = "/home/kyle/projects/FuturesSystem/src/futures_system/price_pipeline/orchestrator.py"

            # Construct the shell command.
            # 'exec' replaces the shell process with the python process.
            # '>>' appends stdout and '2>&1' redirects stderr to stdout.
            command = (
                f"exec {python_executable} {script_path} "
                f">> {self.log_file} 2>&1"
            )

            # Use Popen to run the command in a new, detached process session.
            # This prevents it from being killed if the parent script exits.
            self.process = subprocess.Popen(
                ["bash", "-c", command],
                preexec_fn=os.setsid
            )
            self.job_logger.info(f"Started Orchestrator Program '{self.name}' with PID {self.process.pid}")
            return self.process.pid
        except Exception as e:
            self.job_logger.error(f"Failed to start Orchestrator Program '{self.name}': {e}")
            return None

    @BaseProgram.record_stop
    def stop(self):
        """
        Stops the orchestrator process gracefully.

        It first sends SIGINT (Ctrl+C) to the process group. If the process
        does not terminate after a short wait, it sends SIGKILL to force it.
        """
        self.job_logger.debug(f"Stopping Orchestrator Program: {self.name}")

        # Use the default monitor to check if the process is running
        if not self.default_monitor():
            self.job_logger.warning(f"Orchestrator Program '{self.name}' was not running.")
            return

        pid = self.read_status().get('pid')
        if not pid:
            self.job_logger.error(f"Could not find PID for program '{self.name}' in status file.")
            return

        try:
            # Get the process group ID (should be same as PID due to os.setsid)
            pgid = os.getpgid(pid)

            # 1. Attempt graceful shutdown with SIGINT
            self.job_logger.info(f"Sending SIGINT to process group {pgid} for orchestrator '{self.name}'...")
            os.killpg(pgid, signal.SIGINT)

            # Wait for a moment to allow for graceful exit
            time.sleep(5)

            # 2. Check if it's still running and force stop if necessary
            if self.default_monitor():
                self.job_logger.warning(f"Orchestrator '{self.name}' did not terminate with SIGINT. Sending SIGKILL...")
                os.killpg(pgid, signal.SIGKILL)
                self.job_logger.info(f"Orchestrator '{self.name}' terminated with SIGKILL.")
            else:
                self.job_logger.info(f"Orchestrator '{self.name}' terminated gracefully.")

        except ProcessLookupError:
            self.job_logger.info(f"Process with PID {pid} not found. Already stopped.")
        except Exception as e:
            self.job_logger.error(f"An error occurred while stopping program '{self.name}' (PID: {pid}): {e}")
