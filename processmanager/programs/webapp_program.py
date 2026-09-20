from ..core.BaseProgram import BaseProgram
import os
import signal
import subprocess
import time
import urllib.request
from ..config import Config


class WebappProgram(BaseProgram):
    def __init__(self, schedule, config: Config):
        super().__init__(schedule, config)
        self.monitor_func = self.custom_monitor

    @BaseProgram.record_start
    def start(self):
        self.job_logger.debug(f"Starting webapp: {self.name}")
        try:
            command = (
                f"exec /home/kyle/miniconda3/envs/sctrading/bin/python "
                f"/home/kyle/projects/sctrading/scripts/webapp.py "
                f">> {self.log_file} 2>&1"
            )
            proc = subprocess.Popen(
                ["bash", "-c", command],
                preexec_fn=os.setsid,
            )
            self.job_logger.info(f"Started webapp '{self.name}' with PID {proc.pid}")
            return proc.pid
        except Exception as e:
            self.job_logger.error(f"Failed to start webapp '{self.name}': {e}")
            return None

    @BaseProgram.record_stop
    def stop(self):
        self.job_logger.debug(f"Stopping webapp: {self.name}")
        if self.pid:
            try:
                os.killpg(os.getpgid(self.pid), signal.SIGINT)
                time.sleep(3)
                self.job_logger.info("Webapp terminated.")
            except Exception as e:
                self.job_logger.error(f"Error stopping webapp '{self.name}' (pid={self.pid}): {e}")
        else:
            self.job_logger.warning(f"Webapp '{self.name}' was not running.")

    def custom_monitor(self):
        try:
            with urllib.request.urlopen("http://localhost:5000/api/portfolio", timeout=5) as r:
                if r.status == 200:
                    self.job_logger.debug("Webapp health check passed.")
                    return "SUCCESS"
        except Exception as e:
            self.job_logger.error(f"Webapp health check failed: {e}")
            return "RESTART"
        return "RESTART"
