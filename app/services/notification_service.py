import logging
from typing import List, Optional
from datetime import datetime
import redis

from app.config import settings
from app.models.schedule import ShiftRequest, PharmacistResponse
from app.models.user import Store, Pharmacist
from app.services.line_bot_service import LineBotService

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.line_bot_service = LineBotService()
        self.redis_client = redis.from_url(settings.redis_url)

    def send_shift_request_notification(self, shift_request: ShiftRequest, store: Store, pharmacists: List[Pharmacist]) -> bool:
        """シフト依頼通知を送信"""
        try:
            # 通知履歴を記録
            notification_key = f"notification:shift_request:{shift_request.id}"
            notification_data = {
                "shift_request_id": shift_request.id,
                "store_id": store.id,
                "pharmacist_count": len(pharmacists),
                "sent_at": datetime.now().isoformat(),
                "status": "sent"
            }
            
            self.redis_client.hmset(notification_key, notification_data)
            self.redis_client.expire(notification_key, 86400)  # 24時間で期限切れ
            
            # LINE Botで通知送信
            success = self.line_bot_service.send_shift_request_to_pharmacists(
                pharmacists, shift_request, store
            )
            
            if success:
                logger.info(f"Shift request notification sent to {len(pharmacists)} pharmacists")
            else:
                logger.error("Failed to send shift request notifications")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending shift request notification: {e}")
            return False

    def send_confirmation_notification(self, shift_request: ShiftRequest, store: Store, confirmed_pharmacists: List[Pharmacist]) -> bool:
        """確定通知を送信"""
        try:
            # 店舗に確定通知
            store_success = self.line_bot_service.send_confirmation_to_store(
                store, shift_request, confirmed_pharmacists
            )
            
            # 確定薬剤師に確定通知
            pharmacist_success = self._send_confirmation_to_pharmacists(
                confirmed_pharmacists, shift_request, store
            )
            
            # 通知履歴を記録
            notification_key = f"notification:confirmation:{shift_request.id}"
            notification_data = {
                "shift_request_id": shift_request.id,
                "store_id": store.id,
                "confirmed_pharmacists": [p.id for p in confirmed_pharmacists],
                "sent_at": datetime.now().isoformat(),
                "status": "confirmed"
            }
            
            self.redis_client.hmset(notification_key, notification_data)
            self.redis_client.expire(notification_key, 86400)
            
            return store_success and pharmacist_success
            
        except Exception as e:
            logger.error(f"Error sending confirmation notification: {e}")
            return False

    def send_decline_notifications(self, shift_request: ShiftRequest, store: Store, declined_pharmacists: List[Pharmacist]) -> bool:
        """辞退通知を送信"""
        try:
            success_count = 0
            
            for pharmacist in declined_pharmacists:
                success = self.line_bot_service.send_decline_notification(
                    pharmacist, shift_request, store
                )
                if success:
                    success_count += 1
            
            logger.info(f"Decline notifications sent to {success_count}/{len(declined_pharmacists)} pharmacists")
            return success_count == len(declined_pharmacists)
            
        except Exception as e:
            logger.error(f"Error sending decline notifications: {e}")
            return False

    def send_reminder_notification(self, shift_request: ShiftRequest, store: Store, unresponded_pharmacists: List[Pharmacist]) -> bool:
        """リマインダー通知を送信"""
        try:
            # リマインダー通知の履歴をチェック
            reminder_key = f"reminder:shift_request:{shift_request.id}"
            reminder_count = self.redis_client.get(reminder_key)
            
            if reminder_count and int(reminder_count) >= 2:
                logger.info(f"Maximum reminder count reached for shift request: {shift_request.id}")
                return False
            
            # リマインダー通知を送信
            message = self._create_reminder_message(shift_request, store)
            
            success_count = 0
            for pharmacist in unresponded_pharmacists:
                try:
                    user_id = f"pharmacist_{pharmacist.id}"
                    self.line_bot_service.line_bot_api.push_message(user_id, message)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send reminder to {pharmacist.name}: {e}")
            
            # リマインダー回数を記録
            self.redis_client.incr(reminder_key)
            self.redis_client.expire(reminder_key, 3600)  # 1時間で期限切れ
            
            logger.info(f"Reminder notifications sent to {success_count}/{len(unresponded_pharmacists)} pharmacists")
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Error sending reminder notification: {e}")
            return False

    def _send_confirmation_to_pharmacists(self, pharmacists: List[Pharmacist], shift_request: ShiftRequest, store: Store) -> bool:
        """確定薬剤師に確定通知を送信"""
        try:
            from linebot.models import TextSendMessage
            
            message = TextSendMessage(
                text=f"【勤務確定】\n"
                     f"{shift_request.date.strftime('%m/%d')} {shift_request.time_slot.value} "
                     f"{store.store_name}\n"
                     f"勤務が確定しました。\n"
                     f"よろしくお願いします。"
            )
            
            success_count = 0
            for pharmacist in pharmacists:
                try:
                    user_id = f"pharmacist_{pharmacist.id}"
                    self.line_bot_service.line_bot_api.push_message(user_id, message)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send confirmation to {pharmacist.name}: {e}")
            
            return success_count == len(pharmacists)
            
        except Exception as e:
            logger.error(f"Error sending confirmation to pharmacists: {e}")
            return False

    def _create_reminder_message(self, shift_request: ShiftRequest, store: Store):
        """リマインダーメッセージを作成"""
        from linebot.models import TextSendMessage
        
        text = f"【勤務依頼リマインダー】\n"
        text += f"{shift_request.date.strftime('%m/%d')} {shift_request.time_slot.value} "
        text += f"{store.store_name}\n"
        text += f"まだご回答いただいていません。\n"
        text += f"ご確認をお願いします。"
        
        return TextSendMessage(text=text)

    def get_notification_history(self, shift_request_id: str) -> dict:
        """通知履歴を取得"""
        try:
            notification_key = f"notification:shift_request:{shift_request_id}"
            confirmation_key = f"notification:confirmation:{shift_request_id}"
            
            shift_request_data = self.redis_client.hgetall(notification_key)
            confirmation_data = self.redis_client.hgetall(confirmation_key)
            
            return {
                "shift_request": shift_request_data,
                "confirmation": confirmation_data
            }
            
        except Exception as e:
            logger.error(f"Error getting notification history: {e}")
            return {} 