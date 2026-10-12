"""Build Compose images with the cloud's supplied proxy and CA, or normal VPS networking."""

import os, socket, subprocess, tempfile
from pathlib import Path
from urllib.parse import urlsplit
import yaml

root = Path(__file__).resolve().parents[1]
process_env = dict(os.environ)
process_env.setdefault(
    "DOCKER_CONFIG",
    "/workspace/.docker"
    if Path("/workspace").exists()
    else str(Path.home() / ".docker"),
)
command = ["docker", "compose", "-f", str(root / "docker-compose.yml")]
proxy_hosts = {}
for name in ("HTTP_PROXY", "HTTPS_PROXY"):
    host = urlsplit(process_env.get(name, "")).hostname
    if host:
        proxy_hosts[host] = socket.gethostbyname(host)
cert = process_env.get("SSL_CERT_FILE")
if proxy_hosts and cert and Path(cert).is_file():
    build = {"network": "host", "extra_hosts": proxy_hosts, "secrets": ["cloud-ca"]}
    override = {
        "services": {
            name: {"build": build}
            for name in ("backend", "worker", "scheduler", "migrate", "frontend")
        },
        "secrets": {"cloud-ca": {"file": cert}},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yml") as file:
        yaml.safe_dump(override, file)
        file.flush()
        raise SystemExit(
            subprocess.run(
                command
                + [
                    "-f",
                    file.name,
                    "build",
                    "--build-arg",
                    "HTTP_PROXY",
                    "--build-arg",
                    "HTTPS_PROXY",
                ],
                cwd=root,
                env=process_env,
            ).returncode
        )
raise SystemExit(
    subprocess.run(command + ["build"], cwd=root, env=process_env).returncode
)
