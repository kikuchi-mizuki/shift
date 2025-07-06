import os
from typing import Optional
from pydantic_settings import BaseSettings


class StoreBotSettings(BaseSettings):
    # LINE Bot設定（店舗専用）
    store_line_channel_access_token: str
    store_line_channel_secret: str
    
    # アプリケーション設定
    debug: bool = True
    secret_key: str = "store-bot-secret-key"
    environment: str = "development"
    
    # サーバー設定
    host: str = "0.0.0.0"
    port: int = 8001  # 店舗Bot用ポート
    
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


store_settings = StoreBotSettings() 