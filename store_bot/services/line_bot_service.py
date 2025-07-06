import logging
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    TextSendMessage,
    TemplateSendMessage,
    ButtonsTemplate,
    PostbackAction
)

from store_bot.config import store_settings

logger = logging.getLogger(__name__)


class StoreLineBotService:
    def __init__(self):
        self.line_bot_api = LineBotApi(store_settings.store_line_channel_access_token)
        self.handler = WebhookHandler(store_settings.store_line_channel_secret)
        logger.info("Store Line Bot service initialized")

    def send_message(self, user_id: str, message: TextSendMessage):
        """メッセージを送信"""
        try:
            self.line_bot_api.push_message(user_id, message)
            logger.info(f"Message sent to store user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send message to store user {user_id}: {e}")
            return False

    def send_template_message(self, user_id: str, template: TemplateSendMessage):
        """テンプレートメッセージを送信"""
        try:
            self.line_bot_api.push_message(user_id, template)
            logger.info(f"Template message sent to store user: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to send template message to store user {user_id}: {e}")
            return False

    def reply_message(self, reply_token: str, message):
        """リプライメッセージを送信"""
        try:
            self.line_bot_api.reply_message(reply_token, message)
            logger.info(f"Reply message sent to store user")
            return True
        except Exception as e:
            logger.error(f"Failed to send reply message: {e}")
            return False


# グローバルインスタンス
store_line_bot_service = StoreLineBotService() 