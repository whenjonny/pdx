from datetime import datetime, timezone
from trumptrade.classifier import fake_classify
from trumptrade.types import Signal


PLAYBOOK = {
    "categories": {
        "tariff_china": {
            "description": "tariffs on china",
            "keywords": ["china", "chinese", "tariff", "ccp"],
        },
        "crypto_friendly": {
            "description": "pro crypto",
            "keywords": ["bitcoin", "btc", "crypto"],
        },
    },
    "follow_through_priors": {
        "executive_order_promise_to_signature_30d": 0.70,
        "tariff_threat_to_imposition_90d": 0.45,
        "tweet_only_no_official_channel_30d": 0.20,
    },
}


def _sig(text):
    return Signal(id="s", author="x", timestamp=datetime.now(timezone.utc),
                  text=text, source="t")


def test_fake_classify_tariff_hawkish():
    c = fake_classify(_sig("Imposing 35% tariff on Chinese EVs"), PLAYBOOK)
    assert c.category == "tariff_china"
    assert c.sentiment == "hawkish"
    assert c.follow_through > 0.0
    assert c.confidence > 0.4


def test_fake_classify_tariff_dovish():
    c = fake_classify(_sig("Pause China tariffs to restart negotiations and reach a deal"),
                      PLAYBOOK)
    assert c.category == "tariff_china"
    assert c.sentiment == "dovish"


def test_fake_classify_crypto_signed_eo_high_follow_through():
    c = fake_classify(_sig("Just signed Executive Order on Strategic Bitcoin Reserve"), PLAYBOOK)
    assert c.category == "crypto_friendly"
    assert c.follow_through == 0.70


def test_fake_classify_unknown_topic():
    c = fake_classify(_sig("Beautiful weather at Mar-a-Lago today"), PLAYBOOK)
    assert c.category == "unknown"
    assert c.confidence == 0.0
