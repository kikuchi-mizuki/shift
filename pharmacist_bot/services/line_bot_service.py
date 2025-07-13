import logging
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    TextSendMessage,
    TemplateSendMessage,
    ButtonsTemplate,
    PostbackAction,
    MessageEvent,
    TextMessage,
    PostbackEvent
)

from pharmacist_bot.config import pharmacist_settings
from shared.services.google_sheets_service import GoogleSheetsService
from shared.services.request_manager import request_manager

logger = logging.getLogger(__name__)


class PharmacistLineBotService:
    def __init__(self):
        self.line_bot_api = LineBotApi(pharmacist_settings.pharmacist_line_channel_access_token)
        self.handler = WebhookHandler(pharmacist_settings.pharmacist_line_channel_secret)
        logger.info("Pharmacist Line Bot service initialized")

    def send_message(self, user_id: str, message: TextSendMessage):
        """メッセージを送信"""
        try:
            self.line_bot_api.push_message(user_id, message)
            logger.info(f"Message sent to pharmacist user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to pharmacist user {user_id}: {e}")
            return False

    def send_template_message(self, user_id: str, template: TemplateSendMessage):
        """テンプレートメッセージを送信"""
        try:
            self.line_bot_api.push_message(user_id, template)
            logger.info(f"Template message sent to pharmacist user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send template message to pharmacist user {user_id}: {e}")
            return False

    def reply_message(self, reply_token: str, message):
        """リプライメッセージを送信"""
        try:
            self.line_bot_api.reply_message(reply_token, message)
            logger.info(f"Reply message sent to pharmacist user")
            return True
        except Exception as e:
            logger.error(f"Failed to send reply message: {e}")
            return False


# グローバルインスタンス
pharmacist_line_bot_service = PharmacistLineBotService() 

@pharmacist_line_bot_service.handler.add(MessageEvent, message=TextMessage)
def handle_pharmacist_message(event):
    text = event.message.text.strip()
    # 名前・電話番号登録コマンド（例: "名前,電話番号"）
    if "," in text:
        name, phone = [s.strip() for s in text.split(",", 1)]
        user_id = event.source.user_id
        sheets_service = GoogleSheetsService()
        success = sheets_service.register_pharmacist_user_id(name, phone, user_id)
        if success:
            pharmacist_line_bot_service.reply_message(
                event.reply_token,
                TextSendMessage(text=f"{name}さんのLINE IDを自動登録しました。今後はBotから通知が届きます。")
            )
            return
        else:
            pharmacist_line_bot_service.reply_message(
                event.reply_token,
                TextSendMessage(text=f"{name}さんの登録に失敗しました。名前・電話番号が正しいかご確認ください。")
            )
            return
    # コマンド以外は案内メッセージを自動返信
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
    pharmacist_line_bot_service.reply_message(
        event.reply_token,
        TextSendMessage(text=guide_text)
    )

@pharmacist_line_bot_service.handler.add(PostbackEvent)
def handle_pharmacist_postback(event):
    """薬剤師Botのポストバックイベント処理（ボタンクリックなど）"""
    print(f"[DEBUG] handle_pharmacist_postback called with data: {event.postback.data}")
    try:
        user_id = event.source.user_id
        postback_data = event.postback.data
        
        logger.info(f"Received pharmacist postback from {user_id}: {postback_data}")
        
        # ポストバックデータを解析
        if postback_data.startswith("pharmacist_apply:"):
            print(f"[DEBUG] Calling handle_pharmacist_apply with data: {postback_data}")
            handle_pharmacist_apply(event, postback_data)
        elif postback_data.startswith("apply:"):
            print(f"[DEBUG] Calling handle_pharmacist_apply with data: {postback_data}")
            handle_pharmacist_apply(event, postback_data)
        elif postback_data.startswith("pharmacist_decline:"):
            print(f"[DEBUG] Calling handle_pharmacist_decline with data: {postback_data}")
            handle_pharmacist_decline(event, postback_data)
        elif postback_data.startswith("decline:"):
            print(f"[DEBUG] Calling handle_pharmacist_decline with data: {postback_data}")
            handle_pharmacist_decline(event, postback_data)
        elif postback_data.startswith("pharmacist_details:"):
            print(f"[DEBUG] Calling handle_pharmacist_details with data: {postback_data}")
            handle_pharmacist_details(event, postback_data)
        elif postback_data.startswith("details:"):
            print(f"[DEBUG] Calling handle_pharmacist_details with data: {postback_data}")
            handle_pharmacist_details(event, postback_data)
        else:
            print(f"[DEBUG] Unknown pharmacist postback data: {postback_data}")
            logger.warning(f"Unknown pharmacist postback data: {postback_data}")
            pharmacist_line_bot_service.reply_message(
                event.reply_token,
                TextSendMessage(text="不明なボタン操作です。")
            )
            
    except Exception as e:
        print(f"[DEBUG] Error in handle_pharmacist_postback: {e}")
        logger.error(f"Error handling pharmacist postback: {e}")
        pharmacist_line_bot_service.reply_message(
            event.reply_token,
            TextSendMessage(text="エラーが発生しました。もう一度お試しください。")
        )

