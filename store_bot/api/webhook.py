import logging
from typing import Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    TextMessage, 
    PostbackEvent, 
    MessageEvent,
    TextSendMessage,
    TemplateSendMessage,
    ButtonsTemplate,
    PostbackAction,
    FollowEvent,
    UnfollowEvent
)
import re

from store_bot.config import store_settings
from store_bot.services.line_bot_service import store_line_bot_service
from store_bot.services.schedule_service import store_schedule_service
from shared.models.user import Store
from shared.utils.text_parser import parse_shift_request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/store", tags=["store"])

# 店舗ユーザーの一時データ保存
store_temp_data: Dict[str, Dict[str, Any]] = {}

GUIDE_TEXT = (
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


@router.post("/webhook")
async def store_webhook(request: Request):
    """店舗Bot Webhook エンドポイント"""
    try:
        # リクエストボディを取得
        body = await request.body()
        signature = request.headers.get('X-Line-Signature', '')
        
        # 署名を検証
        try:
            store_line_bot_service.handler.handle(body.decode('utf-8'), signature)
        except InvalidSignatureError:
            logger.error("Invalid signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Store webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@store_line_bot_service.handler.add(FollowEvent)
def handle_store_follow(event):
    """店舗ユーザーの友達追加時の処理"""
    try:
        user_id = event.source.user_id
        logger.info(f"New store user followed: {user_id}")
        profile = store_line_bot_service.line_bot_api.get_profile(user_id)
        user_name = profile.display_name
        logger.info(f"Store user profile: {user_name} ({user_id})")
        welcome_message = TextSendMessage(
            text="\U0001F3E5 薬局シフト管理Botへようこそ！\n\n"
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
        store_line_bot_service.line_bot_api.reply_message(
            event.reply_token,
            welcome_message
        )
        logger.info(f"Sent welcome message to store user {user_name} ({user_id})")
    except Exception as e:
        logger.error(f"Error handling store follow event: {e}")
        error_message = TextSendMessage(
            text="\U0001F3E5 薬局シフト管理Botへようこそ！\n\n"
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
        store_line_bot_service.line_bot_api.reply_message(
            event.reply_token,
            error_message
        )


@store_line_bot_service.handler.add(MessageEvent, message=TextMessage)
def handle_store_text_message(event):
    """店舗ユーザーのテキストメッセージ処理"""
    try:
        user_id = event.source.user_id
        message_text = event.message.text
        
        logger.info(f"Received text message from store user {user_id}: {message_text}")
        
        # 勤務依頼の処理
        if "勤務依頼" in message_text or "シフト" in message_text:
            handle_store_shift_request(event, message_text)
            return
        
        # 確認応答の処理
        if message_text in ["はい", "確認", "確定"]:
            handle_store_confirmation_yes(event)
            return
        
        if message_text in ["いいえ", "キャンセル", "取り消し"]:
            handle_store_confirmation_no(event)
            return
        
        # その他のメッセージ
        handle_store_other_messages(event, message_text)
        
    except Exception as e:
        logger.error(f"Error handling store text message: {e}")
        error_message = TextSendMessage(text="申し訳ございません。エラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)


@store_line_bot_service.handler.add(PostbackEvent)
def handle_store_postback(event):
    """店舗ユーザーのポストバックイベント処理"""
    try:
        user_id = event.source.user_id
        postback_data = event.postback.data
        
        logger.info(f"Received postback from store user {user_id}: {postback_data}")
        
        # ポストバックデータを解析
        if postback_data == "select_date":
            handle_store_date_selection(event)
        elif postback_data == "select_time":
            handle_store_time_selection(event)
        elif postback_data == "select_count":
            handle_store_count_selection(event)
        elif postback_data.startswith("date_"):
            handle_store_date_choice(event, postback_data)
        elif postback_data.startswith("time_"):
            handle_store_time_choice(event, postback_data)
        elif postback_data.startswith("count_"):
            handle_store_count_choice(event, postback_data)
        else:
            logger.warning(f"Unknown store postback data: {postback_data}")
            
    except Exception as e:
        logger.error(f"Error handling store postback: {e}")
        error_response = TextSendMessage(text="エラーが発生しました。もう一度お試しください。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_shift_request(event, message_text: str):
    """店舗のシフト依頼処理"""
    try:
        user_id = event.source.user_id
        print(f"[DEBUG] handle_store_shift_request: user_id={user_id}, message_text='{message_text}'")
        
        # メッセージを解析
        parsed_data = parse_shift_request(message_text)
        
        if parsed_data:
            # シフト依頼内容を解析できた場合
            handle_store_parsed_shift_request(event, parsed_data)
        else:
            # 解析できない場合は選択式のフォームを表示
            template = create_store_shift_request_template()
            store_line_bot_service.line_bot_api.reply_message(event.reply_token, template)
            
    except Exception as e:
        logger.error(f"Error in handle_store_shift_request: {e}")
        error_response = TextSendMessage(text="シフト依頼処理中にエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_parsed_shift_request(event, parsed_data):
    """解析済みシフト依頼の処理（店舗）"""
    user_id = event.source.user_id
    print(f"[DEBUG] handle_store_parsed_shift_request: user_id={user_id}, parsed_data={parsed_data}")
    try:
        # 依頼内容を一時保存
        if user_id not in store_temp_data:
            store_temp_data[user_id] = {}
        store_temp_data[user_id]["date"] = parsed_data["date"]
        store_temp_data[user_id]["time_slot"] = parsed_data["time_slot"]
        store_temp_data[user_id]["required_count"] = parsed_data["required_count"]
        store_temp_data[user_id]["notes"] = parsed_data.get("notes", "")
        
        # 依頼内容確認メッセージを見やすく整形
        response = TextSendMessage(
            text=(
                "【依頼内容の確認】\n\n"
                f"📅 日付: {parsed_data['date'].strftime('%Y/%m/%d')}\n"
                f"⏰ 時間帯: {parsed_data['time_slot']}\n"
                f"👥 人数: {parsed_data['required_count']}名\n"
                f"📝 備考: {parsed_data.get('notes', 'なし')}\n\n"
                "この内容で依頼を送信しますか？\n"
                "「はい」または「いいえ」でお答えください。"
            )
        )
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
    except Exception as e:
        logger.error(f"Error in handle_store_parsed_shift_request: {e}")
        error_response = TextSendMessage(text="依頼内容の処理中にエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def create_store_shift_request_template() -> TemplateSendMessage:
    """店舗用シフト依頼テンプレートを作成"""
    buttons = [
        PostbackAction(label="日付選択", data="select_date"),
        PostbackAction(label="時間帯選択", data="select_time"),
        PostbackAction(label="人数選択", data="select_count")
    ]
    
    template = ButtonsTemplate(
        title="勤務依頼",
        text="項目を選択してください",
        actions=buttons
    )
    
    return TemplateSendMessage(alt_text="勤務依頼", template=template)


def get_store_by_user_id(user_id: str) -> Store:
    """ユーザーIDから店舗情報を取得"""
    # 簡易実装
    return Store(
        id=f"store_{user_id}",
        user_id=user_id,
        store_number="001",
        store_name="メイプル薬局",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


def handle_store_date_selection(event):
    """店舗の日付選択処理"""
    try:
        template = TemplateSendMessage(
            alt_text="日付を選択してください",
            template=ButtonsTemplate(
                title="勤務日を選択",
                text="どの日を希望されますか？",
                actions=[
                    PostbackAction(label="今日", data="date_today"),
                    PostbackAction(label="明日", data="date_tomorrow"),
                    PostbackAction(label="明後日", data="date_day_after_tomorrow"),
                    PostbackAction(label="日付を指定", data="date_custom")
                ]
            )
        )
        
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, template)
        
    except Exception as e:
        logger.error(f"Error handling store date selection: {e}")
        error_response = TextSendMessage(text="日付選択でエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_time_selection(event):
    """店舗の時間選択処理"""
    try:
        template = TemplateSendMessage(
            alt_text="時間帯を選択してください",
            template=ButtonsTemplate(
                title="勤務時間帯を選択",
                text="どの時間帯を希望されますか？",
                actions=[
                    PostbackAction(label="午前 (9:00-13:00)", data="time_morning"),
                    PostbackAction(label="午後 (13:00-17:00)", data="time_afternoon"),
                    PostbackAction(label="夜間 (17:00-21:00)", data="time_evening"),
                    PostbackAction(label="終日 (9:00-18:00)", data="time_full_day")
                ]
            )
        )
        
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, template)
        
    except Exception as e:
        logger.error(f"Error handling store time selection: {e}")
        error_response = TextSendMessage(text="時間選択でエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_count_selection(event):
    """店舗の人数選択処理"""
    try:
        template = TemplateSendMessage(
            alt_text="必要人数を選択してください",
            template=ButtonsTemplate(
                title="必要人数を選択",
                text="何名必要ですか？",
                actions=[
                    PostbackAction(label="1名", data="count_1"),
                    PostbackAction(label="2名", data="count_2"),
                    PostbackAction(label="3名", data="count_3"),
                    PostbackAction(label="4名以上", data="count_4_plus")
                ]
            )
        )
        
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, template)
        
    except Exception as e:
        logger.error(f"Error handling store count selection: {e}")
        error_response = TextSendMessage(text="人数選択でエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_date_choice(event, postback_data: str):
    """店舗の日付選択処理"""
    try:
        user_id = event.source.user_id
        # 選択された日付を取得
        if postback_data == "date_today":
            selected_date = datetime.now().date()
        elif postback_data == "date_tomorrow":
            selected_date = (datetime.now() + timedelta(days=1)).date()
        elif postback_data == "date_day_after_tomorrow":
            selected_date = (datetime.now() + timedelta(days=2)).date()
        elif postback_data == "date_custom":
            response = TextSendMessage(
                text="日付を入力してください。\n例: 4/15, 4月15日, 2024/4/15"
            )
            store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        else:
            response = TextSendMessage(text="無効な日付選択です。")
            store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        # 一時データに日付を保存
        if user_id not in store_temp_data:
            store_temp_data[user_id] = {}
        store_temp_data[user_id]["date"] = selected_date
        store_temp_data[user_id]["date_text"] = selected_date.strftime('%Y/%m/%d')
        logger.info(f"Saved date for store user {user_id}: {selected_date}")
        # 次のステップ（時間選択）に進む
        response = TextSendMessage(
            text=f"✅日付: {selected_date.strftime('%Y/%m/%d')}\n次に時間帯を選択してください。"
        )
        time_template = TemplateSendMessage(
            alt_text="時間帯を選択してください",
            template=ButtonsTemplate(
                title="勤務時間帯を選択",
                text="どの時間帯を希望されますか？",
                actions=[
                    PostbackAction(label="午前 (9:00-13:00)", data="time_morning"),
                    PostbackAction(label="午後 (13:00-17:00)", data="time_afternoon"),
                    PostbackAction(label="夜間 (17:00-21:00)", data="time_evening"),
                    PostbackAction(label="終日 (9:00-18:00)", data="time_full_day")
                ]
            )
        )
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, [response, time_template])
    except Exception as e:
        logger.error(f"Error handling store date choice: {e}")
        error_response = TextSendMessage(text="日付選択でエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_time_choice(event, postback_data: str):
    """店舗の時間選択処理"""
    try:
        user_id = event.source.user_id
        
        # 選択された時間帯を取得
        time_mapping = {
            "time_morning": "午前 (9:00-13:00)",
            "time_afternoon": "午後 (13:00-17:00)",
            "time_evening": "夜間 (17:00-21:00)",
            "time_full_day": "終日 (9:00-18:00)"
        }
        
        selected_time = time_mapping.get(postback_data, "不明")
        
        # 一時データに時間を保存
        if user_id not in store_temp_data:
            store_temp_data[user_id] = {}
        store_temp_data[user_id]["time"] = postback_data
        store_temp_data[user_id]["time_text"] = selected_time
        
        logger.info(f"Saved time for store user {user_id}: {selected_time}")
        
        # 次のステップ（人数選択）に進む
        response = TextSendMessage(
            text=f"時間帯: {selected_time}\n次に必要人数を選択してください。"
        )
        count_template = TemplateSendMessage(
            alt_text="必要人数を選択してください",
            template=ButtonsTemplate(
                title="必要人数を選択",
                text="何名必要ですか？",
                actions=[
                    PostbackAction(label="1名", data="count_1"),
                    PostbackAction(label="2名", data="count_2"),
                    PostbackAction(label="3名", data="count_3"),
                    PostbackAction(label="4名以上", data="count_4_plus")
                ]
            )
        )
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, [response, count_template])
        
    except Exception as e:
        logger.error(f"Error handling store time choice: {e}")
        error_response = TextSendMessage(text="時間選択でエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_count_choice(event, postback_data: str):
    """店舗の人数選択処理"""
    try:
        user_id = event.source.user_id
        # 選択された人数を取得
        count_mapping = {
            "count_1": "1名",
            "count_2": "2名",
            "count_3": "3名",
            "count_4_plus": "4名以上"
        }
        selected_count = count_mapping.get(postback_data, "不明")
        # 一時データに人数を保存
        if user_id not in store_temp_data:
            store_temp_data[user_id] = {}
        store_temp_data[user_id]["count"] = postback_data
        store_temp_data[user_id]["count_text"] = selected_count
        logger.info(f"Saved count for store user {user_id}: {selected_count}")
        # 保存された依頼内容を取得
        date = store_temp_data[user_id].get("date")
        if date:
            date_str = date.strftime('%Y/%m/%d')
        else:
            date_str = "未選択"
        time_text = store_temp_data[user_id].get("time_text", "未選択")
        # 依頼内容の確認メッセージを見やすく整形
        response = TextSendMessage(
            text=(
                "【依頼内容の確認】\n\n"
                f"📅 日付: {date_str}\n"
                f"⏰ 時間帯: {time_text}\n"
                f"👥 人数: {selected_count}\n\n"
                "この内容で依頼を送信しますか？\n"
                "「はい」または「いいえ」でお答えください。"
            )
        )
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
    except Exception as e:
        logger.error(f"Error handling store count choice: {e}")
        error_response = TextSendMessage(text="人数選択でエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_confirmation_yes(event):
    """店舗の依頼内容確定処理"""
    try:
        user_id = event.source.user_id
        print(f"[DEBUG] handle_store_confirmation_yes: user_id={user_id}")
        
        # 保存された依頼内容を取得
        temp_data = store_temp_data.get(user_id, {})
        date = temp_data.get("date")
        time_slot = temp_data.get("time_slot")
        required_count = temp_data.get("required_count")
        notes = temp_data.get("notes", "")
        
        if not date or not time_slot or not required_count:
            response = TextSendMessage(text="依頼内容が見つかりません。最初からやり直してください。")
            store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 店舗情報を取得
        store = get_store_by_user_id(user_id)
        if not store:
            response = TextSendMessage(text="店舗情報の取得に失敗しました。")
            store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # シフト依頼を作成・処理
        shift_request = store_schedule_service.create_shift_request(
            store=store,
            target_date=date,
            time_slot=time_slot,
            required_count=int(required_count) if isinstance(required_count, str) else required_count,
            notes=notes
        )
        
        success = store_schedule_service.process_shift_request(shift_request, store)
        
        if success:
            response = TextSendMessage(
                text=f"✅ 依頼を確定しました！\n\n"
                     f"📅 日付: {date.strftime('%Y/%m/%d')}\n"
                     f"⏰ 時間帯: {time_slot}\n"
                     f"👥 人数: {required_count}名\n"
                     f"📝 備考: {notes or 'なし'}\n\n"
                     f"薬剤師に通知を送信しました。\n"
                     f"応募があったらご連絡いたします。"
            )
        else:
            response = TextSendMessage(
                text=f"⚠️ 依頼を確定しましたが、\n"
                     f"空き薬剤師が見つかりませんでした。\n"
                     f"別の日時で再度お試しください。"
            )
        
        # 一時データをクリア
        if user_id in store_temp_data:
            del store_temp_data[user_id]
        
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling store confirmation yes: {e}")
        error_response = TextSendMessage(text="確定処理中にエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_confirmation_no(event):
    """店舗の依頼内容キャンセル処理"""
    try:
        user_id = event.source.user_id
        
        # 一時データをクリア
        if user_id in store_temp_data:
            del store_temp_data[user_id]
        logger.info(f"Cleared temp request for store user {user_id}")
        
        response = TextSendMessage(
            text="依頼をキャンセルしました。\n"
                 "再度「勤務依頼」と入力して、最初からやり直してください。"
        )
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling store confirmation no: {e}")
        error_response = TextSendMessage(text="キャンセル処理中にエラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_store_other_messages(event, message_text: str):
    """店舗のその他のメッセージ処理"""
    try:
        response = TextSendMessage(text=GUIDE_TEXT)
        
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling store other messages: {e}")
        error_message = TextSendMessage(text="申し訳ございません。エラーが発生しました。")
        store_line_bot_service.line_bot_api.reply_message(event.reply_token, error_message) 


def send_guide_message(event):
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
    store_line_bot_service.line_bot_api.reply_message(event.reply_token, TextSendMessage(text=guide_text)) 