from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from pydantic_settings import BaseSettings
import logging
import os

# 店舗Bot用のインポート
from app.api.line_webhook import router as store_webhook_router

# 薬剤師Bot用のインポート（統合版）
from integrated_pharmacist_webhook import router as pharmacist_webhook_router

class IntegratedSettings(BaseSettings):
    # 店舗Bot用
    line_channel_access_token: str = ""
    line_channel_secret: str = ""
    # 薬剤師Bot用
    pharmacist_line_channel_access_token: str = ""
    pharmacist_line_channel_secret: str = ""
    # Google Sheets設定
    google_sheets_credentials_file: str = "credentials.json"
    spreadsheet_id: str = ""
    # Redis設定
    redis_url: str = "redis://localhost:6379"
    # データベース設定
    database_url: str = "sqlite:///./pharmacy_schedule.db"
    # アプリケーション設定
    debug: bool = True
    secret_key: str = "integrated-bot-secret-key"
    environment: str = "development"
    # サーバー設定
    host: str = "0.0.0.0"
    port: int = 5000

    class Config:
        env_file = ".env"
        extra = "ignore"  # 追加のフィールドを無視

# 設定を読み込み
settings = IntegratedSettings()

# ログ設定を追加
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.FileHandler("integrated_main_debug.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
# 追加: root loggerのレベルを明示的に設定
logging.getLogger().setLevel(logging.INFO)
# 追加: 既存の全loggerのpropagateを有効化
for name in logging.root.manager.loggerDict:
    logging.getLogger(name).propagate = True

# FastAPIアプリを作成
app = FastAPI(
    title="Integrated Pharmacy Bot",
    description="統合薬局Bot（店舗Bot + 薬剤師Bot）",
    version="1.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーターを追加
app.include_router(store_webhook_router, tags=["store_bot"])
app.include_router(pharmacist_webhook_router, tags=["pharmacist_bot"])

@app.get("/")
async def root():
    return {
        "message": "Integrated Pharmacy Bot API",
        "endpoints": {
            "store_bot": "/line/webhook",
            "pharmacist_bot": "/pharmacist/line/webhook"
        }
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    # Railwayの環境変数に対応
    port = int(os.getenv("PORT", settings.port))
    uvicorn.run(
        "integrated_main:app",
        host=settings.host,
        port=port,
        reload=settings.debug
    ) 