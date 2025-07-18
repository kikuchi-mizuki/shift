from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, PostbackEvent
import os
import logging
import re
from datetime import datetime

from shared.services.google_sheets_service import GoogleSheetsService
from shared.services.request_manager import RequestManager

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
request_manager = RequestManager()

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
    # まず、ユーザーが既に登録されているかチェック
    try:
        sheets_service = GoogleSheetsService()
        log_debug(f"Checking if user {user_id} is already registered")
        
        # 薬剤師リストからユーザーを検索
        today = datetime.now().date()
        sheet_name = sheets_service.get_sheet_name(today)
        pharmacists = sheets_service._get_pharmacist_list(sheet_name)
        
        registered_user = None
        for pharmacist in pharmacists:
            if pharmacist.get("user_id") == user_id:
                registered_user = pharmacist
                break
        
        if registered_user:
            log_debug(f"User {user_id} is already registered as pharmacist: {registered_user.get('name')}")
            # 登録済みユーザーへのメッセージ
            registered_text = (
                f"✅ {registered_user.get('name')}さん、お疲れ様です！\n\n"
                "既に薬剤師として登録済みです。\n\n"
                "📋 利用可能な機能：\n"
                "• シフト通知の受信\n"
                "• 勤務状況の確認\n"
                "• シフト申請の受信\n\n"
                "何かご質問がございましたら、お気軽にお声かけください。"
            )
            log_debug(f"Sending registered user message to user_id={user_id}")
            response = TextSendMessage(text=registered_text)
            pharmacist_line_bot_api.reply_message(event.reply_token, response)
            log_debug(f"Registered user message sent successfully to user_id={user_id}")
            return
            
    except Exception as e:
        log_debug(f"Error checking user registration: {str(e)}")
        # エラーが発生した場合は通常の処理を続行
    
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
    
    # 未登録ユーザーへの案内メッセージ
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

@pharmacist_handler.add(PostbackEvent)
def handle_pharmacist_postback(event):
    """薬剤師Botのポストバックイベント処理（ボタンクリックなど）"""
    try:
        user_id = event.source.user_id
        postback_data = event.postback.data
        
        log_debug(f"Pharmacist postback received: user_id={user_id}, postback_data='{postback_data}'")
        logger.info(f"[薬剤師Bot] Postback from {user_id}: {postback_data}")
        
        # 応募ボタンの処理
        if postback_data.startswith("pharmacist_apply:"):
            log_debug(f"Calling handle_pharmacist_apply with data: {postback_data}")
            handle_pharmacist_apply(event, postback_data)
            return
            
        # 辞退ボタンの処理
        elif postback_data.startswith("pharmacist_decline:"):
            log_debug(f"Calling handle_pharmacist_decline with data: {postback_data}")
            handle_pharmacist_decline(event, postback_data)
            return
            
        # 詳細確認ボタンの処理
        elif postback_data.startswith("pharmacist_details:"):
            log_debug(f"Calling handle_pharmacist_details with data: {postback_data}")
            handle_pharmacist_details(event, postback_data)
            return
            
        else:
            logger.warning(f"[薬剤師Bot] Unknown postback data: {postback_data}")
            response = TextSendMessage(text="不明なボタン操作です。")
            pharmacist_line_bot_api.reply_message(event.reply_token, response)
            
    except Exception as e:
        log_debug(f"Error in handle_pharmacist_postback: {e}")
        logger.error(f"[薬剤師Bot] Error handling postback: {e}")
        error_response = TextSendMessage(text="ボタン処理中にエラーが発生しました。")
        pharmacist_line_bot_api.reply_message(event.reply_token, error_response)

