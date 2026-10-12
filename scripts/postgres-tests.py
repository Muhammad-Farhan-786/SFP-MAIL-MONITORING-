"""Run the same tests against a separately created PostgreSQL *_tests database."""

import os, subprocess
from sqlalchemy.engine import make_url
from app.config import config

process_env = dict(os.environ)
process_env["TEST_DATABASE_URL"] = (
    make_url(config().database_url)
    .set(database="emailhealth_tests")
    .render_as_string(hide_password=False)
)
raise SystemExit(
    subprocess.run(
        ["python", "-m", "pytest", "-q"], cwd="/app", env=process_env
    ).returncode
)
