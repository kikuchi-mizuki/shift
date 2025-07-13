from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import logging
import re

from shared.services.google_sheets_service import GoogleSheetsService

# 統合設定から薬剤師Bot用の設定を取得
pharmacist_channel_access_token = os.getenv('PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN')
pharmacist_channel_secret = os.getenv('PHARMACIST_LINE_CHANNEL_SECRET')

# 薬剤師Bot用のLINE APIクライアントを作成
pharmacist_line_bot_api = LineBotApi(pharmacist_channel_access_token)
pharmacist_handler = WebhookHandler(pharmacist_channel_secret)

router = APIRouter(prefix="/pharmacist/line", tags=["pharmacist_line"])

logger = logging.getLogger(__name__)

@pharmacist_handler.add(MessageEvent, message=TextMessage)
def handle_pharmacist_message(event):
    with open("pharmacist_debug.txt", "a", encoding="utf-8") as f:
        f.write(f"handle_pharmacist_message called: {event.message.text}\n")
    
    """薬剤師Bot用のメッセージハンドラー"""
    # メッセージ本文から名前・電話番号を抽出（カンマ区切りまたは全角スペース区切り）
    text = event.message.text.strip()
    logger.info(f"Received pharmacist message: {text}")
    
    # 柔軟な区切り文字対応
    if re.search(r'[ ,、\u3000]', text):
        parts = re.split(r'[ ,、\u3000]+', text)
        if len(parts) >= 2:
            name = parts[0]
            phone = parts[1]
            user_id = event.source.user_id
            logger.info(f"Attempting to register pharmacist: name={name}, phone={phone}, user_id={user_id}")
            
            sheets_service = GoogleSheetsService()
            success = sheets_service.register_pharmacist_user_id(name, phone, user_id)
            
            if success:
                pharmacist_line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{name}さんのLINE IDを自動登録しました。今後はBotから通知が届きます。")
                )
                logger.info(f"Successfully registered pharmacist user_id for {name}")
            else:
                pharmacist_line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{name}さんの登録に失敗しました。名前・電話番号が正しいかご確認ください。")
                )
                logger.warning(f"Failed to register pharmacist user_id for {name}")
            return
    # 通常の応答
    guide_text = (
        "\U0001F3E5 薬局シフト管理Botへようこそ！\n\n"
        "このBotは薬局の勤務シフト管理を効率化します。\n\n"
        "\U0001F4CB 利用方法を選択してください：\n\n"
        "\U0001F3EA 【店舗の方】\n"
        "• 店舗登録がお済みでない方は、\n"
        "店舗登録、 店舗番号、店舗名を送信してください！\n"
        "例：店舗登録 002 サンライズ薬局\n\n"
        "\U0001F48A 【薬剤師の方】\n"
        "• 登録がお済みでない方は、\n"
        "お名前、電話番号を送信してください！\n"
        "例：田中薬剤師,090-1234-5678\n\n"
        "登録は簡単で、すぐに利用開始できます！"
    )
    pharmacist_line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=guide_text)
    )

@router.post("/webhook")
async def pharmacist_line_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get('X-Line-Signature', '')
    try:
        pharmacist_handler.handle(body.decode('utf-8'), signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    return {"status": "ok"} 