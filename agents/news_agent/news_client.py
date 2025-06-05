import aiohttp
from typing import Optional, Dict, Any
from loguru import logger

class NewsAPIClient:
    def __init__(self, api_key: str, base_url: str = "https://newsapi.org/v2"):
        self.api_key = api_key
        self.base_url = base_url

    async def get_top_headlines(self, category: Optional[str] = None,
                                q: Optional[str] = None,
                                country: Optional[str] = "us") -> Dict[str, Any]:
        params = {
            "apiKey": self.api_key,
            "country": country,
        }
        if category:
            params["category"] = category
        if q:
            params["q"] = q

        url = f"{self.base_url}/top-headlines"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        logger.error(f"NewsAPI returned {resp.status}: {text}")
                        return {}
                    data = await resp.json()
                    return data
            except Exception as e:
                logger.error(f"Error fetching news: {e}")
                return {}
