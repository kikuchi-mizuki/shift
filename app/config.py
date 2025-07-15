import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 店舗Bot用LINE設定
    line_channel_access_token: str = ""
    line_channel_secret: str = ""
    
    # Google Sheets設定
    google_sheets_credentials_file: str = "credentials.json"
    spreadsheet_id: str = ""
    
    # Redis設定
    redis_url: str = "redis://localhost:6379"
    
    # データベース設定
    database_url: str = "sqlite:///./pharmacy_schedule.db"
    
    # アプリケーション設定
    debug: bool = True
    secret_key: str = "your-secret-key-here"
    environment: str = "development"
    
    # シフト設定
    max_pharmacists_per_shift: int = 3
    shift_time_slots: list = ["AM", "PM", "終日"]
    
    # 本番環境判定
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    # 開発環境判定
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"
    
    # 薬剤師Bot用LINE設定
    pharmacist_line_channel_access_token: str = ""
    pharmacist_line_channel_secret: str = ""
    
    class Config:
        env_file = ".env"
        # 環境変数名のマッピング
        fields = {
            "line_channel_access_token": {"env": "STORE_LINE_CHANNEL_ACCESS_TOKEN"},
            "line_channel_secret": {"env": "STORE_LINE_CHANNEL_SECRET"},
            "pharmacist_line_channel_access_token": {"env": "PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN"},
            "pharmacist_line_channel_secret": {"env": "PHARMACIST_LINE_CHANNEL_SECRET"},
            "spreadsheet_id": {"env": "SPREADSHEET_ID"},
            "debug": {"env": "DEBUG"},
            "environment": {"env": "ENVIRONMENT"},
            "secret_key": {"env": "SECRET_KEY"}
        }


settings = Settings() 