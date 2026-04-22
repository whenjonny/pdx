from trumptrade.classifier import build_system_prompt


def test_system_prompt_deterministic():
    playbook = {
        "categories": {
            "tariff_china": {"description": "tariffs on china", "keywords": ["china", "tariff"]},
            "crypto_friendly": {"description": "pro crypto", "keywords": ["bitcoin"]},
        },
        "follow_through_priors": {
            "tariff_threat_to_imposition_90d": 0.45,
            "executive_order_promise_to_signature_30d": 0.70,
        },
    }
    p1 = build_system_prompt(playbook)
    p2 = build_system_prompt(playbook)
    # Must be byte-stable for prompt caching
    assert p1 == p2


def test_system_prompt_key_order_deterministic():
    """Changing the dict insertion order must not change the rendered prompt."""
    a = {
        "categories": {"b": {"description": "B"}, "a": {"description": "A"}},
        "follow_through_priors": {"y": 0.1, "x": 0.2},
    }
    b = {
        "categories": {"a": {"description": "A"}, "b": {"description": "B"}},
        "follow_through_priors": {"x": 0.2, "y": 0.1},
    }
    assert build_system_prompt(a) == build_system_prompt(b)
