from sociodec.providers.protocol_invoker import ProtocolCallTrace


def sample_trace():
    return ProtocolCallTrace(
        agent_id='agent-secret', model_id='model-secret', model_family='family-secret',
        provider='provider-secret', returned_model='returned-model-secret', action='draft',
        request_id='request-secret', input_tokens=111, output_tokens=22, latency_ms=45.67,
        input_sha256='input-hash-secret', output_sha256='output-hash-secret',
    )


def test_privacy_redacted_trace_masks_identifiers_and_correlation_fields():
    original = sample_trace()
    safe = original.privacy_redacted()
    assert safe.agent_id == '[REDACTED]'
    assert safe.model_id == '[REDACTED]'
    assert safe.model_family == '[REDACTED]'
    assert safe.provider == '[REDACTED]'
    assert safe.returned_model == '[REDACTED]'
    assert safe.request_id is None
    assert safe.input_sha256 == '[REDACTED]'
    assert safe.output_sha256 == '[REDACTED]'


def test_privacy_redacted_trace_preserves_selected_operational_metrics():
    original = sample_trace()
    safe = original.privacy_redacted()
    assert safe.action == original.action
    assert safe.input_tokens == original.input_tokens
    assert safe.output_tokens == original.output_tokens
    assert safe.latency_ms == original.latency_ms


def test_privacy_redaction_is_opt_in_and_does_not_mutate_original_trace():
    original = sample_trace()
    safe = original.privacy_redacted()
    assert original.agent_id == 'agent-secret'
    assert original.request_id == 'request-secret'
    assert original.input_sha256 == 'input-hash-secret'
    assert safe is not original
