import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os

from app.config import settings
from app.api.line_webhook import router as line_webhook_router
from app.api.schedule import router as schedule_router

# 薬剤師Bot用のインポート
from integrated_pharmacist_webhook import router as pharmacist_webhook_router

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# FastAPIアプリケーションの作成
app = FastAPI(
    title="フリーランス薬剤師シフト調整自動化システム",
    description="LINE BotとGoogle Sheetsを連携した薬剤師シフト調整システム",
    version="1.0.0"
)

# CORS設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本番環境では適切に制限してください
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーターの追加
app.include_router(line_webhook_router)  # 店舗Bot: /line/webhook
app.include_router(schedule_router)
app.include_router(pharmacist_webhook_router)  # 薬剤師Bot: /pharmacist/line/webhook


@app.get("/")
async def root():
    """ルートエンドポイント"""
    return {
        "message": "フリーランス薬剤師シフト調整自動化システム",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "store_bot": "/line/webhook",
            "pharmacist_bot": "/pharmacist/line/webhook"
        }
    }


@app.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    return {"status": "healthy"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """グローバル例外ハンドラー"""
    logging.error(f"Global exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))  # RailwayのPORT環境変数を優先
    debug = os.getenv("DEBUG", "false").lower() == "true"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=debug
    ) 