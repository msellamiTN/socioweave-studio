import pytest
from sociodec.providers.base import ChatMessage, GenerationConfig, GenerationResult

def test_chat_message_accepts_supported_roles():
    assert ChatMessage("user", "hello").content == "hello"
    with pytest.raises(ValueError):
        ChatMessage("tool", "unsupported")

def test_generation_config_validates_limits():
    assert GenerationConfig(temperature=0.7, max_new_tokens=1024).max_new_tokens == 1024
    with pytest.raises(ValueError):
        GenerationConfig(top_p=0)
    with pytest.raises(ValueError):
        GenerationConfig(max_new_tokens=0)

def test_generation_result_keeps_provider_and_model_identity():
    result = GenerationResult(text="{}", provider="test", model="model-a",
                              input_tokens=10, output_tokens=2)
    assert result.provider == "test"
    assert result.model == "model-a"
