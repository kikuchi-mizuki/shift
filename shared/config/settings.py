import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LINE Bot設定（店舗Bot用）
    line_channel_access_token: Optional[str] = None
    line_channel_secret: Optional[str] = None
    
    # LINE Bot設定（薬剤師Bot用）
    pharmacist_line_channel_access_token: Optional[str] = None
    pharmacist_line_channel_secret: Optional[str] = None
    
    # Google Sheets設定（共有）
    google_sheets_credentials_file: str = "credentials.json"
    spreadsheet_id: Optional[str] = None
    
    # Redis設定（共有）
    redis_url: str = "redis://localhost:6379"
    
    # データベース設定（共有）
    database_url: str = "sqlite:///./pharmacy_schedule.db"
    
    # アプリケーション設定（共有）
    debug: bool = True
    secret_key: str = "your-secret-key-here"
    environment: str = "development"
    
    # シフト設定（共有）
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
    
    class Config:
        env_file = ".env"


# 共有設定インスタンス
shared_settings = Settings() 