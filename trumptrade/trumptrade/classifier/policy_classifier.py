from __future__ import annotations
import json
import logging
from typing import Any
import anthropic
from trumptrade.types import Signal, Classification

log = logging.getLogger(__name__)

_CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "sentiment": {"type": "string", "enum": ["hawkish", "dovish", "neutral"]},
        "follow_through": {"type": "number"},
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
        "original_excerpt": {"type": "string"},
    },
    "required": ["category", "sentiment", "follow_through", "rationale", "confidence", "original_excerpt"],
    "additionalProperties": False,
}


def build_system_prompt(playbook: dict) -> str:
    """Deterministic rendering of the playbook. Must be byte-stable across calls
    so prompt caching hits."""
    lines = [
        "You are a policy-signal classifier for a Trump-trading research tool.",
        "Given a post or statement (usually from Donald Trump or the White House),",
        "classify it against the playbook below and estimate follow-through probability.",
        "",
        "# Playbook categories",
    ]
    categories = playbook.get("categories", {})
    for name in sorted(categories.keys()):
        cat = categories[name]
        lines.append(f"\n## {name}")
        lines.append(f"Description: {cat.get('description', '')}")
        kw = cat.get("keywords") or []
        if kw:
            lines.append(f"Keywords: {', '.join(sorted(kw))}")

    lines.append("\n# Special category: `unknown`")
    lines.append("Use `unknown` if the post is off-topic, non-policy, or you cannot confidently map it.")

    lines.append("\n# Follow-through priors")
    priors = playbook.get("follow_through_priors", {})
    for k in sorted(priors.keys()):
        lines.append(f"- {k}: {priors[k]}")

    lines.append("""
# Instructions
- `category`: one of the playbook category keys, or `unknown`.
- `sentiment`:
    - `hawkish` = the statement PUSHES IN THE HARD DIRECTION of the category
      (e.g. tariff_china hawkish = announcing new tariffs; energy_oil_gas hawkish = pro-drilling;
       pharma_price_pressure hawkish = pushing price cuts).
    - `dovish` = the statement PULLS BACK from that direction.
    - `neutral` = ambiguous, mixed, or reaffirming status quo.
- `follow_through`: probability in [0, 1] that this statement leads to actual policy action
  within 30-90 days. Use the priors above and the channel (signed EO vs tweet vs rally speech).
- `confidence`: your own classifier confidence in [0, 1].
- `original_excerpt`: exact quoted sentence from the post that anchors your classification (<= 200 chars).
- `rationale`: 1-3 sentences explaining the call. Reference specific policy/ticker mapping when possible.

Output ONLY the JSON object that matches the schema. No preamble.
""")
    return "\n".join(lines)


def classify(
    signal: Signal,
    playbook: dict,
    client: anthropic.Anthropic | None = None,
    model: str = "claude-opus-4-7",
) -> Classification:
    client = client or anthropic.Anthropic()
    system_prompt = build_system_prompt(playbook)

    user_prompt = (
        f"Author: {signal.author}\n"
        f"Timestamp: {signal.timestamp.isoformat()}\n"
        f"Source: {signal.source}\n"
        f"URL: {signal.url or '(none)'}\n"
        "---\n"
        f"{signal.text}"
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {
                    "type": "json_schema",
                    "schema": _CLASSIFICATION_SCHEMA,
                },
            },
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )
        log.debug(
            "classifier usage: input=%d cache_read=%d cache_create=%d output=%d",
            response.usage.input_tokens,
            response.usage.cache_read_input_tokens,
            response.usage.cache_creation_input_tokens,
            response.usage.output_tokens,
        )
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            raise RuntimeError("classifier returned no text block")
        data = json.loads(text)
        return Classification(**data)
    except (anthropic.APIError, json.JSONDecodeError, ValueError) as e:
        log.warning("classification failed for signal %s: %s", signal.id, e)
        return Classification(
            category="unknown",
            sentiment="neutral",
            follow_through=0.0,
            rationale=f"classification error: {e}",
            confidence=0.0,
            original_excerpt=signal.text[:200],
        )
