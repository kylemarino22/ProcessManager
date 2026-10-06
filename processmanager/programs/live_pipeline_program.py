from __future__ import annotations

import subprocess

from datetime import datetime

from ..config import Config
from ..core.BaseProgram import BaseProgram

COMPOSE_FILE    = "/home/kyle/projects/sctrading/docker-compose.yml"
COMPOSE_PROJECT = "sctrading"
SERVICES        = ["feed_handler", "inference_engine", "execution_engine"]
EXPECTED_NAMES  = {f"{COMPOSE_PROJECT}-{s}-1" for s in SERVICES}


class LivePipelineProgram(BaseProgram):
    """
    Manages the sctrading compose project.

    Unlike the other programs there is no long-lived child process: `up -d`
    exits once the containers are running, so the project is the handle and
    `docker ps` is the health check. start() is a cold start (stop then up)
    so 3:50 AM ET always reloads EOD even if leftover containers are up.
    stop() is the 8:00 PM ET teardown. Both use `stop`, not `down`, so the
    containers and their `docker logs` survive until the next recreate.
    """

    def __init__(self, schedule, config: Config):
        super().__init__(schedule, config)
        self.monitor_func = self.custom_monitor
        self.is_down = True
        self.pid = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _project_containers(self, running_only: bool = True) -> set[str] | None:
        """Compose container names, or None if docker could not be reached."""
        command = ["docker", "ps"] if running_only else ["docker", "ps", "-a"]
        command += [
            "--filter", f"label=com.docker.compose.project={COMPOSE_PROJECT}",
            "--format", "{{.Names}}",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.job_logger.error(
                    f"docker ps returned {result.returncode}: {result.stderr.strip()}"
                )
                return None
            return {line.strip() for line in result.stdout.splitlines() if line.strip()}
        except Exception as e:
            self.job_logger.error(f"docker ps failed: {e}")
            return None

    def _record_running(self):
        """Mark the job running without a pid, preserving the rest of the status."""
        status = self.read_status() or {}
        status.update({
            "pid": 0,
            "time_started": datetime.now().isoformat(sep=' ', timespec='seconds'),
            "num_retries": self.retries,
            "status": "running",
        })
        self.write_status(status)

    def should_stop_outside_schedule(self, current_status):
        if current_status.get("status") == "running":
            return True
        return bool(self._project_containers())

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    def _compose(self, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "compose", "-f", COMPOSE_FILE, "-p", COMPOSE_PROJECT, *args],
            timeout=timeout, capture_output=True, text=True,
        )

    def start(self):
        self.log_file = self._get_program_log_path()
        self.job_logger.info(f"Starting live pipeline: {self.name}")
        try:
            stop = self._compose("stop")
            if stop.returncode != 0:
                self.job_logger.warning(
                    f"docker compose stop returned {stop.returncode}: {stop.stderr.strip()}"
                )
            result = self._compose("up", "-d")
            if result.returncode == 0:
                self.job_logger.info("docker compose up -d complete.")
                self._record_running()
            else:
                self.job_logger.error(
                    f"docker compose up -d returned {result.returncode}: {result.stderr.strip()}"
                )
        except Exception as e:
            self.job_logger.error(f"Failed to start live pipeline: {e}")

    @BaseProgram.record_stop
    def stop(self):
        self.job_logger.info(f"Stopping live pipeline: {self.name}")
        self.is_down = True
        try:
            result = self._compose("stop", timeout=60)
            if result.returncode == 0:
                self.job_logger.info("docker compose stop complete.")
            else:
                self.job_logger.warning(
                    f"docker compose stop returned {result.returncode}: {result.stderr.strip()}"
                )
        except Exception as e:
            self.job_logger.error(f"docker compose stop failed: {e}")

    # ------------------------------------------------------------------
    # Monitor
    # ------------------------------------------------------------------

    def custom_monitor(self):
        running = self._project_containers()
        if running is None:
            self.job_logger.warning("Could not reach docker; skipping this check.")
            return "SUCCESS"

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
