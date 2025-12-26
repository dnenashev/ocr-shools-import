from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # OpenRouter API
    openrouter_api_key: str = ""
    
    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "ocr_crm"
    
    # AMO CRM
    amo_domain: str = ""  # например: pk1amomabiuru.amocrm.ru
    amo_secret_key: str = ""  # AMO_SECRET_KEY
    amo_redirect_uri: str = ""  # AMO_REDIRECT_URI (домен AMO)
    integration_id: str = ""  # INTEGRATION_ID
    amo_long_token: str = ""  # AMO_LONG_TOKEN (access token)
    amo_short_key: str = ""  # AMO_SHORT_KEY (refresh token)
    amo_correct_pipeline_id: int = 7797890  # Правильная воронка для сделок
    
    # Admin Panel
    admin_password: str = "admin"
    secret_key: str = "change-me-in-production"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()

