from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import os
import logging
import re
from datetime import datetime

from shared.services.google_sheets_service import GoogleSheetsService

# 統合設定から薬剤師Bot用の設定を取得
pharmacist_channel_access_token = os.getenv('PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN')
pharmacist_channel_secret = os.getenv('PHARMACIST_LINE_CHANNEL_SECRET')

print(f"[DEBUG] Pharmacist Bot Config: token_length={len(pharmacist_channel_access_token) if pharmacist_channel_access_token else 0}, secret_length={len(pharmacist_channel_secret) if pharmacist_channel_secret else 0}")
print(f"[DEBUG] Pharmacist Bot Config: token_exists={pharmacist_channel_access_token is not None}, secret_exists={pharmacist_channel_secret is not None}")

if not pharmacist_channel_access_token:
    print("[DEBUG] WARNING: PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN is not set!")
if not pharmacist_channel_secret:
    print("[DEBUG] WARNING: PHARMACIST_LINE_CHANNEL_SECRET is not set!")

# 薬剤師Bot用のLINE APIクライアントを作成
pharmacist_line_bot_api = LineBotApi(pharmacist_channel_access_token)
pharmacist_handler = WebhookHandler(pharmacist_channel_secret)

router = APIRouter(prefix="/pharmacist/line", tags=["pharmacist_line"])

logger = logging.getLogger(__name__)

def log_debug(message):
    """デバッグログをファイルに書き込む"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("pharmacist_debug.txt", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[DEBUG] {message}")

@pharmacist_handler.add(MessageEvent, message=TextMessage)
def handle_pharmacist_message(event):
    user_id = event.source.user_id
    text = event.message.text.strip()
    
    log_debug(f"Pharmacist message received: user_id={user_id}, text='{text}'")
    logger.info(f"Received pharmacist message from {user_id}: {text}")
    
    """薬剤師Bot用のメッセージハンドラー"""
    # メッセージ本文から名前・電話番号を抽出（カンマ区切りまたは全角スペース区切り）
    logger.info(f"Received pharmacist message: {text}")
    
    # 柔軟な区切り文字対応
    if re.search(r'[ ,、\u3000]', text):
        parts = re.split(r'[ ,、\u3000]+', text)
        log_debug(f"Parsed parts: {parts}")
        
        if len(parts) >= 2:
            name = parts[0]
            phone = parts[1]
            user_id = event.source.user_id
            
            log_debug(f"Processing pharmacist registration: name='{name}', phone='{phone}', user_id='{user_id}'")
            logger.info(f"Attempting to register pharmacist: name={name}, phone={phone}, user_id={user_id}")
            
            try:
                sheets_service = GoogleSheetsService()
                log_debug(f"GoogleSheetsService initialized successfully")
                
                success = sheets_service.register_pharmacist_user_id(name, phone, user_id)
                log_debug(f"Registration result: success={success}")
                
                if success:
                    response = TextSendMessage(text=f"{name}さんのLINE IDを自動登録しました。今後はBotから通知が届きます。")
                    log_debug(f"Sending registration success message to user_id={user_id}")
                    pharmacist_line_bot_api.reply_message(event.reply_token, response)
                    log_debug(f"Registration success response sent successfully to user_id={user_id}")
                    logger.info(f"Successfully registered pharmacist user_id for {name}")
                else:
                    response = TextSendMessage(text=f"{name}さんの登録に失敗しました。名前・電話番号が正しいかご確認ください。")
                    log_debug(f"Sending registration failure message to user_id={user_id}")
                    pharmacist_line_bot_api.reply_message(event.reply_token, response)
                    log_debug(f"Registration failure response sent successfully to user_id={user_id}")
                    logger.warning(f"Failed to register pharmacist user_id for {name}")
            except Exception as e:
                error_msg = f"Exception during registration: {str(e)}"
                log_debug(error_msg)
                logger.error(error_msg)
                
                response = TextSendMessage(text=f"登録処理中にエラーが発生しました。しばらく時間をおいて再度お試しください。")
                pharmacist_line_bot_api.reply_message(event.reply_token, response)
            return
        else:
            log_debug(f"Insufficient parts for registration: {parts}")
    
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
    
    log_debug(f"Sending guide message to user_id={user_id}")
    response = TextSendMessage(text=guide_text)
    pharmacist_line_bot_api.reply_message(event.reply_token, response)
    log_debug(f"Guide message sent successfully to user_id={user_id}")

@router.post("/webhook")
async def pharmacist_line_webhook(request: Request):
    try:
        body = await request.body()
        signature = request.headers.get('X-Line-Signature', '')
        
        log_debug(f"Pharmacist webhook received: body_length={len(body)}, signature={signature[:20] if signature else 'None'}...")
        logger.info(f"Pharmacist webhook received: body_length={len(body)}")
        
        try:
            pharmacist_handler.handle(body.decode('utf-8'), signature)
            log_debug(f"Pharmacist webhook processed successfully")
            logger.info("Pharmacist webhook processed successfully")
        except InvalidSignatureError:
            error_msg = "Invalid signature for pharmacist webhook"
            log_debug(error_msg)
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        return {"status": "ok"}
        
    except Exception as e:
        error_msg = f"Pharmacist webhook error: {e}"
        log_debug(error_msg)
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail="Internal server error") 