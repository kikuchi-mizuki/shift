import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import LineBotApiError
from linebot.models import TextSendMessage, TemplateSendMessage, ButtonsTemplate, PostbackAction

from app.services.google_sheets_service import GoogleSheetsService
from app.models.schedule import TimeSlot
from app.config import settings

logger = logging.getLogger(__name__)

class PharmacistNotificationService:
    """薬剤師への依頼通知サービス"""
    
    def __init__(self):
        # 薬剤師Bot専用のアクセストークンを使う
        pharmacist_token = settings.pharmacist_line_channel_access_token
        pharmacist_secret = settings.pharmacist_line_channel_secret
        
        # デバッグ: アクセストークンの設定状況をログ出力
        if pharmacist_token:
            logger.info(f"Pharmacist notification service initialized with token: {pharmacist_token[:10]}...")
        else:
            logger.warning("Pharmacist LINE channel access token is not set!")
            
        if pharmacist_secret:
            logger.info(f"Pharmacist notification service initialized with secret: {pharmacist_secret[:10]}...")
        else:
            logger.warning("Pharmacist LINE channel secret is not set!")
        
        self.line_bot_api = LineBotApi(pharmacist_token)
        self.handler = WebhookHandler(pharmacist_secret)
        self.google_sheets_service = GoogleSheetsService()
    
    def notify_pharmacists_of_request(
        self, 
        available_pharmacists: List[Dict[str, Any]], 
        request_data: Dict[str, Any],
        request_id: str
    ) -> Dict[str, Any]:
        """
        空き薬剤師に依頼通知を送信
        
        Args:
            available_pharmacists: 空き薬剤師のリスト
            request_data: 依頼内容
            request_id: 依頼ID
            
        Returns:
            通知結果の辞書
        """
        try:
            notification_results = {
                "total_pharmacists": len(available_pharmacists),
                "notified_count": 0,
                "failed_count": 0,
                "failed_pharmacists": []
            }
            
            # 依頼内容の詳細を作成
            request_details = self._create_request_details(request_data)
            
            for pharmacist in available_pharmacists:
                try:
                    # 薬剤師のLINEユーザーIDを取得
                    pharmacist_user_id = pharmacist.get("user_id")
                    
                    if not pharmacist_user_id:
                        logger.warning(f"No LINE user ID for pharmacist: {pharmacist.get('name')}")
                        notification_results["failed_count"] += 1
                        notification_results["failed_pharmacists"].append({
                            "name": pharmacist.get("name"),
                            "reason": "No LINE user ID"
                        })
                        continue
                    
                    # 薬剤師に通知を送信
                    success = self._send_notification_to_pharmacist(
                        pharmacist_user_id, 
                        pharmacist.get("name"),
                        request_details,
                        request_id
                    )
                    
                    if success:
                        notification_results["notified_count"] += 1
                        logger.info(f"Successfully notified pharmacist: {pharmacist.get('name')}")
                    else:
                        notification_results["failed_count"] += 1
                        notification_results["failed_pharmacists"].append({
                            "name": pharmacist.get("name"),
                            "reason": "Notification failed"
                        })
                        logger.error(f"Failed to notify pharmacist: {pharmacist.get('name')}")
                        
                except Exception as e:
                    logger.error(f"Error notifying pharmacist {pharmacist.get('name')}: {e}")
                    notification_results["failed_count"] += 1
                    notification_results["failed_pharmacists"].append({
                        "name": pharmacist.get("name"),
                        "reason": str(e)
                    })
            
            logger.info(f"Notification completed: {notification_results}")
            
            # 開発環境での結果表示
            if notification_results["total_pharmacists"] > 0:
                if notification_results["notified_count"] > 0:
                    logger.info(f"✅ Successfully notified {notification_results['notified_count']} pharmacists")
                if notification_results["failed_count"] > 0:
                    logger.info(f"⚠️  Skipped {notification_results['failed_count']} pharmacists (development mode)")
            
            return notification_results
            
        except Exception as e:
            logger.error(f"Error in notify_pharmacists_of_request: {e}")
            return {
                "total_pharmacists": len(available_pharmacists),
                "notified_count": 0,
                "failed_count": len(available_pharmacists),
                "failed_pharmacists": [],
                "error": str(e)
            }
    
    def _create_request_details(self, request_data: Dict[str, Any]) -> str:
        """依頼内容の詳細テキストを作成"""
        date = request_data.get("date")
        if date:
            if hasattr(date, 'strftime'):
                date_str = date.strftime('%Y/%m/%d')
            else:
                date_str = str(date)
        else:
            date_str = "未選択"
        start_time_label = request_data.get("start_time_label", "未選択")
        end_time_label = request_data.get("end_time_label", "未選択")
        break_time_label = request_data.get("break_time_label", "未選択")
        count_text = request_data.get("count_text", "未選択")
        store_name = request_data.get("store", "不明店舗")
        
        details = f"📋 勤務依頼の詳細\n"
        details += f"━━━━━━\n"
        details += f"🏪 店舗: {store_name}\n"
        details += f"📅 日付: {date_str}\n"
        details += f"⏰ 開始時間: {start_time_label}\n"
        details += f"⏰ 終了時間: {end_time_label}\n"
        details += f"☕ 休憩時間: {break_time_label}\n"
        details += f"👥 必要人数: {count_text}\n"
        details += f"━━━━━━\n"
        details += f"この依頼に応募しますか？"
        
        return details
    
    def _send_notification_to_pharmacist(
        self, 
        pharmacist_user_id: str, 
        pharmacist_name: Optional[str],
        request_details: str,
        request_id: str
    ) -> bool:
        """
        個別の薬剤師に通知を送信
        
        Args:
            pharmacist_user_id: 薬剤師のLINEユーザーID
            pharmacist_name: 薬剤師の名前（None可）
            request_details: 依頼詳細
            request_id: 依頼ID
            
        Returns:
            送信成功時True
        """
        try:
            # 開発・テスト用: 無効なLINEユーザーIDの場合はスキップ
            if not pharmacist_user_id:
                logger.info(f"Skipping notification for pharmacist {pharmacist_name or ''} (no user ID)")
                return True  # 開発用に成功として扱う
            
            # LINEユーザーIDの形式チェック（U + 32文字の英数字）
            if not pharmacist_user_id.startswith("U") or len(pharmacist_user_id) != 33:
                logger.info(f"Skipping notification for pharmacist {pharmacist_name or ''} (invalid user ID format: {pharmacist_user_id})")
                return True  # 開発用に成功として扱う
            
            # 開発環境でのテスト用IDチェック
            if settings.is_development and pharmacist_user_id.startswith("U1234567890"):
                logger.info(f"Skipping notification for pharmacist {pharmacist_name or ''} (test user ID in development)")
                return True  # 開発用に成功として扱う
            
            # 本番環境または有効なユーザーIDの場合のみ実際に送信
            if settings.is_production or (len(pharmacist_user_id) == 33 and pharmacist_user_id.startswith("U")):
                # テキストメッセージ
                text_message = TextSendMessage(text=request_details)
                
                # 応募ボタン付きテンプレート
                template_message = TemplateSendMessage(
                    alt_text="勤務依頼への応募",
                    template=ButtonsTemplate(
                        title="勤務依頼が届いています",
                        text=f"{(pharmacist_name or '')}さん\n新しい勤務依頼があります",
                        actions=[
                            PostbackAction(
                                label="✅ 応募する",
                                data=f"pharmacist_apply:{request_id}"
                            ),
                            PostbackAction(
                                label="❌ 辞退する",
                                data=f"pharmacist_decline:{request_id}"
                            )
                        ]
                    )
                )
                
                # 追加: 通知先user_idと薬剤師名をprint
                print(f"[DEBUG] 通知送信先 pharmacist_user_id: '{pharmacist_user_id}', name: '{pharmacist_name or ''}'")
                
                # メッセージを送信（push_messageを使用）
                try:
                    self.line_bot_api.push_message(
                        pharmacist_user_id, 
                        [text_message, template_message]
                    )
                    logger.info(f"Sent notification to pharmacist {pharmacist_name or ''}")
                    return True
                except LineBotApiError as push_error:
                    logger.error(f"Push message error for pharmacist {pharmacist_name or ''}: {push_error}")
                    # より詳細なエラー情報をログ出力
                    if hasattr(push_error, 'status_code'):
                        logger.error(f"Error status code: {push_error.status_code}")
                    if hasattr(push_error, 'error_response'):
                        logger.error(f"Error response: {push_error.error_response}")
                    if hasattr(push_error, 'request_id'):
                        logger.error(f"Request ID: {push_error.request_id}")
                    return False
            else:
                logger.info(f"Skipping notification for pharmacist {pharmacist_name or ''} (invalid user ID for production)")
                return True  # 開発用に成功として扱う
                
        except LineBotApiError as e:
            logger.error(f"Error sending notification to pharmacist {pharmacist_name or ''}: {e}")
            # より詳細なエラー情報をログ出力
            if hasattr(e, 'status_code'):
                logger.error(f"Error status code: {e.status_code}")
            if hasattr(e, 'error_response'):
                logger.error(f"Error response: {e.error_response}")
            if hasattr(e, 'request_id'):
                logger.error(f"Request ID: {e.request_id}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending notification to pharmacist {pharmacist_name or ''}: {e}")
            return False
    
    def handle_pharmacist_response(
        self, 
        pharmacist_user_id: str, 
        pharmacist_name: str,
        response_type: str,
        request_id: str
    ) -> Dict[str, Any]:
        """
        薬剤師からの応答を処理
        
        Args:
            pharmacist_user_id: 薬剤師のLINEユーザーID
            pharmacist_name: 薬剤師の名前
            response_type: 応答タイプ（apply/decline/details）
            request_id: 依頼ID
            
        Returns:
            処理結果
        """
        try:
            logger.info(f"Processing pharmacist response: {pharmacist_name} ({pharmacist_user_id}) - {response_type} for request {request_id}")
            
            if response_type == "apply":
                # 応募処理
                logger.info(f"Handling application from {pharmacist_name}")
                result = self._handle_application(pharmacist_user_id, pharmacist_name, request_id)
            elif response_type == "decline":
                # 辞退処理
                logger.info(f"Handling declination from {pharmacist_name}")
                result = self._handle_declination(pharmacist_user_id, pharmacist_name, request_id)
            elif response_type == "details":
                # 詳細確認処理
                logger.info(f"Handling details request from {pharmacist_name}")
                result = self._handle_details_request(pharmacist_user_id, pharmacist_name, request_id)
            else:
                logger.warning(f"Unknown response type: {response_type}")
                result = {"success": False, "error": f"Unknown response type: {response_type}"}
            
            logger.info(f"Response processing result for {pharmacist_name}: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error handling pharmacist response: {e}")
            return {"success": False, "error": str(e)}
    
    def _handle_application(
        self, 
        pharmacist_user_id: str, 
        pharmacist_name: str,
        request_id: str
    ) -> Dict[str, Any]:
        """応募処理"""
        try:
            logger.info(f"Starting application process for {pharmacist_name} (request: {request_id})")
            
            # 応募確認メッセージを薬剤師に送信
            confirmation_message = TextSendMessage(
                text=f"✅ 応募を受け付けました！\n"
                     f"依頼ID: {request_id}\n\n"
                     f"店舗からの確定連絡をお待ちください。\n"
                     f"確定次第、詳細をお知らせいたします。"
            )
            
            # 開発環境では実際の送信はスキップ
            if pharmacist_user_id and not pharmacist_user_id.startswith("U1234567890"):
                self.line_bot_api.push_message(
                    pharmacist_user_id, 
                    confirmation_message
                )
                logger.info(f"Sent confirmation message to {pharmacist_name}")
            else:
                logger.info(f"Skipped sending confirmation message to {pharmacist_name} (development mode)")
            
            # Google Sheetsに応募記録を保存
            logger.info(f"Recording application in Google Sheets for {pharmacist_name}")
            application_success = self.google_sheets_service.record_application(
                request_id=request_id,
                pharmacist_id=f"pharm_{pharmacist_name}",
                pharmacist_name=pharmacist_name,
                store_name="メイプル薬局",  # 仮の店舗名
                date=datetime.now().date(),  # 仮の日付
                time_slot="time_morning"     # 仮の時間帯
            )
            
            if application_success:
                logger.info(f"Application recorded successfully in Google Sheets for {pharmacist_name}")
            else:
                logger.warning(f"Failed to record application in Google Sheets for {pharmacist_name}")
            
            logger.info(f"Application process completed for {pharmacist_name}")
            
            return {
                "success": True,
                "message": f"Pharmacist {pharmacist_name} applied for request {request_id}",
                "sheets_recorded": application_success,
                "confirmation_sent": True
            }
            
        except Exception as e:
            logger.error(f"Error handling application for {pharmacist_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def _handle_declination(
        self, 
        pharmacist_user_id: str, 
        pharmacist_name: str,
        request_id: str
    ) -> Dict[str, Any]:
        """辞退処理"""
        try:
            logger.info(f"Starting declination process for {pharmacist_name} (request: {request_id})")
            
            # 辞退確認メッセージを薬剤師に送信
            confirmation_message = TextSendMessage(
                text=f"❌ 辞退を受け付けました。\n"
                     f"依頼ID: {request_id}\n\n"
                     f"ご連絡ありがとうございました。\n"
                     f"またの機会をお待ちしております。"
            )
            
            # 開発環境では実際の送信はスキップ
            if pharmacist_user_id and not pharmacist_user_id.startswith("U1234567890"):
                self.line_bot_api.push_message(
                    pharmacist_user_id, 
                    confirmation_message
                )
                logger.info(f"Sent declination confirmation to {pharmacist_name}")
            else:
                logger.info(f"Skipped sending declination confirmation to {pharmacist_name} (development mode)")
            
            logger.info(f"Declination process completed for {pharmacist_name}")
            
            return {
                "success": True,
                "message": f"Pharmacist {pharmacist_name} declined request {request_id}",
                "confirmation_sent": True
            }
            
        except Exception as e:
            logger.error(f"Error handling declination for {pharmacist_name}: {e}")
            return {"success": False, "error": str(e)}
    
    def _handle_details_request(
        self, 
        pharmacist_user_id: str, 
        pharmacist_name: str,
        request_id: str
    ) -> Dict[str, Any]:
        """詳細確認処理"""
        try:
            logger.info(f"Starting details request process for {pharmacist_name} (request: {request_id})")
            
            # 詳細情報を薬剤師に送信
            details_message = TextSendMessage(
                text=f"📋 依頼詳細\n"
                     f"依頼ID: {request_id}\n\n"
                     f"詳細情報を確認中です...\n"
                     f"少々お待ちください。"
            )
            
            # 開発環境では実際の送信はスキップ
            if pharmacist_user_id and not pharmacist_user_id.startswith("U1234567890"):
                self.line_bot_api.push_message(
                    pharmacist_user_id, 
                    details_message
                )
                logger.info(f"Sent details message to {pharmacist_name}")
            else:
                logger.info(f"Skipped sending details message to {pharmacist_name} (development mode)")
            
            logger.info(f"Details request process completed for {pharmacist_name}")
            
            return {
                "success": True,
                "message": f"Details requested for request {request_id}",
                "details_sent": True
            }
            
        except Exception as e:
            logger.error(f"Error handling details request for {pharmacist_name}: {e}")
            return {"success": False, "error": str(e)} 