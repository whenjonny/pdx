from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.models.schemas import PredictionResponse
from app.services.blockchain import blockchain_service
from app.services.mirofish_client import mirofish_client, ScheduledMiroFishClient

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class TopicSuggestion(BaseModel):
    question: str
    category: str
    reasoning: str

class TopicSuggestionsResponse(BaseModel):
    topics: list[TopicSuggestion]


@router.get("/topics/suggest", response_model=TopicSuggestionsResponse)
async def suggest_topics(count: int = 5, category: str | None = None):
    """Generate market topic suggestions using LLM or return defaults."""
    from app.config import settings

    if settings.mirofish_llm_api_key:
        try:
            from openai import AsyncOpenAI
            import json

            client = AsyncOpenAI(
                api_key=settings.mirofish_llm_api_key,
                base_url=settings.mirofish_llm_base_url,
            )

            category_hint = f' in the "{category}" category' if category else ""
            prompt = f"""Suggest {count} prediction market questions{category_hint}. Each should be:
- A clear yes/no question about a future event
- Time-bound (include a deadline)
- Verifiable (can be objectively settled)

Return JSON array:
[{{"question": "...", "category": "crypto|politics|sports|tech|general", "reasoning": "why this is a good market"}}]

Only output valid JSON array, nothing else."""

            response = await client.chat.completions.create(
                model=settings.mirofish_llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=1000,
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            topics_data = json.loads(content)
            topics = [
                TopicSuggestion(
                    question=t["question"],
                    category=t.get("category", "general"),
                    reasoning=t.get("reasoning", ""),
                )
                for t in topics_data[:count]
            ]
            return TopicSuggestionsResponse(topics=topics)
        except Exception:
            pass

    # Fallback: return static topic suggestions
    defaults = [
        TopicSuggestion(question="Will Bitcoin exceed $150K by December 2026?", category="crypto", reasoning="BTC price prediction is a popular market topic"),
        TopicSuggestion(question="Will Ethereum complete the Pectra upgrade by Q3 2026?", category="crypto", reasoning="Major protocol upgrades are verifiable events"),
        TopicSuggestion(question="Will the US Federal Reserve cut rates before July 2026?", category="politics", reasoning="Monetary policy decisions are clearly verifiable"),
        TopicSuggestion(question="Will GPT-5 be publicly released by end of 2026?", category="tech", reasoning="Major AI model releases are trackable events"),
        TopicSuggestion(question="Will any team break the FIFA World Cup attendance record in 2026?", category="sports", reasoning="Sports records are objectively verifiable"),
    ]
    filtered = [t for t in defaults if not category or t.category == category.lower()]
    return TopicSuggestionsResponse(topics=filtered[:count])


@router.get("/{market_id}", response_model=PredictionResponse)
async def get_prediction(market_id: int):
    """Get MiroFish probability prediction for a market."""
    market = blockchain_service.get_market(market_id)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    current_yes_price = market.priceYes

    # Use async method if available (ScheduledMiroFishClient)
    if isinstance(mirofish_client, ScheduledMiroFishClient):
        prediction = await mirofish_client.get_prediction_async(market_id, current_yes_price)
    else:
        prediction = mirofish_client.get_prediction(market_id, current_yes_price)

    # Always include current AMM price
    prediction.amm_price_yes = current_yes_price
    return prediction
