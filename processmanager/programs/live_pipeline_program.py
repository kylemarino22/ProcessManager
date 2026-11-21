from __future__ import annotations

import smtplib
import subprocess

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ..config import Config
from ..core.BaseProgram import BaseProgram
from ..core.emailing import send_mail_msg

COMPOSE_FILE    = "/home/kyle/projects/sctrading/docker-compose.yml"
COMPOSE_PROJECT = "sctrading"
SERVICES        = ["feed_handler", "inference_engine", "execution_engine"]
EXPECTED_NAMES  = {f"{COMPOSE_PROJECT}-{s}-1" for s in SERVICES}
ET              = ZoneInfo("America/New_York")
# The engines fail hard (sctrading agents.md): a container that exits during the session is
# restarted with the whole stack at most this many times; then the stack stays down.
MAX_SESSION_RESTARTS = 3
LOG_TAIL_LINES  = 40


class LivePipelineProgram(BaseProgram):
    """
    Manages the sctrading compose project.

    Unlike the other programs there is no long-lived child process: `up -d`
    exits once the containers are running, so the project is the handle and
    `docker ps` is the health check. start() is a cold start (stop then up)
    so 3:50 AM ET always reloads EOD even if leftover containers are up.
    stop() is the 8:00 PM ET teardown. Both use `stop`, not `down`, so the
    containers and their `docker logs` survive until the next recreate.

    The containers have no Docker restart policy. A container that exits during
    the session (it finished today, ET) is a failure: the monitor emails its exit
    code and log tail and restarts the whole stack (the feed's restart changes
    the run_id the others attach to), up to MAX_SESSION_RESTARTS times a session.
    After that it stops the stack, sends an URGENT email, and leaves it down until
    the next session; positions keep their IB backstop stops.
    """

    def __init__(self, schedule, config: Config):
        super().__init__(schedule, config)
        self.monitor_func = self.custom_monitor
        self.is_down = True
        self.pid = None
        self.session: date | None = None
        self.session_restarts = 0
        self.gave_up = False

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

    def _exited_today(self) -> dict[str, tuple[int, str]] | None:
        """Project containers that exited during today's ET session: name -> (exit code, finished at).
        None if docker could not be reached."""
        names = self._project_containers(running_only=False)
        if names is None:
            return None
        stopped = sorted((names & EXPECTED_NAMES) - (self._project_containers() or set()))
        if not stopped:
            return {}
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.Name}}\t{{.State.ExitCode}}\t{{.State.FinishedAt}}", *stopped],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            self.job_logger.error(f"docker inspect returned {result.returncode}: {result.stderr.strip()}")
            return None
        today = datetime.now(ET).date()
        out = {}
        for line in result.stdout.splitlines():
            name, code, finished = line.split("\t")
            ended = datetime.fromisoformat(finished[:19]).replace(tzinfo=timezone.utc).astimezone(ET)
            if ended.date() == today:
                out[name.lstrip("/")] = (int(code), ended.strftime("%H:%M:%S"))
        return out

    def _log_tail(self, name: str) -> str:
        result = subprocess.run(["docker", "logs", "--tail", str(LOG_TAIL_LINES), name],
                                capture_output=True, text=True, timeout=10)
        return (result.stdout + result.stderr).strip()

    def _alert(self, body: str, subject: str) -> None:
        try:
            send_mail_msg(body, subject)
        except (smtplib.SMTPException, OSError) as e:
            # A failed email must not end this monitor thread: it is also what restarts the stack.
            self.job_logger.error(f"Alert email failed ({e}): {subject}")

    def _on_failure(self, exited: dict[str, tuple[int, str]]) -> str:
        """Alert, then restart the stack, or give up for the session after MAX_SESSION_RESTARTS."""
        today = datetime.now(ET).date()
        if self.session != today:
            self.session, self.session_restarts, self.gave_up = today, 0, False
        if self.gave_up:
            return "SUCCESS"            # down for the rest of the session; already alerted
        what = ", ".join(f"{n.removeprefix(COMPOSE_PROJECT + '-').removesuffix('-1')} (exit {c} at {t} ET)"
                         for n, (c, t) in sorted(exited.items()))
        body = "\n\n".join(f"===== {n}: exit {c} at {t} ET, last {LOG_TAIL_LINES} log lines =====\n{self._log_tail(n)}"
                            for n, (c, t) in sorted(exited.items()))
        self.is_down = True              # the "back up" email follows the restart
        if self.session_restarts < MAX_SESSION_RESTARTS:
            self.session_restarts += 1
            self.job_logger.error(f"Exited: {what}; restarting the stack "
                                  f"({self.session_restarts}/{MAX_SESSION_RESTARTS})")
            self._alert(body, f"sctrading live: {what}; restarting "
                              f"({self.session_restarts}/{MAX_SESSION_RESTARTS})")
            return "SILENT_RESTART"
        self.gave_up = True
        self.job_logger.error(f"Exited: {what}; {MAX_SESSION_RESTARTS} restarts used, stopping the stack")
        self._compose("stop", timeout=60)
        self._alert(body, f"URGENT sctrading live down: {what}; {MAX_SESSION_RESTARTS} restarts used, "
                          f"stack stopped for the session (positions keep their IB backstops)")
        return "SUCCESS"

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
        if missing and self.within_schedule():
            exited = self._exited_today()
            if exited is None:
                self.job_logger.warning("Could not reach docker; skipping this check.")
                return "SUCCESS"
            if exited:
                return self._on_failure(exited)
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
