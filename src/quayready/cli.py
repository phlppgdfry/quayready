from __future__ import annotations

import argparse
import json
import os
import secrets
import time
from pathlib import Path

import httpx
import uvicorn

from .api import create_app
from .common import Json, canonical, iso
from .config import Settings, load_settings
from .db import Database
from .store import Store
from .worker import Worker


def initialize(path: Path, app_port: int = 8080, target_port: int = 8081) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    principals = {}
    for name, roles, kind in [
        ("OPERATOR", ["operator", "reviewer"], None),
        ("REVIEWER", ["reviewer"], None),
        ("AUDITOR", ["auditor"], None),
        ("ORDER", ["order_source"], "ORDER"),
        ("WAREHOUSE", ["warehouse_source"], "WAREHOUSE"),
        ("DOCUMENT", ["document_source"], "DOCUMENT"),
    ]:
        principals[secrets.token_urlsafe(32)] = {
            "subject": "DEMO-" + name,
            "site": "DEMO-ZEE",
            "roles": roles,
            "kind": kind,
        }
    config = {
        "principals": principals,
        "workerKey": secrets.token_urlsafe(32),
        "domainTime": "2026-11-02T11:40:00Z",
        "appPort": app_port,
        "targetPort": target_port,
    }
    target = path / "config.json"
    target.write_text(json.dumps(config, indent=2) + "\n")
    target.chmod(0o600)
    old = os.environ.get("QUAYREADY_CONFIG")
    os.environ["QUAYREADY_CONFIG"] = str(target.resolve())
    try:
        cfg = load_settings()
        Store(cfg).db.initialize()
        db = Database(path / "target.db", True)
        db.initialize()
        with db.transaction() as c:
            c.execute("INSERT INTO target_orders VALUES('DEMO-ZEE','DEMO-ORDER-001',1)")
    finally:
        if old is None:
            os.environ.pop("QUAYREADY_CONFIG", None)
        else:
            os.environ["QUAYREADY_CONFIG"] = old
    return target


def key_for(cfg: Settings, subject: str) -> str:
    return next(k for k, p in cfg.principals.items() if p.subject == "DEMO-" + subject.upper())


def seed(cfg: Settings, correct: bool = False) -> dict[str, str]:
    with httpx.Client(base_url=cfg.origin, trust_env=False, timeout=5) as client:
        order: Json = {
            "schemaVersion": 1,
            "eventId": "DEMO-ORDER-E001",
            "externalOrderRef": "DEMO-ORDER-001",
            "orderRevision": 1,
            "route": "DEMO-EU-GB",
            "cutoffAt": "2026-11-02T12:00:00Z",
            "expectedPalletIds": ["DEMO-P001", "DEMO-P002", "DEMO-P003"],
        }
        r = client.post("/v1/orders", json=order, headers={"X-Source-Key": key_for(cfg, "ORDER")})
        r.raise_for_status()
        sid = r.json()["shipmentId"]
        rev = 2 if correct else 1
        warehouse = {
            "schemaVersion": 1,
            "eventId": f"DEMO-WMS-E00{rev}",
            "shipmentId": sid,
            "sourceRevision": rev,
            "observedAt": iso(cfg.now()),
            "watermark": f"DEMO-WMS-W00{rev}",
            "kind": "warehouse_snapshot",
            "status": "KNOWN",
            "scannedPalletIds": order["expectedPalletIds"]
            if correct
            else order["expectedPalletIds"][:2],
            "hardHold": False,
        }
        r = client.post(
            "/v1/events", json=warehouse, headers={"X-Source-Key": key_for(cfg, "WAREHOUSE")}
        )
        r.raise_for_status()
        if not correct:
            doc = {
                "schemaVersion": 1,
                "eventId": "DEMO-DOC-E001",
                "shipmentId": sid,
                "sourceRevision": 1,
                "observedAt": iso(cfg.now()),
                "watermark": "DEMO-DOC-W001",
                "kind": "document_snapshot",
                "status": "AVAILABLE",
            }
            r = client.post(
                "/v1/events", json=doc, headers={"X-Source-Key": key_for(cfg, "DOCUMENT")}
            )
            r.raise_for_status()
        return {
            "shipmentId": sid,
            "scenario": "corrected-three-pallets" if correct else "missing-third-pallet",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="QuayReady · local synthetic integration lab")
    parser.add_argument(
        "command", choices=["init", "serve", "target", "worker", "seed", "correct", "credentials"]
    )
    parser.add_argument("--directory", default=".runs/demo")
    parser.add_argument("--role", default="operator", choices=["operator", "reviewer", "auditor"])
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--app-port", type=int, default=8080)
    parser.add_argument("--target-port", type=int, default=8081)
    args = parser.parse_args()
    if args.command == "init":
        print(initialize(Path(args.directory), args.app_port, args.target_port))
        return
    if "QUAYREADY_CONFIG" not in os.environ:
        os.environ["QUAYREADY_CONFIG"] = str(Path(args.directory) / "config.json")
    cfg = load_settings()
    if args.command in ("serve", "target"):
        is_target = args.command == "target"
        uvicorn.run(
            create_app(cfg, target=is_target),
            host="127.0.0.1",
            port=cfg.target_port if is_target else cfg.app_port,
            proxy_headers=False,
            access_log=False,
        )
    elif args.command == "credentials":
        print(key_for(cfg, args.role))
    elif args.command in ("seed", "correct"):
        print(canonical(seed(cfg, args.command == "correct")))
    else:
        store = Store(cfg)
        store.db.initialize()
        worker = Worker(store)
        while True:
            row = worker.tick()
            if row:
                print(
                    canonical(
                        {"dispatchId": row["dispatch_id"], "reservedAction": row["next_action"]}
                    ),
                    flush=True,
                )
            if args.once:
                break
            time.sleep(0.25)


if __name__ == "__main__":
    main()
