from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from store_bot.api.webhook import router as store_webhook_router
from store_bot.config import store_settings

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# FastAPIアプリケーション作成
app = FastAPI(
    title="薬局シフト管理Bot（店舗版）",
    description="薬局の勤務依頼管理を効率化するLINE Bot",
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

# ルーターの追加
app.include_router(store_webhook_router)

@app.get("/")
async def root():
    return {
        "message": "薬局シフト管理Bot（店舗版）",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "store_bot.main:app",
        host=store_settings.host,
        port=store_settings.port,
        reload=store_settings.debug
    ) 