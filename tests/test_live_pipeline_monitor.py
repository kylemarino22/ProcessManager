"""live-pipeline: a container that exits during the session is alerted and restarted with the
stack at most MAX_SESSION_RESTARTS times; then the stack is stopped for the session."""
import logging
import subprocess
from datetime import datetime, timezone
from types import SimpleNamespace

from processmanager.programs import live_pipeline_program as lp

NAMES = sorted(lp.EXPECTED_NAMES)
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Docker:
    """`docker` with every container running except ``exited`` (name -> (code, finished_at))."""

    def __init__(self, exited):
        self.exited, self.calls = exited, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        out = ""
        if cmd[:2] == ["docker", "ps"]:
            out = "\n".join(NAMES if "-a" in cmd else [n for n in NAMES if n not in self.exited])
        elif cmd[:2] == ["docker", "inspect"]:
            out = "\n".join(f"/{n}\t{self.exited[n][0]}\t{self.exited[n][1]}" for n in cmd[4:])
        elif cmd[:2] == ["docker", "logs"]:
            out = f"Traceback ...\nRuntimeError: boom in {cmd[-1]}"
        return SimpleNamespace(returncode=0, stdout=out, stderr="")


def program(monkeypatch, exited):
    docker, mails = Docker(exited), []
    monkeypatch.setattr(subprocess, "run", docker)
    monkeypatch.setattr(lp, "send_mail_msg", lambda body, subject: mails.append((subject, body)))
    p = lp.LivePipelineProgram.__new__(lp.LivePipelineProgram)
    p.is_down, p.session, p.session_restarts, p.gave_up = False, None, 0, False
    p.job_logger = logging.getLogger("test")
    p.within_schedule = lambda: True
    return p, docker, mails


def test_a_crash_is_alerted_with_its_log_and_restarted_three_times_then_the_stack_stops(monkeypatch):
    inference = "sctrading-inference_engine-1"
    p, docker, mails = program(monkeypatch, {inference: (1, TODAY)})
    assert [p.custom_monitor() for _ in range(3)] == ["SILENT_RESTART"] * 3
    for k, (subject, _) in enumerate(mails, 1):
        assert subject.startswith("sctrading live: inference_engine (exit 1 at ") and subject.endswith(f"restarting ({k}/3)")
    assert "RuntimeError: boom in sctrading-inference_engine-1" in mails[0][1]
    assert p.custom_monitor() == "SUCCESS"                       # the fourth: give up
    assert mails[-1][0].startswith("URGENT sctrading live down") and len(mails) == 4
    assert ["docker", "compose", "-f", lp.COMPOSE_FILE, "-p", lp.COMPOSE_PROJECT, "stop"] in docker.calls
    assert p.custom_monitor() == "SUCCESS" and len(mails) == 4   # stays down, quietly


def test_containers_stopped_before_today_start_the_session_normally(monkeypatch):
    p, _, mails = program(monkeypatch, {n: (0, "2026-11-20T01:00:28.264Z") for n in NAMES})
    p.is_down = True
    assert p.custom_monitor() == "SILENT_RESTART" and not mails and p.session_restarts == 0
