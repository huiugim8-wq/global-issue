from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


class Settings:
    def __init__(self) -> None:
        self.app_env = os.getenv('APP_ENV', 'local').strip() or 'local'
        self.mongodb_uri = (os.getenv('MONGODB_URI') or os.getenv('MONGODB_URL') or '').strip()
        self.mongodb_db_name = os.getenv('MONGODB_DB_NAME', 'global_issue_map').strip() or 'global_issue_map'
        self.newsapi_api_key = os.getenv('NEWSAPI_API_KEY', '').strip()
        self.alpha_vantage_api_key = (os.getenv('ALPHA_VANTAGE_API_KEY') or os.getenv('ALPHAVANTAGE_API_KEY') or '').strip()
        self.finnhub_api_key = os.getenv('FINNHUB_API_KEY', '').strip()
        self.openai_api_key = os.getenv('OPENAI_API_KEY', '').strip()
        self.openai_model = os.getenv('OPENAI_MODEL', 'gpt-4.1-mini').strip() or 'gpt-4.1-mini'
        self.session_cookie_name = os.getenv('SESSION_COOKIE_NAME', 'gid_session').strip() or 'gid_session'
        self.allowed_origins = [
            origin.strip()
            for origin in os.getenv('ALLOWED_ORIGINS', 'http://127.0.0.1:8000,http://localhost:8000').split(',')
            if origin.strip()
        ]


settings = Settings()
