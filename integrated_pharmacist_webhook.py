from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import logging

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
    
    # 区切り文字を検出（カンマ、全角スペース、半角スペース）
    separator = None
    if "," in text:
        separator = ","
    elif "　" in text:  # 全角スペース
        separator = "　"
    elif " " in text:   # 半角スペース
        separator = " "
    
    if separator:
        try:
            name, phone = [s.strip() for s in text.split(separator, 1)]
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
        except Exception as e:
            logger.error(f"Error in pharmacist registration: {e}")
            pharmacist_line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="登録処理中にエラーが発生しました。")
            )
            return
    
    # 通常の応答
    pharmacist_line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"薬剤師Bot: {event.message.text} を受信しました")
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