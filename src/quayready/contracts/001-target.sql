-- Independent mock-TMS database. Never ATTACH it to the application database.
PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
CREATE TABLE target_orders(
 site_id TEXT NOT NULL, shipment_ref TEXT NOT NULL, order_revision INTEGER NOT NULL CHECK(order_revision=1),
 PRIMARY KEY(site_id,shipment_ref), UNIQUE(site_id,shipment_ref,order_revision)
) STRICT;
CREATE TABLE dispatch_requests(
 dispatch_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, shipment_ref TEXT NOT NULL, order_revision INTEGER NOT NULL,
 payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64), payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 receipt_id TEXT NOT NULL UNIQUE, accepted_at_ms INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status='ACCEPTED_FOR_REVIEW'),
 UNIQUE(site_id,shipment_ref),
 FOREIGN KEY(site_id,shipment_ref,order_revision) REFERENCES target_orders(site_id,shipment_ref,order_revision)
) STRICT;
CREATE TRIGGER target_no_update BEFORE UPDATE ON dispatch_requests BEGIN SELECT RAISE(ABORT,'immutable target effect'); END;
CREATE TRIGGER target_no_delete BEFORE DELETE ON dispatch_requests BEGIN SELECT RAISE(ABORT,'preserve target idempotency'); END;
COMMIT;
