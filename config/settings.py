# config/settings.py
import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict
from loguru import logger
from typing import Dict, Any, Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
   
    # Application settings
    APP_NAME: str = "Agent Server"
    API_V1_STR: str = "/api/v1"
    
    # Environment and debug settings (MISSING FIELDS ADDED)
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
   
    # API Keys and URLs
    NEWS_API_KEY: str = ""
    NEWS_API_BASE_URL: str = "https://newsapi.org/v2"
    WEATHER_API_KEY: str = ""
    WEATHER_API_BASE_URL: str = "https://api.weatherapi.com/v1"
   
    # Server configuration
    AGENT_SERVER_HOST: str = "127.0.0.1"
    AGENT_SERVER_PORT: int = 8000
    WEBSOCKET_PORT: int = 8001
   
    # Perplexity AI settings
    PERPLEXITY_API_KEY: str = ""
    PERPLEXITY_MODEL: str = "llama-3.1-sonar-small-128k-online"
    PERPLEXITY_BASE_URL: str = "https://api.perplexity.ai"
   
    def load_agent_config(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """Load agent configuration from YAML file."""
        try:
            with open("config/agent_config.yaml", "r") as f:
                data = yaml.safe_load(f)
           
            config = data.get("agents", {}).get(agent_name)
            if not config:
                logger.warning(f"Agent config for '{agent_name}' not found in YAML.")
                return None
           
            logger.info(f"Loaded config for agent '{agent_name}': {config}")
            return config
           
        except FileNotFoundError:
            logger.error(f"Agent config file 'config/agent_config.yaml' not found.")
            return None
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML config: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading agent config: {e}")
            return None
   
    def get_agent_endpoint(self, agent_name: str) -> Optional[str]:
        """Get the A2A endpoint for a specific agent."""
        config = self.load_agent_config(agent_name)
        if config:
            return config.get("a2a_endpoint")
        return None
   
    def get_agent_port(self, agent_name: str) -> Optional[int]:
        """Extract port from agent's a2a_endpoint."""
        endpoint = self.get_agent_endpoint(agent_name)
        if endpoint:
            try:
                # Extract port from URL like "http://127.0.0.1:5001/a2a"
                port_str = endpoint.split(":")[-1].split("/")[0]
                return int(port_str)
            except (ValueError, IndexError) as e:
                logger.error(f"Failed to extract port from endpoint {endpoint}: {e}")
                return None
        return None
   
    def validate_required_keys(self) -> bool:
        """Validate that required API keys are present."""
        missing_keys = []
       
        if not self.WEATHER_API_KEY:
            missing_keys.append("WEATHER_API_KEY")
        if not self.PERPLEXITY_API_KEY:
            missing_keys.append("PERPLEXITY_API_KEY")
       
        if missing_keys:
            logger.warning(f"Missing required API keys: {', '.join(missing_keys)}")
            return False
       
        return True

# Create the global settings instance
settings = Settings()