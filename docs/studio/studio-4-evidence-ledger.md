# Studio-4: evidence ledger and source archive

## Scope

Studio-4 adds a local, single-instance evidence persistence layer:

- SQLite append-only application API for operator attestation events.
- Canonical JSON serialization and a SHA-256 hash chain.
- Content-addressed source blob archive keyed by SHA-256.
- Independent re-hashing of archived bytes.
- Read-only integrity endpoints and a Studio verification panel.

This layer is provenance infrastructure, not a scientific approval system.

## Enable writes

Writes are disabled unless the server process is configured with both:

- `SOCIOWEAVE_EVIDENCE_WRITE_TOKEN`: a high-entropy bearer token held only by the server/operator.
- `SOCIOWEAVE_EVIDENCE_DIR`: a durable, private directory on a persistent volume.

The API currently uses one shared instance token. It does not provide user identities, role-based authorization, tenant isolation, or a secure multi-user control plane. Do not expose write routes to an untrusted network. Use TLS and an upstream authenticated reverse proxy if deploying beyond localhost; a shared token remains a single-instance administrative gate.

The default data directory is `./var/evidence`. Back it up as a consistent database plus blob-store snapshot. SQLite WAL mode is enabled.

## Attestation semantics

Only `operator_attestation` events are accepted. The `actor_claim` field is a self-reported label, not a verified principal. The API rejects common credential fields. An attestation records that an operator made a claim; it does not validate the claim, grant legal approval, or certify annotation quality.

Example request:

```http
POST /api/v1/evidence/events
Authorization: Bearer <instance-token>
Content-Type: application/json

{
  "actor_claim": "reviewer-01",
  "subject": "BREAK@release-2026-11",
  "payload": {
    "claim": "license review completed",
    "evidence_reference": "ticket-123"
  }
}
```

## Source archive

Upload exact source bytes to:

```http
PUT /api/v1/evidence/blobs/<lowercase-sha256>
Authorization: Bearer <instance-token>
Content-Type: application/octet-stream

<raw bytes>
```

The API verifies the digest before storing bytes. The current maximum upload size is 10 MiB per blob. Existing content-addressed blobs are idempotent and are checked before reuse. Rechecking uses `GET /api/v1/evidence/blobs/<sha256>/verify`.

The archive does not automatically discover or copy paths from a snapshot manifest. The operator must explicitly upload the exact source bytes. A manifest's declared source digest is not independently verified until matching bytes have been archived and rechecked.

## Integrity model and limitations

Each event hash covers the schema version, sequence, timestamp, actor claim, event type, subject, canonical payload and previous event hash. SQLite transactions serialize appends. The verifier checks sequence continuity, schema version, previous-hash links and each event digest.

This detects accidental or partial tampering when compared with an independently retained trusted head hash. It is **not tamper-proof storage**: a local administrator with write access to the database can rewrite the full chain. The current release has no signed checkpoints, remote transparency log, WORM storage, key management or external timestamp authority.

The blob archive is content-addressed and re-hashed on verification. It is local filesystem storage, not an immutable object-lock service. Filesystem and host administrators remain trusted.

## Operational and research boundary

- No experiment launch or provider execution is added.
- No E1 readiness status is changed.
- Synthetic test fixtures remain engineering fixtures.
- Operator attestations are not independent legal, source-authenticity or scientific validation.
- Authentication is a shared-token write gate only; multi-user authorization is not implemented.
- Do not store secrets, personal data or restricted dataset contents without a separate privacy/licensing review.
