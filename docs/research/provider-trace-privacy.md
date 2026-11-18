# Provider trace privacy view (Core 22.3.15)

## Scope

The provider invocation trace (ProtocolCallTrace) contains identity/configuration fields, request correlation, operational metrics, and content fingerprints. Hashes are treated as potentially linkable correlation data; they are not assumed to be anonymous merely because they are not raw prompt/output text.

## Opt-in redacted export

ProtocolCallTrace.privacy_redacted() returns a separate trace view intended for privacy-reduced export or sharing. It masks actor/model/model-family/provider/returned-model identifiers; provider request ID; input and output SHA-256 fingerprints.

It preserves action, input/output token counts, and measured latency. The original trace is unchanged. Redaction is opt-in; it is not applied to routing or runtime execution. This change does not claim a complete privacy boundary or implement retention, access control, encryption, provider logging controls, pseudonymization rotation, or differential privacy.

## Threat and limitations

- Preserved metrics may still contribute to run-level linkage when combined with external metadata.
- The sentinel string [REDACTED] is a display/export convention, not cryptographic anonymization.
- Prompt and response content are not stored in this trace dataclass, but provider SDKs and external services may retain request data.
- This is a narrow field-level reduction for exported trace records; governance decisions about retention and access remain outstanding.
