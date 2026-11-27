"""Local single-instance evidence ledger and content-addressed source archive.

This is an append-only application interface, not a tamper-proof WORM service.
A local administrator can still alter the database or blob store; export signed
checkpoints to an independently controlled system for stronger assurance.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "socioweave-evidence-event-v1"
ZERO_HASH = "0" * 64


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def storage_root() -> Path:
    return Path(os.environ.get("SOCIOWEAVE_EVIDENCE_DIR", "./var/evidence")).expanduser().resolve()


def database_path() -> Path:
    return storage_root() / "ledger.sqlite3"


def _connect() -> sqlite3.Connection:
    root = storage_root()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = database_path()
    if db.is_symlink():
        raise ValueError("ledger database must not be a symlink")
    connection = sqlite3.connect(str(db), timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS evidence_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            actor_claim TEXT NOT NULL,
            event_type TEXT NOT NULL,
            subject TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL UNIQUE
        )
    """)
    return connection


def append_event(*, actor_claim: str, event_type: str, subject: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not actor_claim.strip() or len(actor_claim) > 200:
        raise ValueError("actor_claim must contain 1..200 characters")
    if not subject.strip() or len(subject) > 500:
        raise ValueError("subject must contain 1..500 characters")
    if event_type != "operator_attestation":
        raise ValueError("only operator_attestation events are accepted in Studio-4")
    payload_json = canonical_json(payload)
    created_at = datetime.now(timezone.utc).isoformat()
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        last = connection.execute(
            "SELECT sequence, event_hash FROM evidence_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = last["event_hash"] if last else ZERO_HASH
        sequence = (last["sequence"] + 1) if last else 1
        event = {
            "schema_version": SCHEMA_VERSION,
            "sequence": sequence,
            "created_at": created_at,
            "actor_claim": actor_claim,
            "event_type": event_type,
            "subject": subject,
            "payload": json.loads(payload_json),
            "previous_hash": previous_hash,
        }
        event_hash = sha256_bytes(canonical_json(event).encode("utf-8"))
        connection.execute(
            """INSERT INTO evidence_events
            (sequence, schema_version, created_at, actor_claim, event_type, subject,
             payload_json, previous_hash, event_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (sequence, SCHEMA_VERSION, created_at, actor_claim, event_type, subject,
             payload_json, previous_hash, event_hash),
        )
        connection.execute("COMMIT")
        return {**event, "event_hash": event_hash}
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def verify_ledger() -> dict[str, Any]:
    connection = _connect()
    try:
        rows = connection.execute("SELECT * FROM evidence_events ORDER BY sequence").fetchall()
    finally:
        connection.close()
    previous_hash = ZERO_HASH
    errors: list[str] = []
    for expected_sequence, row in enumerate(rows, start=1):
        if row["sequence"] != expected_sequence:
            errors.append(f"sequence gap at row {expected_sequence}")
        if row["schema_version"] != SCHEMA_VERSION:
            errors.append(f"unsupported schema at sequence {row['sequence']}")
        if row["previous_hash"] != previous_hash:
            errors.append(f"previous hash mismatch at sequence {row['sequence']}")
        event = {
            "schema_version": row["schema_version"],
            "sequence": row["sequence"],
            "created_at": row["created_at"],
            "actor_claim": row["actor_claim"],
            "event_type": row["event_type"],
            "subject": row["subject"],
            "payload": json.loads(row["payload_json"]),
            "previous_hash": row["previous_hash"],
        }
        calculated = sha256_bytes(canonical_json(event).encode("utf-8"))
        if calculated != row["event_hash"]:
            errors.append(f"event hash mismatch at sequence {row['sequence']}")
        previous_hash = row["event_hash"]
    return {
        "verification": "LEDGER_CHAIN_VALID" if not errors else "LEDGER_CHAIN_INVALID",
        "event_count": len(rows),
        "head_hash": previous_hash,
        "errors": errors,
        "tamper_resistance": "hash-chain tampering is detectable relative to a trusted checkpoint; local administrators can rewrite the entire store",
        "actor_identity": "self_asserted_claim_not_authenticated_identity",
    }


def store_blob(expected_sha256: str, content: bytes, *, max_bytes: int = 10 * 1024 * 1024) -> dict[str, Any]:
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    if len(content) > max_bytes:
        raise ValueError(f"source blob exceeds {max_bytes} byte limit")
    actual = sha256_bytes(content)
    if actual != expected_sha256:
        raise ValueError("uploaded bytes do not match expected SHA-256")
    root = storage_root() / "blobs"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / actual
    if target.is_symlink():
        raise ValueError("blob target must not be a symlink")
    if target.exists():
        if not target.is_file() or sha256_bytes(target.read_bytes()) != actual:
            raise ValueError("existing content-addressed blob is corrupt")
        return {"sha256": actual, "byte_count": len(content), "stored": False, "idempotent": True}
    temporary = root / (actual + ".tmp-" + str(os.getpid()))
    if temporary.exists() or temporary.is_symlink():
        raise ValueError("temporary blob path already exists")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {"sha256": actual, "byte_count": len(content), "stored": True, "idempotent": False}


def verify_blob(expected_sha256: str) -> dict[str, Any]:
    if len(expected_sha256) != 64 or any(c not in "0123456789abcdef" for c in expected_sha256):
        raise ValueError("expected_sha256 must be a lowercase SHA-256 digest")
    root = storage_root() / "blobs"
    target = root / expected_sha256
    if target.is_symlink() or not target.is_file():
        return {"verification": "SOURCE_BLOB_MISSING", "sha256": expected_sha256, "source_file_rechecked": False}
    actual = sha256_bytes(target.read_bytes())
    return {
        "verification": "SOURCE_BLOB_HASH_VALID" if actual == expected_sha256 else "SOURCE_BLOB_HASH_INVALID",
        "sha256": expected_sha256,
        "actual_sha256": actual,
        "source_file_rechecked": True,
    }
