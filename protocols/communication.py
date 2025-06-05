# multi_agent_system/protocols/communication.py

import httpx
from typing import Dict, Any, Optional
from loguru import logger
import asyncio
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

class AsyncCommManager:
    def __init__(self):
        # httpx.AsyncClient is recommended for persistent connections and better performance
        self._client = httpx.AsyncClient(timeout=30.0) # Global timeout for all requests
        logger.info("AsyncCommManager initialized.")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(httpx.NetworkError))
    async def get(self, url: str, headers: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Performs an asynchronous GET request."""
        try:
            logger.debug(f"Making GET request to: {url} with params: {params}")
            response = await self._client.get(url, headers=headers, params=params)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error on GET {url}: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error on GET {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during GET {url}: {e}", exc_info=True)
            raise

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(httpx.NetworkError))
    async def post(self, url: str, headers: Optional[Dict] = None, json_data: Optional[Dict] = None, data: Optional[Any] = None) -> Dict[str, Any]:
        """Performs an asynchronous POST request."""
        try:
            logger.debug(f"Making POST request to: {url} with json: {json_data}")
            response = await self._client.post(url, headers=headers, json=json_data, data=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error on POST {url}: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error on POST {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during POST {url}: {e}", exc_info=True)
            raise

    async def close(self):
        """Closes the underlying httpx client."""
        await self._client.aclose()
        logger.info("AsyncCommManager client closed.")

comm_manager = AsyncCommManager()