import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from shared.services.google_sheets_service import GoogleSheetsService
from pharmacist_bot.services.line_bot_service import pharmacist_line_bot_service
from linebot.models import (
    TextSendMessage,
    TemplateSendMessage,
    ButtonsTemplate,
    PostbackAction
)

logger = logging.getLogger(__name__)


class PharmacistNotificationService:
    def __init__(self):
        self.google_sheets_service = GoogleSheetsService()
        logger.info("Pharmacist notification service initialized")

    def notify_pharmacists_of_request(self, pharmacists: List[Dict[str, Any]], 
                                    request_data: Dict[str, Any], 
                                    request_id: str) -> Dict[str, Any]:
        """薬剤師に勤務依頼を通知"""
        try:
            total_pharmacists = len(pharmacists)
            notified_count = 0
            failed_count = 0
            failed_pharmacists = []
            
            for pharmacist in pharmacists:
                user_id = pharmacist.get("user_id", "")
                pharmacist_name = pharmacist.get("name", "薬剤師")
                
                # 無効なユーザーIDの場合はスキップ
                if not user_id or user_id == "":
                    logger.info(f"Skipping notification for pharmacist {pharmacist_name} (invalid user ID: {user_id})")
                    continue
                
                try:
                    # 通知メッセージを作成
                    notification_sent = self._send_shift_notification(
                        user_id, 
                        pharmacist_name, 
                        request_data, 
                        request_id
                    )
                    
                    if notification_sent:
                        notified_count += 1
                        logger.info(f"Successfully notified pharmacist: {pharmacist_name}")
                    else:
                        failed_count += 1
                        failed_pharmacists.append({
                            "name": pharmacist_name,
                            "reason": "Notification failed"
                        })
                        logger.error(f"Failed to notify pharmacist: {pharmacist_name}")
                        
                except Exception as e:
                    failed_count += 1
                    failed_pharmacists.append({
                        "name": pharmacist_name,
                        "reason": str(e)
                    })
                    logger.error(f"Error sending notification to pharmacist {pharmacist_name}: {e}")
            
            result = {
                "total_pharmacists": total_pharmacists,
                "notified_count": notified_count,
                "failed_count": failed_count,
                "failed_pharmacists": failed_pharmacists
            }
            
            logger.info(f"Notification completed: {result}")
            
            if notified_count > 0:
                logger.info(f"✅ Successfully notified {notified_count} pharmacists")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in notify_pharmacists_of_request: {e}")
            return {
                "total_pharmacists": len(pharmacists),
                "notified_count": 0,
                "failed_count": len(pharmacists),
                "failed_pharmacists": [{"name": p.get("name", "薬剤師"), "reason": str(e)} for p in pharmacists]
            }

    def _send_shift_notification(self, user_id: str, pharmacist_name: str, 
                                request_data: Dict[str, Any], request_id: str) -> bool:
        """個別の薬剤師にシフト通知を送信"""
        try:
            # 通知メッセージを作成
            date_text = request_data.get("date_text", "未指定")
            time_text = request_data.get("time_text", "未指定")
            count_text = request_data.get("count_text", "未指定")
            
            message_text = (
                f"💼 勤務依頼が届きました！\n\n"
                f"📅 勤務日: {date_text}\n"
                f"⏰ 時間帯: {time_text}\n"
                f"👥 必要人数: {count_text}\n"
                f"🆔 依頼ID: {request_id}\n\n"
                f"ご応募をご検討ください。"
            )
            
            # ボタンテンプレートを作成
            template = TemplateSendMessage(
                alt_text="勤務依頼",
                template=ButtonsTemplate(
                    title="勤務依頼",
                    text=message_text,
                    actions=[
                        PostbackAction(
                            label="応募する",
                            data=f"pharmacist_apply:{request_id}"
                        ),
                        PostbackAction(
                            label="辞退する",
                            data=f"pharmacist_decline:{request_id}"
                        ),
                        PostbackAction(
                            label="詳細を確認",
                            data=f"pharmacist_details:{request_id}"
                        )
                    ]
                )
            )
            
            # メッセージを送信
            success = pharmacist_line_bot_service.send_template_message(user_id, template)
            
            if success:
                logger.info(f"Sent shift notification to {pharmacist_name} ({user_id})")
                return True
            else:
                logger.error(f"Failed to send shift notification to {pharmacist_name} ({user_id})")
                return False
                
        except Exception as e:
            logger.error(f"Error sending shift notification to {pharmacist_name}: {e}")
            return False

    def handle_pharmacist_response(self, user_id: str, pharmacist_name: str, 
                                 response_type: str, request_id: str) -> Dict[str, Any]:
        """薬剤師の応答を処理"""
        try:
            logger.info(f"Processing pharmacist response: {pharmacist_name} ({user_id}) - {response_type} for request {request_id}")
            
            if response_type == "apply":
                return self._handle_application(user_id, pharmacist_name, request_id)
            elif response_type == "decline":
                return self._handle_declination(user_id, pharmacist_name, request_id)
            elif response_type == "details":
                return self._handle_details_request(user_id, pharmacist_name, request_id)
            else:
                logger.error(f"Unknown response type: {response_type}")
                return {"success": False, "error": f"Unknown response type: {response_type}"}
                
        except Exception as e:
            logger.error(f"Error handling pharmacist response: {e}")
            return {"success": False, "error": str(e)}

    def _handle_application(self, user_id: str, pharmacist_name: str, request_id: str) -> Dict[str, Any]:
        """応募処理"""
        try:
            logger.info(f"Handling application from {pharmacist_name}")
            
            # 応募処理を開始
            logger.info(f"Starting application process for {pharmacist_name} (request: {request_id})")
            
            # 確認メッセージを送信
            confirmation_message = TextSendMessage(
                text=f"✅ 応募を受け付けました！\n\n"
                     f"依頼ID: {request_id}\n"
                     f"薬剤師: {pharmacist_name}\n\n"
                     f"店舗からの確定をお待ちください。\n"
                     f"確定次第、ご連絡いたします。"
            )
            
            success = pharmacist_line_bot_service.send_message(user_id, confirmation_message)
            if success:
                logger.info(f"Sent confirmation message to {pharmacist_name}")
            
            # Google Sheetsに応募記録
            logger.info(f"Recording application in Google Sheets for {pharmacist_name}")
            sheets_recorded = self.google_sheets_service.record_application(
                request_id=request_id,
                pharmacist_id=f"pharm_{user_id[-8:]}",
                pharmacist_name=pharmacist_name,
                store_name="メイプル薬局",  # 実際は店舗名を取得
                date=datetime.now().date(),
                time_slot="午前"  # 実際は依頼データから取得
            )
            
            if not sheets_recorded:
                logger.warning(f"Failed to record application in Google Sheets for {pharmacist_name}")
            
            logger.info(f"Application process completed for {pharmacist_name}")
            
            return {
                "success": True,
                "message": f"Pharmacist {pharmacist_name} applied for request {request_id}",
                "sheets_recorded": sheets_recorded,
                "confirmation_sent": success
            }
            
        except Exception as e:
            logger.error(f"Error in application handling: {e}")
            return {"success": False, "error": str(e)}

    def _handle_declination(self, user_id: str, pharmacist_name: str, request_id: str) -> Dict[str, Any]:
        """辞退処理"""
        try:
            logger.info(f"Handling declination from {pharmacist_name}")
            
            # 辞退処理を開始
            logger.info(f"Starting declination process for {pharmacist_name} (request: {request_id})")
            
            # 辞退確認メッセージを送信
            declination_message = TextSendMessage(
                text=f"📝 辞退を受け付けました。\n\n"
                     f"依頼ID: {request_id}\n"
                     f"薬剤師: {pharmacist_name}\n\n"
                     f"ご回答ありがとうございました。\n"
                     f"他の依頼もお待ちしております。"
            )
            
            success = pharmacist_line_bot_service.send_message(user_id, declination_message)
            if success:
                logger.info(f"Sent declination confirmation to {pharmacist_name}")
            
            logger.info(f"Declination process completed for {pharmacist_name}")
            
            return {
                "success": True,
                "message": f"Pharmacist {pharmacist_name} declined request {request_id}",
                "confirmation_sent": success
            }
            
        except Exception as e:
            logger.error(f"Error in declination handling: {e}")
            return {"success": False, "error": str(e)}

    def _handle_details_request(self, user_id: str, pharmacist_name: str, request_id: str) -> Dict[str, Any]:
        """詳細確認処理"""
        try:
            logger.info(f"Handling details request from {pharmacist_name}")
            
            # 詳細確認処理を開始
            logger.info(f"Starting details request process for {pharmacist_name} (request: {request_id})")
            
            # 詳細メッセージを送信
            details_message = TextSendMessage(
                text=f"📋 依頼詳細\n\n"
                     f"依頼ID: {request_id}\n"
                     f"店舗: メイプル薬局\n"
                     f"勤務日: 2025年7月3日\n"
                     f"時間帯: 午前 (9:00-13:00)\n"
                     f"必要人数: 1名\n"
                     f"時給: 2,000円\n"
                     f"交通費: 実費支給\n\n"
                     f"※ 詳細は応募後に店舗からご連絡いたします。"
            )
            
            success = pharmacist_line_bot_service.send_message(user_id, details_message)
            if success:
                logger.info(f"Sent details message to {pharmacist_name}")
            
            logger.info(f"Details request process completed for {pharmacist_name}")
            
            return {
                "success": True,
                "message": f"Details requested for request {request_id}",
                "details_sent": success
            }
            
        except Exception as e:
            logger.error(f"Error in details request handling: {e}")
            return {"success": False, "error": str(e)}


# グローバルインスタンス
pharmacist_notification_service = PharmacistNotificationService() 