from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("/line/webhook")
async def line_webhook(request: Request):
    body = await request.body()
    print("LINEから受信:", body)
    return JSONResponse(content={"status": "ok"}, status_code=200)