from fastapi import FastAPI
from app.api.line_webhook import router as store_router
from pharmacist_bot.api.webhook import router as pharmacist_router

app = FastAPI(
    title="統合シフト管理Bot",
    description="店舗Bot・薬剤師Botの両方のWebhookを統合したAPIサーバー",
    version="1.0.0"
)

app.include_router(store_router)
app.include_router(pharmacist_router)

@app.get("/")
async def root():
    return {"message": "統合シフト管理Bot", "status": "running"} 