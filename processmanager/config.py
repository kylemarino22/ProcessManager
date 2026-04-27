from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class Config:
    schedule_file: Path
    status_dir:    Path
    log_dir:       Path

# then, to instantiate:
config = Config(
    schedule_file=Path("/home/kyle/projects/processmanager/schedules/full_schedule.json"),
    status_dir=   Path("/home/kyle/projects/processmanager/statuses"),
    log_dir=      Path("/home/kyle/projects/processmanager/logs"),
)