"""Run browser tests without printing test credentials. Uses existing local .env."""

import os, subprocess
from pathlib import Path
from dotenv import dotenv_values

root = Path(__file__).resolve().parents[1]
values = dotenv_values(root / ".env")
process_env = {
    **os.environ,
    "E2E_EMAIL": values["ADMIN_EMAIL"],
    "E2E_PASSWORD": values["ADMIN_PASSWORD"],
}
raise SystemExit(
    subprocess.run(
        ["npx", "playwright", "test"], cwd=root / "frontend", env=process_env
    ).returncode
)
