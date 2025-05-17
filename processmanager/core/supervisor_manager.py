import subprocess

def reload_supervisor():
    commands = [
        ["sudo", "supervisorctl", "update"],
        ["sudo", "supervisorctl", "restart", "scheduler"],
    ]

    for cmd in commands:
        try:
            # run the command, capture stdout/stderr
            completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"$ {' '.join(cmd)}\n{completed.stdout.strip()}\n")
        except subprocess.CalledProcessError as e:
            print(f"Error running: {' '.join(cmd)}")
            print(f"Exit code: {e.returncode}")
            print(f"Stdout: {e.stdout.strip()}")
            print(f"Stderr: {e.stderr.strip()}")