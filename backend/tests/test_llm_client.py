from types import SimpleNamespace

from app.agent.llm_client import TokenUsage


def sdk_usage(input_tokens, output_tokens, thought_tokens, total_tokens):
    """Stand-in for the SDK's interaction.usage: only the fields TokenUsage reads."""
    return SimpleNamespace(
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        total_thought_tokens=thought_tokens,
        total_tokens=total_tokens,
    )


def test_usage_adds_up_over_calls():
    usage = TokenUsage()

    usage.add(sdk_usage(600, 90, 300, 990))
    usage.add(sdk_usage(610, 80, 250, 940))

    assert usage.calls == 2
    assert usage.input_tokens == 1210
    assert usage.thought_tokens == 550
    assert usage.total_tokens == 1930


def test_missing_usage_still_counts_the_call():
    """The SDK types usage and each field as Optional: None must not crash or add anything."""
    usage = TokenUsage()

    usage.add(None)
    usage.add(sdk_usage(600, None, None, 600))

    assert usage.calls == 2
    assert usage.input_tokens == 600
    assert usage.output_tokens == 0
