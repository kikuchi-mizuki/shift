import os
import logging
import re
from datetime import datetime
from linebot import LineBotApi, WebhookHandler
from linebot.models import TextSendMessage, TemplateSendMessage, ButtonsTemplate, PostbackAction, MessageEvent, TextMessage, PostbackEvent
from linebot.exceptions import LineBotApiError
from shared.services.google_sheets_service import GoogleSheetsService
from shared.services.request_manager import RequestManager

logger = logging.getLogger(__name__)

class PharmacistLineBotService:
    def __init__(self):
        self.channel_access_token = os.getenv('PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN')
        self.channel_secret = os.getenv('PHARMACIST_LINE_CHANNEL_SECRET')
        self.line_bot_api = LineBotApi(self.channel_access_token)
        self.handler = WebhookHandler(self.channel_secret)

    def send_message(self, user_id: str, message: TextSendMessage):
        try:
            self.line_bot_api.push_message(user_id, message)
            logger.info(f"Message sent to pharmacist: {user_id}")
        except LineBotApiError as e:
            logger.error(f"Failed to send message to pharmacist {user_id}: {e}")

    def send_template_message(self, user_id: str, template: TemplateSendMessage):
        try:
            self.line_bot_api.push_message(user_id, template)
            logger.info(f"Template message sent to pharmacist: {user_id}")
        except LineBotApiError as e:
            logger.error(f"Failed to send template message to pharmacist {user_id}: {e}")

    def reply_message(self, reply_token: str, message):
        try:
            self.line_bot_api.reply_message(reply_token, message)
            logger.info(f"Reply message sent to pharmacist")
        except LineBotApiError as e:
            logger.error(f"Failed to send reply message to pharmacist: {e}")

# グローバルインスタンス
pharmacist_line_bot_service = PharmacistLineBotService()
request_manager = RequestManager()

@pharmacist_line_bot_service.handler.add(MessageEvent, message=TextMessage)
def handle_pharmacist_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id
    # 柔軟な区切り文字対応
    if re.search(r'[ ,、\u3000]', text):
        parts = re.split(r'[ ,、\u3000]+', text)
        if len(parts) >= 2:
            name = parts[0]
            phone = parts[1]
            sheets_service = GoogleSheetsService()
            success = sheets_service.register_pharmacist_user_id(name, phone, user_id)
            if success:
                # TextSendMessage(text=f"{name}さんのLINE IDを自動登録しました。今後はBotから通知が届きます。")
                # ↑このメッセージ送信を削除
                return
            else:
                pharmacist_line_bot_service.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f"{name}さんの登録に失敗しました。名前・電話番号が正しいかご確認ください。")
                )
                return
    # コマンド以外は案内メッセージを自動返信（未登録ユーザーのみ）
    # ここでユーザー登録判定が必要なら追加
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
    """薬剤師Botのポストバックイベント処理"""
    print(f"[DEBUG] handle_pharmacist_postback called with data: {event.postback.data}")
    
    postback_data = event.postback.data
    
    try:
        if postback_data.startswith("pharmacist_apply:"):
            handle_pharmacist_apply(event, postback_data)
        elif postback_data.startswith("pharmacist_decline:"):
            handle_pharmacist_decline(event, postback_data)
        elif postback_data.startswith("pharmacist_details:"):
            handle_pharmacist_details(event, postback_data)
        else:
            pharmacist_line_bot_service.reply_message(
                event.reply_token,
                TextSendMessage(text="このボタンは現在ご利用いただけません。最新のBotからの通知をご利用ください。")
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
        
        # 詳細確認メッセージを送信
        response = TextSendMessage(
            text=f"📋 依頼詳細\n"
                 f"依頼ID: {request_id}\n\n"
                 f"詳細情報を確認中です...\n"
                 f"少々お待ちください。"
        )
        
        pharmacist_line_bot_service.reply_message(event.reply_token, response)
        logger.info(f"Details confirmation sent to pharmacist: {user_id}")
        
    except Exception as e:
        print(f"[DEBUG] handle_pharmacist_details: Exception occurred: {e}")
        logger.error(f"Error handling pharmacist details: {e}")
        pharmacist_line_bot_service.reply_message(
            event.reply_token,
            TextSendMessage(text="詳細確認処理中にエラーが発生しました。")
        ) 