def handle_pharmacist_apply(event, postback_data: str):
    """薬剤師の応募処理"""
    log_debug(f"handle_pharmacist_apply called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        log_debug(f"handle_pharmacist_apply: user_id={user_id}, request_id={request_id}")
        logger.info(f"[薬剤師Bot] Pharmacist apply button clicked: user_id={user_id}, request_id={request_id}")
        
        # 依頼内容を取得
        request_data = request_manager.get_request(request_id)
        
        # 1. 応募確認メッセージを送信
        if request_data:
            date = request_data.get('date')
            if date:
                if hasattr(date, 'strftime'):
                    date_str = date.strftime('%Y/%m/%d')
                else:
                    from datetime import datetime
                    date_str = str(date)
            else:
                date_str = '不明'
            response_text = f"✅ 応募を受け付けました！\n\n"
            response_text += f"🏪 店舗: {request_data.get('store', '不明')}\n"
            response_text += f"📅 日付: {date_str}\n"
            response_text += f"⏰ 時間: {request_data.get('start_time_label', '不明')}〜{request_data.get('end_time_label', '不明')}\n\n"
            response_text += f"店舗からの確定連絡をお待ちください。\n"
            response_text += f"確定次第、詳細をお知らせいたします。"
        else:
            response_text = f"✅ 応募を受け付けました！\n"
            response_text += f"依頼ID: {request_id}\n\n"
            response_text += f"店舗からの確定連絡をお待ちください。\n"
            response_text += f"確定次第、詳細をお知らせいたします。"
        
        response = TextSendMessage(text=response_text)
        pharmacist_line_bot_api.reply_message(event.reply_token, response)
        logger.info(f"[薬剤師Bot] Application confirmation sent to {user_id}")
        
        # 2. 応募者リストに追加
        request_manager.add_applicant(request_id, user_id)
        logger.info(f"[薬剤師Bot] Added {user_id} to applicants for request {request_id}")
        
        # 3. Google Sheetsに応募記録を保存
        try:
            pharmacist_name = "薬剤師A"  # 実際はDBから取得
            sheets_service = GoogleSheetsService()
            application_success = sheets_service.record_application(
                request_id=request_id,
                pharmacist_id=f"pharm_{pharmacist_name}",
                pharmacist_name=pharmacist_name,
                store_name=request_data.get('store', 'メイプル薬局') if request_data else "メイプル薬局",
                date=request_data.get('date', datetime.now().date()) if request_data else datetime.now().date(),
                time_slot=request_data.get('time_slot', 'time_morning') if request_data else "time_morning"
            )
            
            if application_success:
                logger.info(f"[薬剤師Bot] Application recorded in Google Sheets for {pharmacist_name}")
            else:
                logger.warning(f"[薬剤師Bot] Failed to record application in Google Sheets for {pharmacist_name}")
                
        except Exception as e:
            logger.error(f"[薬剤師Bot] Error recording application in Google Sheets: {e}")
        
        logger.info(f"[薬剤Bot] Application process completed for {user_id}")
        
    except Exception as e:
        log_debug(f"handle_pharmacist_apply: Exception occurred: {e}")
        logger.error(f"[薬剤師Bot] Error handling pharmacist apply: {e}")
        pharmacist_line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="応募処理中にエラーが発生しました。")
        )

def handle_pharmacist_decline(event, postback_data: str):
    """薬剤師の辞退処理"""
    log_debug(f"handle_pharmacist_decline called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        log_debug(f"handle_pharmacist_decline: user_id={user_id}, request_id={request_id}")
        logger.info(f"[薬剤師Bot] Pharmacist decline button clicked: user_id={user_id}, request_id={request_id}")
        
        # 辞退確認メッセージを送信
        response = TextSendMessage(
            text=f"❌ 辞退を受け付けました。\n"
                 f"依頼ID: {request_id}\n\n"
                 f"ご連絡ありがとうございました。\n"
                 f"またの機会をお待ちしております。"
        )
        
        pharmacist_line_bot_api.reply_message(event.reply_token, response)
        logger.info(f"[薬剤師Bot] Decline confirmation sent to pharmacist: {user_id}")
        
    except Exception as e:
        log_debug(f"handle_pharmacist_decline: Exception occurred: {e}")
        logger.error(f"[薬剤師Bot] Error handling pharmacist decline: {e}")
        pharmacist_line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="辞退処理中にエラーが発生しました。")
        )

def handle_pharmacist_details(event, postback_data: str):
    """薬剤師の詳細確認処理"""
    log_debug(f"handle_pharmacist_details called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        log_debug(f"handle_pharmacist_details: user_id={user_id}, request_id={request_id}")
        logger.info(f"[薬剤師Bot] Pharmacist details button clicked: user_id={user_id}, request_id={request_id}")
        
        # 依頼内容を取得
        request_data = request_manager.get_request(request_id)
        
        if request_data:
            # 詳細情報を作成
            date = request_data.get('date')
            if date:
                if hasattr(date, 'strftime'):
                    date_str = date.strftime('%Y/%m/%d')
                else:
                    date_str = str(date)
            else:
                date_str = '不明'
                
            details_text = f"📋 勤務依頼の詳細\n"
            details_text += f"━━━━━━━━━━━━━━━━\n"
            details_text += f"🏪 店舗: {request_data.get('store', '不明')}\n"
            details_text += f"📅 日付: {date_str}\n"
            details_text += f"⏰ 開始時間: {request_data.get('start_time_label', '不明')}\n"
            details_text += f"⏰ 終了時間: {request_data.get('end_time_label', '不明')}\n"
            details_text += f"☕ 休憩時間: {request_data.get('break_time_label', '不明')}\n"
            details_text += f"👥 必要人数: {request_data.get('count_text', '不明')}\n"
            details_text += f"━━━━━━━━━━━━━━━━\n"
            details_text += f"この依頼に応募しますか？"
            
            response = TextSendMessage(text=details_text)
        else:
            response = TextSendMessage(
                text=f"📋 依頼詳細\n"
                     f"依頼ID: {request_id}\n\n"
                     f"詳細情報を確認中です...\n"
                     f"少々お待ちください。"
            )
        
        pharmacist_line_bot_api.reply_message(event.reply_token, response)
        logger.info(f"[薬剤師Bot] Details confirmation sent to pharmacist: {user_id}")
        
    except Exception as e:
        log_debug(f"handle_pharmacist_details: Exception occurred: {e}")
        logger.error(f"[薬剤師Bot] Error handling pharmacist details: {e}")
        pharmacist_line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="詳細確認処理中にエラーが発生しました。")
        )

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