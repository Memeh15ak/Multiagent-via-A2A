# multi_agent_system/agents/web_search_agent/duckduckgo_search_client.py

import httpx
from loguru import logger
from typing import Dict, Any

# Import the AsyncCommManager instance for communication/logging if needed
from protocols.communication import comm_manager

class DuckDuckGoSearchClient:
    def __init__(self, comm_manager=comm_manager):
        self.base_search_url = "https://duckduckgo.com/?q="
        self.search_api_url = "https://api.duckduckgo.com/?q="  # For Instant Answers API
        self.comm_manager = comm_manager  # Use the shared AsyncCommManager instance
        logger.info("DuckDuckGoSearchClient initialized.")

    async def search_web(self, query: str) -> Dict[str, Any]:
        """
        Performs a web search using DuckDuckGo's Instant Answer API.
        Returns structured results mapped into a common format.
        """
        full_url = f"{self.search_api_url}{query}&format=json&nohtml=1&noredirect=1&skip_disambig=1"
        logger.info(f"Searching DuckDuckGo with query: {query}")
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(full_url, follow_redirects=True, timeout=10)
                response.raise_for_status()
                data = response.json()

                web_results_formatted = []

                if data.get("Results"):
                    for res in data["Results"]:
                        web_results_formatted.append({
                            "title": res.get("Text"),
                            "url": res.get("FirstURL"),
                            "description": res.get("Text")  # Short description
                        })
                elif data.get("Abstract"):
                    web_results_formatted.append({
                        "title": data.get("Heading", query),
                        "url": data.get("AbstractURL", f"https://duckduckgo.com/?q={query}"),
                        "description": data.get("Abstract")
                    })

                if data.get("RelatedTopics"):
                    for topic in data["RelatedTopics"]:
                        if "Text" in topic:
                            web_results_formatted.append({
                                "title": topic.get("Text", ""),
                                "url": topic.get("FirstURL", ""),
                                "description": topic.get("Text", "")
                            })

                return {
                    "web": {
                        "results": web_results_formatted
                    }
                }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error searching DuckDuckGo: {e.response.status_code} - {e.response.text}")
            return {"error": f"HTTP error: {e.response.status_code}"}
        except httpx.RequestError as e:
            logger.error(f"Network error searching DuckDuckGo: {e}")
            return {"error": f"Network error: {e}"}
        except Exception as e:
            logger.error(f"Unexpected error while searching DuckDuckGo: {e}", exc_info=True)
            return {"error": f"Unexpected error: {e}"}
