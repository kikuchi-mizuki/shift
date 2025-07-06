import logging
from typing import List, Dict, Optional
from datetime import datetime
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import (
    TextSendMessage, 
    TemplateSendMessage, 
    ButtonsTemplate, 
    PostbackAction,
    CarouselTemplate,
    CarouselColumn,
    QuickReply,
    QuickReplyButton,
    MessageAction
)

from app.config import settings
from app.models.schedule import ShiftRequest, TimeSlot, ResponseStatus
from app.models.user import Store, Pharmacist

logger = logging.getLogger(__name__)


class LineBotService:
    def __init__(self):
        self.line_bot_api = LineBotApi(settings.line_channel_access_token)
        self.handler = WebhookHandler(settings.line_channel_secret)

    def send_shift_request_to_pharmacists(
        self, 
        pharmacists: List[Pharmacist], 
        shift_request: ShiftRequest, 
        store: Store
    ) -> bool:
        """薬剤師にシフト依頼を送信"""
        try:
            message = self._create_shift_request_message(shift_request, store)
            
            for pharmacist in pharmacists:
                # 実際の実装では、pharmacist.line_user_idを使用
                # ここでは簡易実装として固定のユーザーIDを使用
                user_id = f"pharmacist_{pharmacist.id}"
                
                try:
                    self.line_bot_api.push_message(user_id, message)
                    logger.info(f"Shift request sent to pharmacist: {pharmacist.name}")
                except LineBotApiError as e:
                    logger.error(f"Failed to send message to {pharmacist.name}: {e}")
                    continue
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending shift requests: {e}")
            return False

    def send_confirmation_to_store(self, store: Store, shift_request: ShiftRequest, confirmed_pharmacists: List[Pharmacist]) -> bool:
        """店舗に確定通知を送信"""
        try:
            message = self._create_confirmation_message(shift_request, confirmed_pharmacists)
            
            # 実際の実装では、store.line_user_idを使用
            user_id = f"store_{store.id}"
            
            self.line_bot_api.push_message(user_id, message)
            logger.info(f"Confirmation sent to store: {store.store_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending confirmation to store: {e}")
            return False

    def send_decline_notification(self, pharmacist: Pharmacist, shift_request: ShiftRequest, store: Store) -> bool:
        """薬剤師に辞退通知を送信"""
        try:
            message = TextSendMessage(
                text=f"【勤務依頼辞退】\n"
                     f"{shift_request.date.strftime('%m/%d')} {shift_request.time_slot.value} "
                     f"{store.store_name}\n"
                     f"他の薬剤師が確定しました。\n"
                     f"ご応募ありがとうございました。"
            )
            
            user_id = f"pharmacist_{pharmacist.id}"
            self.line_bot_api.push_message(user_id, message)
            return True
            
        except Exception as e:
            logger.error(f"Error sending decline notification: {e}")
            return False

    def _create_shift_request_message(self, shift_request: ShiftRequest, store: Store) -> TemplateSendMessage:
        """シフト依頼メッセージを作成"""
        title = f"【勤務確認】{shift_request.date.strftime('%m/%d')} {shift_request.time_slot.value}"
        text = f"{store.store_name}\n"
        
        if shift_request.notes:
            text += f"備考: {shift_request.notes}\n"
        
        text += "勤務可能ですか？"
        
        buttons = [
            PostbackAction(
                label="はい",
                data=f"accept:{shift_request.id}"
            ),
            PostbackAction(
                label="いいえ", 
                data=f"decline:{shift_request.id}"
            ),
            PostbackAction(
                label="条件付きで可",
                data=f"conditional:{shift_request.id}"
            )
        ]
        
        template = ButtonsTemplate(
            title=title,
            text=text,
            actions=buttons
        )
        
        return TemplateSendMessage(alt_text=title, template=template)

    def _create_confirmation_message(self, shift_request: ShiftRequest, confirmed_pharmacists: List[Pharmacist]) -> TextSendMessage:
        """確定通知メッセージを作成"""
        pharmacist_names = ", ".join([p.name for p in confirmed_pharmacists])
        
        text = f"【勤務確定】\n"
        text += f"日時: {shift_request.date.strftime('%m/%d')} {shift_request.time_slot.value}\n"
        text += f"確定薬剤師: {pharmacist_names}\n"
        text += f"スケジュールに記入しました。"
        
        return TextSendMessage(text=text)

    def create_shift_request_quick_reply(self) -> QuickReply:
        """シフト依頼用のクイックリプライを作成"""
        items = [
            QuickReplyButton(
                action=MessageAction(label="AM", text="AM")
            ),
            QuickReplyButton(
                action=MessageAction(label="PM", text="PM")
            ),
            QuickReplyButton(
                action=MessageAction(label="終日", text="終日")
            )
        ]
        
        return QuickReply(items=items)

    def create_number_quick_reply(self) -> QuickReply:
        """人数選択用のクイックリプライを作成"""
        items = [
            QuickReplyButton(
                action=MessageAction(label="1名", text="1")
            ),
            QuickReplyButton(
                action=MessageAction(label="2名", text="2")
            ),
            QuickReplyButton(
                action=MessageAction(label="3名", text="3")
            )
        ]
        
        return QuickReply(items=items) 