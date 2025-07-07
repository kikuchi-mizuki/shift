import os
from typing import Optional
from pydantic_settings import BaseSettings


class PharmacistBotSettings(BaseSettings):
    # 店舗Bot用（未使用だが.envに存在するため定義）
    line_channel_access_token: str
    line_channel_secret: str
    # 薬剤師Bot用
    pharmacist_line_channel_access_token: str
    pharmacist_line_channel_secret: str
    # Google Sheets設定
    google_sheets_credentials_file: str = "credentials.json"
    spreadsheet_id: str
    # Redis設定
    redis_url: str = "redis://localhost:6379"
    # データベース設定
    database_url: str = "sqlite:///./pharmacy_schedule.db"
    # アプリケーション設定
    debug: bool = True
    secret_key: str = "pharmacist-bot-secret-key"
    environment: str = "development"
    # サーバー設定
    host: str = "0.0.0.0"
    port: int = 8002
    
    # 本番環境判定
    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"
    
    # 開発環境判定
    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"
    
    class Config:
        env_file = ".env"


pharmacist_settings = PharmacistBotSettings() 