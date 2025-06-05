# multi_agent_system/agents/weather_agent/weather_client.py

from typing import Dict, Any, Optional
from loguru import logger
from protocols.communication import AsyncCommManager # Assuming comm_manager is passed or imported

class WeatherClient:
    def __init__(self, api_key: str, base_url: str, comm_manager: AsyncCommManager):
        self.api_key = api_key
        self.base_url = base_url
        self.comm_manager = comm_manager
        logger.info(f"WeatherClient initialized with base URL: {base_url}")

    async def get_current_weather(self, location: str) -> Optional[Dict[str, Any]]:
        """
        Fetches current weather data for a given location.
        Uses WeatherAPI.com (free tier) as an example.
        """
        endpoint = f"{self.base_url}/current.json"
        params = {
            "key": self.api_key,
            "q": location
        }
        try:
            data = await self.comm_manager.get(endpoint, params=params)
            logger.debug(f"WeatherAPI current weather response for {location}: {data}")
            return data
        except Exception as e:
            logger.error(f"Failed to fetch current weather for {location}: {e}")
            return None

    async def get_weather_forecast(self, location: str, days: int = 3) -> Optional[Dict[str, Any]]:
        """
        Fetches weather forecast data for a given location and number of days.
        Uses WeatherAPI.com (free tier) as an example.
        """
        if not (1 <= days <= 10): # Free tier limit is often 10 days
            logger.warning(f"Forecast days ({days}) out of supported range (1-10). Defaulting to 3.")
            days = 3

        endpoint = f"{self.base_url}/forecast.json"
        params = {
            "key": self.api_key,
            "q": location,
            "days": days
        }
        try:
            data = await self.comm_manager.get(endpoint, params=params)
            logger.debug(f"WeatherAPI forecast response for {location} ({days} days): {data}")
            return data
        except Exception as e:
            logger.error(f"Failed to fetch weather forecast for {location} ({days} days): {e}")
            return None