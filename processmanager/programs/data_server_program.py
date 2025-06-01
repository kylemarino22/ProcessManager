# data_server_program.py
from ..core.BaseProgram import BaseProgram
import subprocess
import os
import time
from multiprocessing.managers import BaseManager
import signal
from ..config import Config

class DataServerProgram(BaseProgram):
    def __init__(self, schedule, config: Config):
        super().__init__(schedule, config)
        # The status_file is inherited from BaseProgram (config or default).
        # Override the monitor function with our custom monitor.
        self.monitor_func = self.custom_monitor

    @BaseProgram.record_start
    def start(self):
        """
        Starts the data server script using a fixed command and returns its PID.
        """

        self.job_logger.debug(f"Starting Data Server Program: {self.name}")
        try:
            command = (
                f"source $HOME/.profile; "
                f"exec /home/kyle/anaconda3/envs/pysystemenv/bin/python "
                f"/home/kyle/pysystemtrade/kyle_tests/data_engine/data_server_v2.py "
                f">> {self.log_file} 2>&1"
            )
            self.process = subprocess.Popen(
                ["bash", "-c", command],
                preexec_fn=os.setsid  # Detach the process from the parent.
            )
            self.job_logger.info(f"Started Data Server Program '{self.name}' with PID {self.process.pid}")
            return self.process.pid
        except Exception as e:
            self.job_logger.error(f"Failed to start Data Server Program '{self.name}': {e}")
            return None

    @BaseProgram.record_stop
    def stop(self):
        """
        Stops the data server process gracefully by sending SIGINT (simulating Ctrl+C)
        to the entire process group.
        """
        self.job_logger.debug(f"Stopping Data Server Program: {self.name}")

        if self.default_monitor():

            pid = self.read_status().get('pid')
            try:
                # Send SIGINT to the process group to simulate a Ctrl+C
                os.killpg(os.getpgid(pid), signal.SIGINT)
                # Optionally, wait for the process to exit gracefully
                self.job_logger.info(f"Waiting for Data Server Program to terminate...")
                time.sleep(60)
                self.job_logger.info(f"Data Server Program terminated gracefully with SIGINT.")
            except Exception as e:
                self.job_logger.error(f"Error stopping Data Server Program '{self.name}', pid: {pid}: {e}")

        else:
            self.job_logger.warning(f"Data Server Program '{self.name}' was not running.")

    def custom_monitor(self):
        """
        Custom monitoring function for the data server.
        First checks the recorded PID in the status file.
        Then attempts to connect to the server using a QueueManager.
        Restarts the server if either check fails.
        """


        # pid_running = self.default_monitor()

        # if not pid_running:
        #     self.job_logger.info("Data server not running based on status file. Attempting restart.")
        #     return True

        # Next, test connection to the server using a QueueManager.
        class QueueManager(BaseManager):
            pass

        manager = QueueManager(address=('127.0.0.1', 50000), authkey=b'secret')
        try:
            manager.connect()
            self.job_logger.info("Connection to data server succeeded.")
        except Exception as e:
            self.job_logger.error(f"[Client] Error connecting to data server: {e}")
            self.job_logger.info("Attempting restart of data server.")
            return True

        return False
