"""Only processes started by a test are terminated; no shared services are touched."""

import os
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx


@contextmanager
def server(cfg, command="target", fault="none"):
    env = {
        **os.environ,
        "QUAYREADY_CONFIG": str(cfg.run_dir / "config.json"),
        "QUAYREADY_TARGET_FAULT": fault,
    }
    log = (cfg.run_dir / f"{command}-{fault}.log").open("a")
    process = subprocess.Popen(
        [sys.executable, "-m", "quayready.cli", command], env=env, stdout=log, stderr=log
    )
    port = cfg.target_port if command == "target" else cfg.app_port
    url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(trust_env=False, timeout=0.3) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(f"{command} exited: see {log.name}")
                try:
                    if client.get(url + "/health/ready").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.05)
            else:
                raise RuntimeError(f"{command} did not become ready")
        yield url
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        log.close()
