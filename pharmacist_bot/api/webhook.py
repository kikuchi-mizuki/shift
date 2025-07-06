from fastapi import APIRouter, Request, HTTPException
from linebot.exceptions import InvalidSignatureError
from pharmacist_bot.services.line_bot_service import pharmacist_line_bot_service
from linebot.models import TextSendMessage

router = APIRouter(prefix="/pharmacist/line", tags=["pharmacist_line"])

@router.post("/webhook")
async def pharmacist_line_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get('X-Line-Signature', '')
    try:
        pharmacist_line_bot_service.handler.handle(body.decode('utf-8'), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return {"status": "ok"}

def send_guide_message(event):
    guide_text = (
        "🏥 薬局シフト管理Botへようこそ！\n\n"
        "このBotは薬局の勤務シフト管理を効率化します。\n\n"
        "📋 利用方法を選択してください：\n\n"
        "🏪 【店舗の方】\n"
        "• 店舗登録がお済みでない方\n"
        "→ 「店舗番号」＋「店舗名」を送信\n"
        "• 勤務依頼の送信\n"
        "→「勤務依頼」と送信\n\n"
        "💊 【薬剤師の方】\n"
        "• 店舗登録がお済みでない方\n"
        "→ 「お名前」＋「電話番号」を送信\n"
        "・店舗からシフト依頼が届くまでお待ちください！\n\n"
        "どちらを選択されますか？\n"
        "登録は簡単で、すぐに利用開始できます！"
    )
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=guide_text)) 