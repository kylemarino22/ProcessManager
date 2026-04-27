from __future__ import annotations

import subprocess

from ..config import Config
from ..core.BaseProgram import BaseProgram

COMPOSE_FILE    = "/home/kyle/projects/sctrading/docker-compose.yml"
COMPOSE_PROJECT = "sctrading"
SERVICES        = ["feed_handler", "inference_engine", "execution_engine"]
EXPECTED_NAMES  = {f"{COMPOSE_PROJECT}-{s}-1" for s in SERVICES}


class LivePipelineProgram(BaseProgram):

    def __init__(self, schedule, config: Config):
        super().__init__(schedule, config)
        self.monitor_func = self.custom_monitor
        self.is_down = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _running_containers(self) -> set[str]:
        try:
            result = subprocess.run(
                ["docker", "ps",
                 "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}",
                 "--filter", "status=running"],
                capture_output=True, text=True, timeout=10,
            )
            return {
                line.split()[-1]
                for line in result.stdout.splitlines()[1:]
                if line.strip()
            }
        except Exception as e:
            self.job_logger.error(f"docker ps failed: {e}")
            return set()

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    @BaseProgram.record_start
    def start(self):
        self.job_logger.info(f"Starting live pipeline: {self.name}")
        try:
            proc = subprocess.Popen(
                ["docker", "compose", "-f", COMPOSE_FILE, "-p", COMPOSE_PROJECT, "up", "-d"],
            )
            proc.wait(timeout=60)
            if proc.returncode == 0:
                self.job_logger.info("docker compose up -d succeeded.")
                return proc.pid
            else:
                self.job_logger.error(f"docker compose up -d failed (exit {proc.returncode}).")
                return None
        except Exception as e:
            self.job_logger.error(f"Failed to start live pipeline: {e}")
            return None

    @BaseProgram.record_stop
    def stop(self):
        self.job_logger.info(f"Stopping live pipeline: {self.name}")
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", COMPOSE_FILE, "-p", COMPOSE_PROJECT, "down"],
                timeout=60, capture_output=True, text=True,
            )
            if result.returncode == 0:
                self.job_logger.info("docker compose down complete.")
            else:
                self.job_logger.warning(
                    f"docker compose down returned {result.returncode}: {result.stderr.strip()}"
                )
        except Exception as e:
            self.job_logger.error(f"docker compose down failed: {e}")

    # ------------------------------------------------------------------
    # Monitor
    # ------------------------------------------------------------------

    def custom_monitor(self):
        running = self._running_containers()
        missing = EXPECTED_NAMES - running
        if missing:
            if self.within_schedule():
                self.job_logger.warning(f"Containers not running: {missing}")
            if self.is_down:
                return "SILENT_RESTART"
            self.is_down = True
            return "RESTART"

        self.job_logger.debug("All containers Up.")
        if self.is_down:
            self.is_down = False
            return "NOTIFY_SUCCESS"
        return "SUCCESS"
