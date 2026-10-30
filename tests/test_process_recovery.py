import os
import subprocess
import sys
import time

import pytest
from conftest import approve, ready
from processes import server
from test_recovery import effects, row


@pytest.mark.integration
def test_T12_T13_T14_worker_process_restart_after_lost_response(cfg, store):
    dispatch = approve(store, ready(store))
    env = {**os.environ, "QUAYREADY_CONFIG": str(cfg.run_dir / "config.json")}
    with server(cfg, fault="drop-after-commit"), (cfg.run_dir / "worker.log").open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "quayready.cli", "worker"], env=env, stdout=log, stderr=log
        )
        try:
            for _ in range(100):
                current = row(store)
                if current["state"] == "RETRY_WAIT":
                    break
                assert process.poll() is None
                time.sleep(0.025)
            else:
                pytest.fail("Worker did not persist uncertain outcome")
            assert effects(cfg) == 1
        finally:
            process.terminate()
            process.wait(timeout=5)
        assert row(store)["state"] == "RETRY_WAIT"
        # Persisted due time survives actual process termination; never reset it to 'now'.
        wait = max(0, (current["next_attempt_at_ms"] - time.time_ns() // 1_000_000) / 1000) + 0.05
        time.sleep(wait)
        subprocess.run(
            [sys.executable, "-m", "quayready.cli", "worker", "--once"],
            env=env,
            stdout=log,
            stderr=log,
            check=True,
            timeout=10,
        )
        final = row(store)
        assert final["state"] == "CONFIRMED" and final["dispatch_id"] == dispatch
        assert final["post_attempts"] == 1 and final["lookup_attempts"] == 1 and effects(cfg) == 1
