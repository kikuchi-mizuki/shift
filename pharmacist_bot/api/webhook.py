from fastapi import APIRouter, Request, HTTPException
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    MessageEvent, TextMessage, PostbackEvent, FollowEvent, UnfollowEvent,
    TextSendMessage, TemplateSendMessage, ButtonsTemplate, PostbackAction
)
import logging
from ..config import settings
from ..services.line_bot_service import pharmacist_line_bot_service
from ..services.notification_service import PharmacistNotificationService
from shared.services.request_manager import RequestManager
from shared.models.user import UserType
from shared.services.google_sheets_service import GoogleSheetsService
from datetime import datetime
import json

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# 薬剤師Bot専用のLINE Bot APIとハンドラー
pharmacist_line_bot_api = LineBotApi(settings.pharmacist_line_channel_access_token)
pharmacist_handler = WebhookHandler(settings.pharmacist_line_channel_secret)

# サービス初期化
pharmacist_notification_service = PharmacistNotificationService()
request_manager = RequestManager()
google_sheets_service = GoogleSheetsService()

@router.post("/webhook")
async def pharmacist_webhook(request: Request):
    """薬剤師Bot専用のWebhookエンドポイント"""
    try:
        body = await request.body()
        signature = request.headers.get('X-Line-Signature', '')
        
        logger.info(f"[薬剤師Bot] Webhook received - Body length: {len(body)}")
        
        try:
            pharmacist_handler.handle(body.decode('utf-8'), signature)
            logger.info("[薬剤師Bot] Webhook handled successfully")
        except InvalidSignatureError:
            logger.error("[薬剤師Bot] Invalid signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        except Exception as e:
            logger.error(f"[薬剤Bot] Webhook handling error: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"[薬剤師Bot] Webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@pharmacist_handler.add(FollowEvent)
def handle_pharmacist_follow(event):
    """薬剤師Botのフォローイベント処理"""
    try:
        user_id = event.source.user_id
        logger.info(f"[薬剤師Bot] Follow event from user: {user_id}")
        
        welcome_message = TextSendMessage(
            text="💊 薬剤師Botへようこそ！\n\n"
                 "このBotは勤務依頼の受信・応募・辞退を行います。\n\n"
                 "まずは薬剤師登録を行ってください：\n"
                 "「薬剤師登録」と入力してください。"
        )
        
        pharmacist_line_bot_api.reply_message(event.reply_token, welcome_message)
        logger.info(f"[薬剤師Bot] Welcome message sent to {user_id}")
        
    except Exception as e:
        logger.error(f"[薬剤師Bot] Error handling follow event: {e}")

@pharmacist_handler.add(UnfollowEvent)
def handle_pharmacist_unfollow(event):
    """薬剤師Botのアンフォローイベント処理"""
    try:
        user_id = event.source.user_id
        logger.info(f"[薬剤師Bot] Unfollow event from user: {user_id}")
        # 必要に応じてユーザー情報をクリーンアップ
        
    except Exception as e:
        logger.error(f"[薬剤師Bot] Error handling unfollow event: {e}")

@pharmacist_handler.add(MessageEvent, message=TextMessage)
def handle_pharmacist_text_message(event):
    """薬剤師Botのテキストメッセージ処理"""
    try:
        user_id = event.source.user_id
        message_text = event.message.text.strip()
        
        logger.info(f"[薬剤師Bot] Text message from {user_id}: {message_text}")
        
        # 薬剤師登録処理
        if "薬剤師登録" in message_text:
            handle_pharmacist_registration(event, message_text)
        else:
            # その他のメッセージ
            response = TextSendMessage(
                text="💊 薬剤師Botです。\n\n"
                     "以下のコマンドが利用できます：\n\n"
                     "• 薬剤師登録 - 薬剤師として登録\n"
                     "• ヘルプ - このメッセージを表示\n\n"
                     "勤務依頼が届いた場合は、ボタンから応募・辞退を行ってください。"
            )
            pharmacist_line_bot_api.reply_message(event.reply_token, response)
            
    except Exception as e:
        logger.error(f"[薬剤師Bot] Error handling text message: {e}")
        error_response = TextSendMessage(text="メッセージ処理中にエラーが発生しました。")
        pharmacist_line_bot_api.reply_message(event.reply_token, error_response)

@pharmacist_handler.add(PostbackEvent)
def handle_pharmacist_postback(event):
    """薬剤師Botのポストバックイベント処理（ボタンクリックなど）"""
    try:
        user_id = event.source.user_id
        postback_data = event.postback.data
        
        logger.info(f"[薬剤師Bot] Postback from {user_id}: {postback_data}")
        print(f"[DEBUG][薬剤師Bot] handle_postback: postback_data={postback_data!r}, user_id={user_id}")
        
        # 応募ボタンの処理
        if postback_data.startswith("pharmacist_apply:"):
            print(f"[DEBUG][薬剤師Bot] Calling handle_pharmacist_apply with data: {postback_data}")
            handle_pharmacist_apply(event, postback_data)
            return
            
        # 辞退ボタンの処理
        elif postback_data.startswith("pharmacist_decline:"):
            print(f"[DEBUG][薬剤師Bot] Calling handle_pharmacist_decline with data: {postback_data}")
            handle_pharmacist_decline(event, postback_data)
            return
            
        # 詳細確認ボタンの処理
        elif postback_data.startswith("pharmacist_details:"):
            print(f"[DEBUG][薬剤師Bot] Calling handle_pharmacist_details with data: {postback_data}")
            handle_pharmacist_details(event, postback_data)
            return
            
        else:
            logger.warning(f"[薬剤師Bot] Unknown postback data: {postback_data}")
            response = TextSendMessage(text="不明なボタン操作です。")
            pharmacist_line_bot_api.reply_message(event.reply_token, response)
            
    except Exception as e:
        logger.error(f"[薬剤師Bot] Error handling postback: {e}")
        error_response = TextSendMessage(text="ボタン処理中にエラーが発生しました。")
        pharmacist_line_bot_api.reply_message(event.reply_token, error_response)

def handle_pharmacist_registration(event, message_text: str):
    """薬剤師登録処理"""
    try:
        user_id = event.source.user_id
        
        # 薬剤師情報を解析（柔軟なパターンに対応）
        import re
        # カンマ、スペース、改行などで分割
        parts = re.split(r'[,，\s\n]+', message_text)
        
        pharmacist_name = None
        for part in parts:
            if part and part != "薬剤師登録":
                pharmacist_name = part.strip()
                break
        
        if not pharmacist_name:
            response = TextSendMessage(
                text="💊 薬剤師登録\n\n"
                     "以下の形式で登録してください：\n\n"
                     "• 薬剤師登録 田中太郎\n"
                     "• 薬剤師登録,田中太郎\n"
                     "• 薬剤師登録 田中 太郎\n\n"
                     "名前を入力してください。"
            )
            pharmacist_line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 薬剤師情報を保存（実際はDBに保存）
        # TODO: 実際の実装ではDBに保存
        logger.info(f"[薬剤師Bot] Pharmacist registration: {pharmacist_name} ({user_id})")
        
        # 登録完了メッセージ
        response = TextSendMessage(
            text=f"✅ 薬剤師登録が完了しました！\n\n"
                 f"👤 名前: {pharmacist_name}\n"
                 f"🆔 ユーザーID: {user_id}\n\n"
                 f"これで勤務依頼を受信・応募・辞退ができるようになりました。\n"
                 f"依頼が届いたら、ボタンから操作してください。"
        )
        
        pharmacist_line_bot_api.reply_message(event.reply_token, response)
        logger.info(f"[薬剤師Bot] Registration completed for {pharmacist_name}")
        
    except Exception as e:
        logger.error(f"[薬剤師Bot] Error in pharmacist registration: {e}")
        error_response = TextSendMessage(text="登録処理中にエラーが発生しました。")
        pharmacist_line_bot_api.reply_message(event.reply_token, error_response)

def handle_pharmacist_apply(event, postback_data: str):
    """薬剤師の応募処理"""
    print(f"[DEBUG][薬剤師Bot] handle_pharmacist_apply called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        print(f"[DEBUG][薬剤師Bot] handle_pharmacist_apply: user_id={user_id}, request_id={request_id}")
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
            application_success = google_sheets_service.record_application(
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
        
        # 4. 店舗Botに確定通知を送信
        try:
            from linebot import LineBotApi
            from app.config import settings
            
            # 店舗Bot用のLINE API
            store_line_bot_api = LineBotApi(settings.line_channel_access_token)
            
            # 店舗のuser_id（実際はDBから取得）
            store_user_id = "U37da00c3f064eb4acc037aa8ec6ea79e"  # サンライズ薬局のuser_id
            
            store_line_bot_api.push_message(
                store_user_id,
                TemplateSendMessage(
                    alt_text="薬剤師が応募しました！",
                    template=ButtonsTemplate(
                        title="🎉 薬剤師が応募しました！",
                        text=f"応募日時: {datetime.now().strftime('%Y/%m/%d %H:%M')}",
                        actions=[
                            PostbackAction(label="承諾", data=f"pharmacist_confirm_accept:{request_id}:{user_id}"),
                            PostbackAction(label="拒否", data=f"pharmacist_confirm_reject:{request_id}:{user_id}")
                        ]
                    )
                )
            )
            
            logger.info(f"[薬剤師Bot] Store notification sent to: {store_user_id}")
            
        except Exception as e:
            logger.error(f"[薬剤師Bot] Error sending store notification: {e}")
        
        # 5. 他の薬剤師に辞退通知を送信
        try:
            # 同じ依頼に応募した他の薬剤師を取得
            # 実際の実装では、同じ依頼IDに応募した他の薬剤師をDBから取得
            # 現在は、実際に存在する薬剤師IDのみに送信
            other_pharmacist_user_ids = []
            
            # 開発用: 実際に存在する薬剤師IDのみを追加
            # 例: 他の薬剤師がいる場合はここに追加
            # other_pharmacist_user_ids.append("U32985fe83988007da045f7b65c3bb90f")
             
            decline_notification = TextSendMessage(
                text=f"❌ 勤務依頼の辞退通知\n\n"
                     f"依頼ID: {request_id}\n"
                     f"他の薬剤師が確定しました。\n"
                     f"ご応募ありがとうございました。\n"
                     f"またの機会をお待ちしております。"
            )
            
            for other_user_id in other_pharmacist_user_ids:
                try:
                    pharmacist_line_bot_api.push_message(other_user_id, decline_notification)
                    logger.info(f"[薬剤師Bot] Decline notification sent to: {other_user_id}")
                except Exception as e:
                    logger.error(f"[薬剤師Bot] Failed to send decline notification to {other_user_id}: {e}")
            
            if not other_pharmacist_user_ids:
                logger.info("[薬剤師Bot] No other pharmacists to notify for this request")
                     
        except Exception as e:
            logger.error(f"[薬剤師Bot] Error sending decline notifications: {e}")
        
        logger.info(f"[薬剤師Bot] Application process completed for {user_id}")
        
    except Exception as e:
        print(f"[DEBUG][薬剤師Bot] handle_pharmacist_apply: Exception occurred: {e}")
        logger.error(f"[薬剤師Bot] Error handling pharmacist apply: {e}")
        pharmacist_line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="応募処理中にエラーが発生しました。")
        )

def handle_pharmacist_decline(event, postback_data: str):
    """薬剤師の辞退処理"""
    print(f"[DEBUG][薬剤師Bot] handle_pharmacist_decline called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        print(f"[DEBUG][薬剤師Bot] handle_pharmacist_decline: user_id={user_id}, request_id={request_id}")
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
        print(f"[DEBUG][薬剤師Bot] handle_pharmacist_decline: Exception occurred: {e}")
        logger.error(f"[薬剤師Bot] Error handling pharmacist decline: {e}")
        pharmacist_line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="辞退処理中にエラーが発生しました。")
        )

def handle_pharmacist_details(event, postback_data: str):
    """薬剤師の詳細確認処理"""
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
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
                text=f"❌ 依頼情報が見つかりません。\n"
                     f"依頼ID: {request_id}\n\n"
                     f"依頼が削除されたか、期限が切れている可能性があります。"
            )
        
        pharmacist_line_bot_api.reply_message(event.reply_token, response)
        logger.info(f"[薬剤師Bot] Details sent to pharmacist: {user_id}")
        
    except Exception as e:
        logger.error(f"[薬剤師Bot] Error handling pharmacist details: {e}")
        pharmacist_line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="詳細確認処理中にエラーが発生しました。")
        ) 