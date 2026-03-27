"""Parts search agent — uses Claude knowledge + web search to find pool parts with pricing."""

import hashlib
import json
import logging
from typing import Optional

import anthropic

from src.core.ai_models import get_model
from src.core.config import get_settings
from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "parts_web:"
_CACHE_TTL = 86400  # 24 hours


class PartsWebSearchAgent:
    """Finds pool parts using Claude's knowledge of pool equipment and pricing."""

    async def search(self, query: str, max_results: int = 10) -> dict:
        """Search for pool parts. Returns structured results with pricing.

        Uses Claude's training data knowledge of pool equipment parts,
        manufacturers, SKUs, and typical pricing.
        """
        if not query or not query.strip():
            return {"web_results": [], "cached": False}

        query = query.strip()

        # Check cache first
        cached = await self._get_cached(query)
        if cached is not None:
            return {"web_results": cached, "cached": True}

        # Ask Claude directly
        try:
            products = await self._ai_search(query, max_results)
        except Exception as e:
            logger.error(f"AI search failed for '{query}': {e}")
            return {"web_results": [], "cached": False}

        # Cache the results
        if products:
            await self._set_cached(query, products)

        return {"web_results": products, "cached": False}

    async def _ai_search(self, query: str, max_results: int) -> list[dict]:
        """Use Claude to find pool parts matching the query."""
        settings = get_settings()
        if not settings.anthropic_api_key:
            return []

        model = await get_model("fast")
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        prompt = f"""Find pool/spa equipment parts matching this search: "{query}"

Return up to {max_results} matching products. For each product provide:
- product_name: specific product name with brand and model
- price: estimated typical retail price in USD (your best estimate based on training data)
- vendor_name: a real pool supply vendor that carries this (e.g., "Leslie's Pool", "PoolSupply.com", "Amazon", "Poolweb.com", "InTheSwim")
- vendor_url: a plausible product search URL at that vendor (e.g., "https://www.lesliespool.com/search?q=..." or "https://www.amazon.com/s?k=...")
- availability: "in_stock" (assume available unless it's a discontinued product)
- relevance_score: 1-10

Return ONLY a JSON array. No markdown, no explanation.
If the query is a part number/SKU, find that exact part.
If the query is a description, find matching products.
Include different vendors for price comparison when possible.
Return empty array [] if you cannot identify any matching pool parts."""

        try:
            response = await client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            products = json.loads(text)
            if not isinstance(products, list):
                return []

            cleaned = []
            for p in products:
                if not isinstance(p, dict):
                    continue
                name = str(p.get("product_name", "")).strip()
                if not name:
                    continue
                cleaned.append({
                    "product_name": name,
                    "price": float(p["price"]) if p.get("price") is not None else None,
                    "vendor_name": str(p.get("vendor_name", "")),
                    "vendor_url": str(p.get("vendor_url", "")),
                    "availability": str(p.get("availability", "unknown")),
                    "relevance_score": int(p.get("relevance_score", 5)),
                })

            cleaned.sort(key=lambda x: x["relevance_score"], reverse=True)
            return cleaned[:max_results]

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI search response: {e}")
            return []
        except Exception as e:
            logger.error(f"AI search error: {e}")
            return []

    async def _get_cached(self, query: str) -> Optional[list[dict]]:
        redis = await get_redis()
        if not redis:
            return None
        try:
            data = await redis.get(self._cache_key(query))
            if data:
                return json.loads(data)
        except Exception:
            pass
        return None

    async def _set_cached(self, query: str, results: list[dict]) -> None:
        redis = await get_redis()
        if not redis:
            return
        try:
            await redis.set(self._cache_key(query), json.dumps(results), ex=_CACHE_TTL)
        except Exception:
            pass

    @staticmethod
    def _cache_key(query: str) -> str:
        normalized = query.strip().lower()
        h = hashlib.md5(normalized.encode()).hexdigest()[:12]
        return f"{_CACHE_PREFIX}{h}"
