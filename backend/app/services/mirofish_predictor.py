"""MiroFish prediction engine — LLM mode + heuristic fallback."""

import json
import logging
import time

from app.config import settings

logger = logging.getLogger("mirofish")


async def analyze_market(
    market_id: int,
    question: str,
    evidence_list: list[dict],
) -> dict:
    """Analyze a market and return prediction dict.

    Returns dict with keys: probability_yes, confidence, reasoning, source
    """
    if settings.mirofish_llm_api_key:
        try:
            return await _llm_analyze(market_id, question, evidence_list)
        except Exception as e:
            logger.warning("LLM analysis failed for market %d: %s, falling back to heuristic", market_id, e)

    return _heuristic_analyze(market_id, question, evidence_list)


async def _llm_analyze(
    market_id: int,
    question: str,
    evidence_list: list[dict],
) -> dict:
    """Use OpenAI-compatible LLM to analyze market."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.mirofish_llm_api_key,
        base_url=settings.mirofish_llm_base_url,
    )

    evidence_text = ""
    for i, ev in enumerate(evidence_list, 1):
        direction = ev.get("direction", "")
        title = ev.get("title", "")
        content = ev.get("content", "")
        source_url = ev.get("source_url", "")
        summary = ev.get("summary", "")

        # Use full content if available, otherwise fall back to summary
        if content:
            ev_line = f"\n{i}. [{direction}] {title}: {content}"
            if source_url:
                ev_line += f" (source: {source_url})"
        else:
            ev_line = f"\n{i}. {summary}"
        evidence_text += ev_line

    if not evidence_text:
        evidence_text = "\nNo evidence submitted yet."

    prompt = f"""You are a probability analyst for a prediction market. Analyze the following market question and evidence to estimate the probability of the YES outcome.

Market Question: {question}

Submitted Evidence (each prefixed with [YES] or [NO] indicating the submitter's stance):{evidence_text}

Based on the evidence above, provide your analysis as JSON:
{{
  "probability_yes": <float between 0.05 and 0.95>,
  "confidence": <float between 0.0 and 1.0, how confident you are>,
  "reasoning": "<brief 1-2 sentence explanation>"
}}

Only output valid JSON, nothing else."""

    response = await client.chat.completions.create(
        model=settings.mirofish_llm_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=300,
    )

    content = response.choices[0].message.content.strip()
    # Try to extract JSON from response
    if content.startswith("```"):
        content = content.split("```")[1]
        if content.startswith("json"):
            content = content[4:]

    data = json.loads(content)
    prob = max(0.05, min(0.95, float(data["probability_yes"])))
    conf = max(0.0, min(1.0, float(data["confidence"])))

    return {
        "probability_yes": round(prob, 4),
        "confidence": round(conf, 2),
        "reasoning": data.get("reasoning", "LLM analysis complete."),
        "source": "MiroFish AI",
    }


def _heuristic_analyze(
    market_id: int,
    question: str,
    evidence_list: list[dict],
) -> dict:
    """Evidence-based heuristic when no LLM available."""
    if not evidence_list:
        return {
            "probability_yes": 0.5,
            "confidence": 0.1,
            "reasoning": "No evidence submitted yet. Defaulting to neutral probability.",
            "source": "MiroFish Heuristic",
        }

    # Use explicit direction from IPFS when available, fall back to keyword detection
    yes_weight = 0.0
    no_weight = 0.0
    now = time.time()

    positive_keywords = ["yes", "will", "likely", "confirm", "support", "positive", "agree", "pass", "approve", "succeed", "increase", "rise", "win"]
    negative_keywords = ["no", "won't", "unlikely", "deny", "oppose", "negative", "disagree", "fail", "reject", "decrease", "fall", "lose"]

    for ev in evidence_list:
        ts = ev.get("timestamp", 0)
        # Recency weight: more recent evidence has more weight
        age_days = max(0, (now - ts) / 86400) if ts > 0 else 30
        recency = 1.0 / (1.0 + age_days * 0.1)

        direction = ev.get("direction", "").upper()
        if direction == "YES":
            yes_weight += recency
        elif direction == "NO":
            no_weight += recency
        else:
            # No explicit direction — fall back to keyword analysis
            text = (ev.get("content", "") or ev.get("summary", "")).lower()
            yes_score = sum(1 for kw in positive_keywords if kw in text)
            no_score = sum(1 for kw in negative_keywords if kw in text)

            if yes_score > no_score:
                yes_weight += recency
            elif no_score > yes_score:
                no_weight += recency
            else:
                yes_weight += recency * 0.5
                no_weight += recency * 0.5

    total = yes_weight + no_weight
    if total == 0:
        prob = 0.5
    else:
        prob = 0.5 + 0.4 * (yes_weight - no_weight) / total

    prob = max(0.05, min(0.95, prob))

    # Confidence based on evidence count
    n = len(evidence_list)
    if n <= 2:
        confidence = 0.3
    elif n <= 5:
        confidence = 0.5
    elif n <= 10:
        confidence = 0.65
    else:
        confidence = 0.8

    direction = "YES" if prob > 0.5 else "NO" if prob < 0.5 else "neutral"
    return {
        "probability_yes": round(prob, 4),
        "confidence": confidence,
        "reasoning": f"Heuristic analysis of {n} evidence items suggests {direction} outcome at {prob:.0%}.",
        "source": "MiroFish Heuristic",
    }
