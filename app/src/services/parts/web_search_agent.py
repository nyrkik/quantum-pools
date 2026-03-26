"""Parts web search agent — searches the web for pool parts and extracts structured results."""

import hashlib
import json
import logging
from typing import Optional

import anthropic
from duckduckgo_search import DDGS

from src.core.ai_models import get_model
from src.core.config import get_settings
from src.core.redis_client import get_redis

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "parts_web:"
_CACHE_TTL = 86400  # 24 hours

# Domains to filter out (not product pages)
_BLOCKED_DOMAINS = {
    "youtube.com", "reddit.com", "facebook.com", "twitter.com",
    "instagram.com", "tiktok.com", "pinterest.com", "quora.com",
    "wikipedia.org", "wikihow.com",
}

_EXTRACTION_PROMPT = """Given these web search results for pool equipment/parts, extract product listings.

Search query: {query}

Results:
{formatted_results}

Extract each product you can identify. Return ONLY a JSON array (no markdown, no explanation):
[{{
  "product_name": "exact product name",
  "price": 123.45,
  "vendor_name": "store name",
  "vendor_url": "direct URL to product page",
  "availability": "in_stock",
  "relevance_score": 8
}}]

Rules:
- Only include actual product listings, not articles/reviews/forums
- price: float or null if not visible in the snippet
- vendor_name: the store (e.g., "Amazon", "Leslie's Pool", "Poolweb", "InTheSwim")
- availability: "in_stock" or "out_of_stock" or "unknown"
- relevance_score: 1-10 (how well it matches the search query)
- If a result is a category page not a specific product, skip it
- Sort by relevance_score descending
- Return empty array [] if no products found"""


class PartsWebSearchAgent:
    """Searches the web for pool parts and returns structured results with pricing."""

    async def search(self, query: str, max_results: int = 10) -> dict:
        """Search web for pool parts, extract structured data, cache results.

        Returns dict with web_results list and cached flag.
        """
        if not query or not query.strip():
            return {"web_results": [], "cached": False}

        query = query.strip()

        # Check cache first
        cached = await self._get_cached(query)
        if cached is not None:
            return {"web_results": cached, "cached": True}

        # Search the web
        try:
            raw_results = await self._web_search(query, max_results=max_results * 2)
        except Exception as e:
            logger.error(f"Web search failed for '{query}': {e}")
            return {"web_results": [], "cached": False}

        if not raw_results:
            return {"web_results": [], "cached": False}

        # Extract structured product data via Claude
        try:
            products = await self._extract_products(query, raw_results)
        except Exception as e:
            logger.error(f"Product extraction failed for '{query}': {e}")
            return {"web_results": [], "cached": False}

        # Limit to requested count
        products = products[:max_results]

        # Cache the results
        await self._set_cached(query, products)

        return {"web_results": products, "cached": False}

    async def _web_search(self, query: str, max_results: int = 20) -> list[dict]:
        """Execute DuckDuckGo search, return raw results."""
        search_query = f"{query} pool supply buy price"
        results = []

        try:
            with DDGS() as ddgs:
                for r in ddgs.text(search_query, max_results=max_results):
                    # Filter blocked domains
                    href = r.get("href", "")
                    if any(d in href for d in _BLOCKED_DOMAINS):
                        continue
                    # Filter PDFs
                    if href.lower().endswith(".pdf"):
                        continue
                    results.append({
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                        "url": href,
                    })
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            raise

        return results

    async def _extract_products(self, query: str, raw_results: list[dict]) -> list[dict]:
        """Use Claude Haiku to extract structured product data from search results."""
        settings = get_settings()
        if not settings.anthropic_api_key:
            logger.warning("No Anthropic API key — cannot extract products")
            return []

        # Format results for the prompt
        formatted = ""
        for i, r in enumerate(raw_results, 1):
            formatted += f"\n{i}. **{r['title']}**\n   URL: {r['url']}\n   {r['snippet']}\n"

        prompt = _EXTRACTION_PROMPT.format(query=query, formatted_results=formatted)
        model = await get_model("fast")

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse the JSON response
            text = response.content[0].text.strip()
            # Handle potential markdown code blocks
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            products = json.loads(text)
            if not isinstance(products, list):
                logger.warning(f"Expected list from extraction, got {type(products)}")
                return []

            # Validate and clean each product
            cleaned = []
            for p in products:
                if not isinstance(p, dict):
                    continue
                cleaned.append({
                    "product_name": str(p.get("product_name", "")),
                    "price": float(p["price"]) if p.get("price") is not None else None,
                    "vendor_name": str(p.get("vendor_name", "")),
                    "vendor_url": str(p.get("vendor_url", "")),
                    "availability": str(p.get("availability", "unknown")),
                    "relevance_score": int(p.get("relevance_score", 5)),
                })

            # Sort by relevance
            cleaned.sort(key=lambda x: x["relevance_score"], reverse=True)
            return cleaned

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse extraction response: {e}")
            return []
        except Exception as e:
            logger.error(f"Claude extraction error: {e}")
            return []

    async def _get_cached(self, query: str) -> Optional[list[dict]]:
        """Check Redis cache for previous results."""
        redis = await get_redis()
        if not redis:
            return None
        try:
            key = self._cache_key(query)
            data = await redis.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            logger.debug(f"Cache read error: {e}")
        return None

    async def _set_cached(self, query: str, results: list[dict]) -> None:
        """Cache results in Redis with 24h TTL."""
        redis = await get_redis()
        if not redis:
            return
        try:
            key = self._cache_key(query)
            await redis.set(key, json.dumps(results), ex=_CACHE_TTL)
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

    @staticmethod
    def _cache_key(query: str) -> str:
        """Generate a deterministic cache key from the query."""
        normalized = query.strip().lower()
        h = hashlib.md5(normalized.encode()).hexdigest()[:12]
        return f"{_CACHE_PREFIX}{h}"
