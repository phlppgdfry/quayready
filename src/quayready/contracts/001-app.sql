-- Engineering specification only. Apply to a NEW disposable database.
-- PRAGMA foreign_keys=ON must be set on EACH connection before BEGIN.
PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY CHECK(version>0), checksum TEXT NOT NULL, applied_at_ms INTEGER NOT NULL) STRICT;
CREATE TABLE shipments(
 id TEXT PRIMARY KEY, site_id TEXT NOT NULL, order_source_id TEXT NOT NULL,
 external_order_ref TEXT NOT NULL CHECK(length(external_order_ref) BETWEEN 8 AND 100),
 route TEXT NOT NULL CHECK(route='DEMO-EU-GB'), order_revision INTEGER NOT NULL CHECK(order_revision=1),
 cutoff_ms INTEGER NOT NULL CHECK(cutoff_ms>=0), aggregate_version INTEGER NOT NULL CHECK(aggregate_version>=1),
 created_at_ms INTEGER NOT NULL CHECK(created_at_ms>=0),
 order_conflicted INTEGER NOT NULL DEFAULT 0 CHECK(order_conflicted IN (0,1)),
 UNIQUE(site_id,id), UNIQUE(site_id,order_source_id,external_order_ref)
) STRICT;
CREATE TABLE expected_pallets(
 site_id TEXT NOT NULL, shipment_id TEXT NOT NULL, pallet_id TEXT NOT NULL CHECK(length(pallet_id) BETWEEN 8 AND 100),
 PRIMARY KEY(site_id,shipment_id,pallet_id),
 FOREIGN KEY(site_id,shipment_id) REFERENCES shipments(site_id,id)
) STRICT;
CREATE TABLE inbound_receipts(
 id TEXT PRIMARY KEY, site_id TEXT NOT NULL, shipment_id TEXT NOT NULL, source_id TEXT NOT NULL,
 event_id TEXT NOT NULL CHECK(length(event_id) BETWEEN 8 AND 100),
 kind TEXT NOT NULL CHECK(kind IN ('ORDER','WAREHOUSE','DOCUMENT')),
 request_hash TEXT NOT NULL CHECK(length(request_hash)=64 AND request_hash NOT GLOB '*[^0-9a-f]*'),
 content_hash TEXT NOT NULL CHECK(length(content_hash)=64 AND content_hash NOT GLOB '*[^0-9a-f]*'),
 canonical_json TEXT NOT NULL CHECK(json_valid(canonical_json)),
 source_revision INTEGER NOT NULL CHECK(source_revision>=1),
 observed_at_ms INTEGER CHECK(observed_at_ms IS NULL OR observed_at_ms>=0),
 received_at_ms INTEGER NOT NULL CHECK(received_at_ms>=0),
 result TEXT NOT NULL CHECK(result IN ('APPLIED','STALE_IGNORED','REVISION_REPLAY')),
 CHECK((kind='ORDER' AND observed_at_ms IS NULL) OR (kind!='ORDER' AND observed_at_ms IS NOT NULL AND observed_at_ms<=received_at_ms)),
 UNIQUE(site_id,source_id,event_id), UNIQUE(site_id,shipment_id,id),
 FOREIGN KEY(site_id,shipment_id) REFERENCES shipments(site_id,id)
) STRICT;
CREATE TABLE warehouse_events(
 site_id TEXT NOT NULL, shipment_id TEXT NOT NULL, receipt_id TEXT NOT NULL, pallet_id TEXT NOT NULL,
 PRIMARY KEY(receipt_id,pallet_id),
 FOREIGN KEY(site_id,shipment_id,receipt_id) REFERENCES inbound_receipts(site_id,shipment_id,id)
) STRICT;
CREATE TABLE source_snapshots(
 site_id TEXT NOT NULL, shipment_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('WAREHOUSE','DOCUMENT')),
 source_id TEXT NOT NULL, receipt_id TEXT NOT NULL, source_revision INTEGER NOT NULL CHECK(source_revision>=1),
 observed_at_ms INTEGER NOT NULL CHECK(observed_at_ms>=0), valid_until_ms INTEGER NOT NULL,
 watermark TEXT NOT NULL CHECK(length(watermark) BETWEEN 8 AND 100),
 status TEXT NOT NULL, hard_hold INTEGER NOT NULL CHECK(hard_hold IN (0,1)),
 conflict_revision_floor INTEGER CHECK(conflict_revision_floor IS NULL OR conflict_revision_floor>=source_revision),
 CHECK(valid_until_ms=observed_at_ms+900000),
 CHECK((kind='WAREHOUSE' AND status IN ('KNOWN','UNKNOWN')) OR
       (kind='DOCUMENT' AND status IN ('AVAILABLE','MISSING','UNKNOWN','HOLD') AND hard_hold=(status='HOLD'))),
 PRIMARY KEY(site_id,shipment_id,kind),
 FOREIGN KEY(site_id,shipment_id,receipt_id) REFERENCES inbound_receipts(site_id,shipment_id,id)
) STRICT;
CREATE TABLE operational_issues(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, site_id TEXT NOT NULL, shipment_id TEXT NOT NULL,
 reason_code TEXT NOT NULL CHECK(reason_code IN ('HARD_HOLD','CUTOFF_REACHED','WAREHOUSE_MISSING','DOCUMENT_MISSING','WAREHOUSE_UNKNOWN','DOCUMENT_UNKNOWN','DOCUMENT_UNAVAILABLE','WAREHOUSE_EXPIRED','DOCUMENT_EXPIRED','SOURCE_CONFLICT','MISSING_PALLET','UNEXPECTED_PALLET','POST_APPROVAL_CHANGE')),
 owner TEXT NOT NULL CHECK(owner IN ('Warehouse','Documents','Planner','Integration')),
 detail_json TEXT NOT NULL CHECK(json_valid(detail_json)), first_seen_ms INTEGER NOT NULL,
 resolved_at_ms INTEGER CHECK(resolved_at_ms IS NULL OR resolved_at_ms>=first_seen_ms),
 FOREIGN KEY(site_id,shipment_id) REFERENCES shipments(site_id,id)
) STRICT;
CREATE UNIQUE INDEX one_open_issue ON operational_issues(site_id,shipment_id,reason_code) WHERE resolved_at_ms IS NULL;
CREATE INDEX issues_cursor ON operational_issues(site_id,sequence);
CREATE TABLE approval_proposals(
 id TEXT PRIMARY KEY, site_id TEXT NOT NULL, shipment_id TEXT NOT NULL, requested_by TEXT NOT NULL,
 idempotency_key TEXT NOT NULL CHECK(length(idempotency_key) BETWEEN 8 AND 100),
 request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
 evidence_version INTEGER NOT NULL CHECK(evidence_version>=1), evidence_hash TEXT NOT NULL CHECK(length(evidence_hash)=64),
 rules_version TEXT NOT NULL CHECK(rules_version='readiness-v1'), evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
 created_at_ms INTEGER NOT NULL, expires_at_ms INTEGER NOT NULL CHECK(expires_at_ms>created_at_ms),
 status TEXT NOT NULL CHECK(status IN ('PENDING_REVIEW','REJECTED','APPROVED','INVALIDATED','EXPIRED')),
 UNIQUE(site_id,id), UNIQUE(site_id,shipment_id,id), UNIQUE(site_id,requested_by,idempotency_key),
 FOREIGN KEY(site_id,shipment_id) REFERENCES shipments(site_id,id)
) STRICT;
CREATE UNIQUE INDEX one_pending_proposal ON approval_proposals(site_id,shipment_id) WHERE status='PENDING_REVIEW';
CREATE TABLE review_decisions(
 id TEXT PRIMARY KEY, site_id TEXT NOT NULL, shipment_id TEXT NOT NULL, proposal_id TEXT NOT NULL UNIQUE,
 reviewer TEXT NOT NULL, idempotency_key TEXT NOT NULL CHECK(length(idempotency_key) BETWEEN 8 AND 100),
 request_hash TEXT NOT NULL CHECK(length(request_hash)=64),
 action TEXT NOT NULL CHECK(action IN ('APPROVE','REJECT')), reason TEXT NOT NULL CHECK(length(reason) BETWEEN 1 AND 500),
 decided_at_ms INTEGER NOT NULL, dispatch_id TEXT,
 CHECK((action='APPROVE' AND dispatch_id IS NOT NULL) OR (action='REJECT' AND dispatch_id IS NULL)),
 UNIQUE(site_id,shipment_id,proposal_id), UNIQUE(site_id,reviewer,idempotency_key),
 FOREIGN KEY(site_id,shipment_id,proposal_id) REFERENCES approval_proposals(site_id,shipment_id,id),
 FOREIGN KEY(site_id,shipment_id,proposal_id,dispatch_id) REFERENCES outbox(site_id,shipment_id,proposal_id,dispatch_id) DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE TABLE outbox(
 dispatch_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, shipment_id TEXT NOT NULL, proposal_id TEXT NOT NULL UNIQUE,
 payload_json TEXT NOT NULL CHECK(json_valid(payload_json)), payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
 state TEXT NOT NULL CHECK(state IN ('QUEUED','SENDING','RETRY_WAIT','CONFIRMED','MANUAL_REVIEW','CANCELLED_BEFORE_SEND')),
 next_action TEXT NOT NULL CHECK(next_action IN ('POST','LOOKUP')),
 post_attempts INTEGER NOT NULL DEFAULT 0 CHECK(post_attempts BETWEEN 0 AND 3),
 lookup_attempts INTEGER NOT NULL DEFAULT 0 CHECK(lookup_attempts BETWEEN 0 AND 3),
 next_attempt_at_ms INTEGER NOT NULL CHECK(next_attempt_at_ms>=0),
 last_worker_at_ms INTEGER NOT NULL DEFAULT 0 CHECK(last_worker_at_ms>=0),
 lease_generation INTEGER NOT NULL DEFAULT 0 CHECK(lease_generation>=0), lease_until_ms INTEGER,
 target_receipt_id TEXT, confirmed_at_ms INTEGER, last_error_code TEXT,
 CHECK((state='SENDING' AND lease_until_ms IS NOT NULL) OR (state!='SENDING' AND lease_until_ms IS NULL)),
 CHECK(state!='CANCELLED_BEFORE_SEND' OR post_attempts=0),
 CHECK((state='CONFIRMED' AND target_receipt_id IS NOT NULL AND confirmed_at_ms IS NOT NULL) OR
       (state!='CONFIRMED' AND target_receipt_id IS NULL AND confirmed_at_ms IS NULL)),
 UNIQUE(site_id,shipment_id,proposal_id,dispatch_id),
 FOREIGN KEY(site_id,shipment_id,proposal_id) REFERENCES review_decisions(site_id,shipment_id,proposal_id) DEFERRABLE INITIALLY DEFERRED
) STRICT;
CREATE UNIQUE INDEX one_dispatch_barrier ON outbox(site_id,shipment_id) WHERE state!='CANCELLED_BEFORE_SEND';
CREATE INDEX outbox_due ON outbox(state,next_attempt_at_ms);
CREATE TABLE audit_events(
 sequence INTEGER PRIMARY KEY AUTOINCREMENT, site_id TEXT NOT NULL, shipment_id TEXT NOT NULL,
 actor TEXT NOT NULL, kind TEXT NOT NULL, at_ms INTEGER NOT NULL CHECK(at_ms>=0),
 correlation_id TEXT NOT NULL, detail_json TEXT NOT NULL CHECK(json_valid(detail_json)),
 FOREIGN KEY(site_id,shipment_id) REFERENCES shipments(site_id,id)
) STRICT;
CREATE INDEX audit_cursor ON audit_events(site_id,shipment_id,sequence);
CREATE TRIGGER order_immutable BEFORE UPDATE OF id,site_id,order_source_id,external_order_ref,route,order_revision,cutoff_ms,created_at_ms ON shipments
 BEGIN SELECT RAISE(ABORT,'immutable order'); END;
CREATE TRIGGER order_version_step BEFORE UPDATE OF aggregate_version ON shipments WHEN NEW.aggregate_version!=OLD.aggregate_version+1
 BEGIN SELECT RAISE(ABORT,'aggregate version must increment by one'); END;
CREATE TRIGGER order_conflict_latched BEFORE UPDATE OF order_conflicted ON shipments WHEN NEW.order_conflicted<OLD.order_conflicted
 BEGIN SELECT RAISE(ABORT,'immutable order conflict requires new demo run'); END;
CREATE TRIGGER expected_no_update BEFORE UPDATE ON expected_pallets BEGIN SELECT RAISE(ABORT,'immutable expected pallet'); END;
CREATE TRIGGER expected_no_delete BEFORE DELETE ON expected_pallets BEGIN SELECT RAISE(ABORT,'immutable expected pallet'); END;
CREATE TRIGGER expected_sealed BEFORE INSERT ON expected_pallets
 WHEN EXISTS(SELECT 1 FROM inbound_receipts WHERE site_id=NEW.site_id AND shipment_id=NEW.shipment_id AND kind='ORDER')
 BEGIN SELECT RAISE(ABORT,'order receipt seals expected pallet set'); END;
CREATE TRIGGER receipts_no_update BEFORE UPDATE ON inbound_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE TRIGGER receipts_no_delete BEFORE DELETE ON inbound_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE TRIGGER warehouse_no_update BEFORE UPDATE ON warehouse_events BEGIN SELECT RAISE(ABORT,'immutable membership'); END;
CREATE TRIGGER warehouse_no_delete BEFORE DELETE ON warehouse_events BEGIN SELECT RAISE(ABORT,'immutable membership'); END;
CREATE TRIGGER warehouse_kind BEFORE INSERT ON warehouse_events
 WHEN NOT EXISTS(SELECT 1 FROM inbound_receipts WHERE id=NEW.receipt_id AND kind='WAREHOUSE')
 BEGIN SELECT RAISE(ABORT,'warehouse receipt required'); END;
CREATE TRIGGER decisions_no_update BEFORE UPDATE ON review_decisions BEGIN SELECT RAISE(ABORT,'immutable decision'); END;
CREATE TRIGGER decisions_no_delete BEFORE DELETE ON review_decisions BEGIN SELECT RAISE(ABORT,'immutable decision'); END;
CREATE TRIGGER decision_valid BEFORE INSERT ON review_decisions
 WHEN NOT EXISTS(SELECT 1 FROM approval_proposals p JOIN shipments s ON s.id=p.shipment_id AND s.site_id=p.site_id
  WHERE p.id=NEW.proposal_id AND p.site_id=NEW.site_id AND p.shipment_id=NEW.shipment_id
    AND p.status='PENDING_REVIEW' AND p.requested_by!=NEW.reviewer
    AND p.evidence_version=s.aggregate_version AND NEW.decided_at_ms>=p.created_at_ms AND NEW.decided_at_ms<p.expires_at_ms)
 BEGIN SELECT RAISE(ABORT,'invalid or self decision'); END;
CREATE TRIGGER outbox_approval BEFORE INSERT ON outbox
 WHEN NOT EXISTS(SELECT 1 FROM review_decisions d WHERE d.proposal_id=NEW.proposal_id AND d.action='APPROVE' AND d.dispatch_id=NEW.dispatch_id AND d.site_id=NEW.site_id AND d.shipment_id=NEW.shipment_id)
 BEGIN SELECT RAISE(ABORT,'matching approval required'); END;
CREATE TRIGGER outbox_payload_immutable BEFORE UPDATE OF dispatch_id,site_id,shipment_id,proposal_id,payload_json,payload_hash ON outbox
 BEGIN SELECT RAISE(ABORT,'immutable dispatch payload'); END;
CREATE TRIGGER outbox_no_delete BEFORE DELETE ON outbox BEGIN SELECT RAISE(ABORT,'preserve dispatch barrier'); END;
CREATE TRIGGER outbox_monotone BEFORE UPDATE ON outbox
 WHEN NEW.post_attempts<OLD.post_attempts OR NEW.lookup_attempts<OLD.lookup_attempts OR NEW.lease_generation<OLD.lease_generation OR NEW.last_worker_at_ms<OLD.last_worker_at_ms
 BEGIN SELECT RAISE(ABORT,'counters and fences never decrease'); END;
CREATE TRIGGER outbox_transition BEFORE UPDATE OF state ON outbox
 WHEN NOT (NEW.state=OLD.state OR
  (OLD.state IN ('QUEUED','RETRY_WAIT') AND NEW.state IN ('SENDING','CANCELLED_BEFORE_SEND','MANUAL_REVIEW')) OR
  (OLD.state='SENDING' AND NEW.state IN ('CONFIRMED','RETRY_WAIT','MANUAL_REVIEW')) OR
  (OLD.state='MANUAL_REVIEW' AND NEW.state='CONFIRMED'))
 BEGIN SELECT RAISE(ABORT,'invalid delivery transition'); END;
CREATE TRIGGER proposal_immutable BEFORE UPDATE OF id,site_id,shipment_id,requested_by,idempotency_key,request_hash,evidence_version,evidence_hash,rules_version,evidence_json,created_at_ms,expires_at_ms ON approval_proposals
 BEGIN SELECT RAISE(ABORT,'immutable proposal evidence'); END;
CREATE TRIGGER proposal_no_delete BEFORE DELETE ON approval_proposals BEGIN SELECT RAISE(ABORT,'preserve proposal'); END;
CREATE TRIGGER proposal_transition BEFORE UPDATE OF status ON approval_proposals
 WHEN NOT ((OLD.status='PENDING_REVIEW' AND NEW.status IN ('APPROVED','REJECTED','INVALIDATED','EXPIRED')) OR
           (OLD.status='APPROVED' AND NEW.status IN ('INVALIDATED','EXPIRED')))
 BEGIN SELECT RAISE(ABORT,'invalid proposal transition'); END;
CREATE TRIGGER proposal_approved BEFORE UPDATE OF status ON approval_proposals WHEN NEW.status='APPROVED' AND
 NOT EXISTS(SELECT 1 FROM review_decisions d JOIN outbox o ON o.dispatch_id=d.dispatch_id WHERE d.proposal_id=NEW.id AND d.action='APPROVE')
 BEGIN SELECT RAISE(ABORT,'approval and outbox required'); END;
CREATE TRIGGER proposal_rejected BEFORE UPDATE OF status ON approval_proposals WHEN NEW.status='REJECTED' AND
 NOT EXISTS(SELECT 1 FROM review_decisions WHERE proposal_id=NEW.id AND action='REJECT')
 BEGIN SELECT RAISE(ABORT,'reject decision required'); END;
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT,'append only audit'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT,'append only audit'); END;
COMMIT;