def handle_pharmacist_apply(event, postback_data: str):
    """薬剤師の応募処理"""
    print(f"[DEBUG] handle_pharmacist_apply called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        print(f"[DEBUG] handle_pharmacist_apply: user_id={user_id}, request_id={request_id}")
        logger.info(f"Pharmacist apply button clicked: user_id={user_id}, request_id={request_id}")
        
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
        
        pharmacist_line_bot_service.reply_message(event.reply_token, response)
        logger.info(f"Application confirmation sent to pharmacist: {user_id}")
        
        # 2. Google Sheetsに応募記録を保存
        try:
            sheets_service = GoogleSheetsService()
            from datetime import datetime
            # 応募記録をスケジュールシートに直接記録
            today = datetime.now().date()
            sheet_name = sheets_service.get_sheet_name(today)
            
            print(f"[DEBUG] Recording application to sheet: {sheet_name}, date: {today}")
            
            # 薬剤師の行を特定
            pharmacists = sheets_service._get_pharmacist_list(sheet_name)
            pharmacist_row = None
            pharmacist_name = ""
            for pharmacist in pharmacists:
                if pharmacist["user_id"] == user_id:
                    pharmacist_row = pharmacist["row_number"]
                    pharmacist_name = pharmacist["name"]
                    break
            
            print(f"[DEBUG] Found pharmacist: {pharmacist_name} at row: {pharmacist_row}")
            
            if pharmacist_row:
                # スケジュールに応募確定を記録
                # 列番号の計算を修正（A列=0, B列=1, C列=2...）
                # 日付に応じて適切な列を計算
                day_column = today.day + 2  # A列(0)が名前、B列(1)がuser_id、C列(2)が電話番号、D列(3)からが日付
                range_name = f"{sheet_name}!{chr(65 + day_column)}{pharmacist_row}"
                schedule_entry = "応募確定 - サンライズ薬局"
                
                print(f"[DEBUG] Writing to range: {range_name} with value: {schedule_entry}")
                
                if sheets_service.service:
                    body = {'values': [[schedule_entry]]}
                    result = sheets_service.service.spreadsheets().values().update(
                        spreadsheetId=sheets_service.spreadsheet_id,
                        range=range_name,
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                    
                    print(f"[DEBUG] Google Sheets update result: {result}")
                    logger.info(f"Application recorded in Google Sheets for request: {request_id}")
                else:
                    logger.warning("Google Sheets service not available, skipping application recording")
            else:
                logger.warning(f"Pharmacist not found in sheet for user_id: {user_id}")
                
        except Exception as e:
            print(f"[DEBUG] Error recording application: {e}")
            logger.error(f"Error recording application in Google Sheets: {e}")
        
        # 3. 店舗Botに確定通知を送信
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
            
            logger.info(f"Store notification sent to: {store_user_id}")
            
        except Exception as e:
            logger.error(f"Error sending store notification: {e}")
        
        # 4. 他の薬剤師に辞退通知を送信
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
                    pharmacist_line_bot_service.line_bot_api.push_message(other_user_id, decline_notification)
                    logger.info(f"Decline notification sent to: {other_user_id}")
                except Exception as e:
                    logger.error(f"Failed to send decline notification to {other_user_id}: {e}")
            
            if not other_pharmacist_user_ids:
                logger.info("No other pharmacists to notify for this request")
                     
        except Exception as e:
            logger.error(f"Error sending decline notifications: {e}")
        
    except Exception as e:
        print(f"[DEBUG] handle_pharmacist_apply: Exception occurred: {e}")
        logger.error(f"Error handling pharmacist apply: {e}")
        pharmacist_line_bot_service.reply_message(
            event.reply_token,
            TextSendMessage(text="応募処理中にエラーが発生しました。")
        )

def handle_pharmacist_decline(event, postback_data: str):
    """薬剤師の辞退処理"""
    print(f"[DEBUG] handle_pharmacist_decline called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        print(f"[DEBUG] handle_pharmacist_decline: user_id={user_id}, request_id={request_id}")
        logger.info(f"Pharmacist decline button clicked: user_id={user_id}, request_id={request_id}")
        
        # 辞退確認メッセージを送信
        response = TextSendMessage(
            text=f"❌ 辞退を受け付けました。\n"
                 f"依頼ID: {request_id}\n\n"
                 f"ご連絡ありがとうございました。\n"
                 f"またの機会をお待ちしております。"
        )
        
        pharmacist_line_bot_service.reply_message(event.reply_token, response)
        logger.info(f"Decline confirmation sent to pharmacist: {user_id}")
        
    except Exception as e:
        print(f"[DEBUG] handle_pharmacist_decline: Exception occurred: {e}")
        logger.error(f"Error handling pharmacist decline: {e}")
        pharmacist_line_bot_service.reply_message(
            event.reply_token,
            TextSendMessage(text="辞退処理中にエラーが発生しました。")
        )

def handle_pharmacist_details(event, postback_data: str):
    """薬剤師の詳細確認処理"""
    print(f"[DEBUG] handle_pharmacist_details called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        print(f"[DEBUG] handle_pharmacist_details: user_id={user_id}, request_id={request_id}")
        logger.info(f"Pharmacist details button clicked: user_id={user_id}, request_id={request_id}")
        
        # 依頼内容を取得
        request_data = request_manager.get_request(request_id)
        
        if request_data:
            # 詳細情報を表示
            date = request_data.get('date')
            if date:
                if hasattr(date, 'strftime'):
                    date_str = date.strftime('%Y/%m/%d')
                else:
                    from datetime import datetime
                    date_str = str(date)
            else:
                date_str = '不明'
            details_text = f"📋 勤務依頼の詳細\n\n"
            details_text += f"🏪 店舗: {request_data.get('store', '不明')}\n"
            details_text += f"📅 日付: {date_str}\n"
            details_text += f"⏰ 開始時間: {request_data.get('start_time_label', '不明')}\n"
            details_text += f"⏰ 終了時間: {request_data.get('end_time_label', '不明')}\n"
            details_text += f"☕ 休憩時間: {request_data.get('break_time_label', '不明')}\n"
            details_text += f"👥 必要人数: {request_data.get('count_text', '不明')}\n\n"
            details_text += f"依頼ID: {request_id}"
            
            response = TextSendMessage(text=details_text)
        else:
            # 依頼が見つからない場合
            response = TextSendMessage(
                text=f"❌ 依頼詳細の取得に失敗しました\n\n"
                     f"依頼ID: {request_id}\n"
                     f"依頼内容が見つかりませんでした。\n"
                     f"店舗にお問い合わせください。"
            )
        
        pharmacist_line_bot_service.reply_message(event.reply_token, response)
        logger.info(f"Details sent to pharmacist: {user_id}")
        
    except Exception as e:
        print(f"[DEBUG] handle_pharmacist_details: Exception occurred: {e}")
        logger.error(f"Error handling pharmacist details: {e}")
        pharmacist_line_bot_service.reply_message(
            event.reply_token,
            TextSendMessage(text="詳細確認処理中にエラーが発生しました。")
        ) 