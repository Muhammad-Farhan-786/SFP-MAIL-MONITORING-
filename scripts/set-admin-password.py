"""Run the operator password-reset helper inside the backend container."""

import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
raise SystemExit(
    subprocess.run(
        ["docker", "compose", "exec", "backend", "python", "-m", "app.password"],
        cwd=root,
    ).returncode
)
