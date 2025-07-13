import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends
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
    UnfollowEvent,
    QuickReply,
    QuickReplyButton,
    FlexSendMessage
)
from dateutil.parser import parse as parse_date
from fastapi.responses import JSONResponse
import re

from app.config import settings
from app.services.line_bot_service import LineBotService
from app.services.schedule_service import ScheduleService
from app.services.google_sheets_service import GoogleSheetsService
from app.services.pharmacist_notification_service import PharmacistNotificationService
from app.services.user_management_service import UserManagementService, UserType
from app.models.schedule import TimeSlot, ResponseStatus
from app.models.user import Store, Pharmacist
from app.utils.text_parser import parse_shift_request, parse_pharmacist_response
from shared.services.request_manager import request_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/line", tags=["line"])

line_bot_service = LineBotService()
schedule_service = ScheduleService()
google_sheets_service = GoogleSheetsService()
pharmacist_notification_service = PharmacistNotificationService()
user_management_service = UserManagementService()

# 一時的な依頼内容保存（実際はRedis/DBを使用）
temp_requests: Dict[str, Dict[str, Any]] = {}

# --- 案内文統一 ---
WELCOME_GUIDE = (
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
async def line_webhook(request: Request):
    """LINE Bot Webhook エンドポイント"""
    try:
        # リクエストボディを取得
        body = await request.body()
        signature = request.headers.get('X-Line-Signature', '')
        
        # 署名を検証
        try:
            line_bot_service.handler.handle(body.decode('utf-8'), signature)
        except InvalidSignatureError:
            logger.error("Invalid signature")
            raise HTTPException(status_code=400, detail="Invalid signature")
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        # LINE Bot APIのエラーは通常のHTTPエラーとして扱わない
        if "Invalid reply token" in str(e) or "must be non-empty text" in str(e):
            logger.warning(f"LINE Bot API error (non-critical): {e}")
            return {"status": "ok"}
        else:
            raise HTTPException(status_code=500, detail="Internal server error")


@line_bot_service.handler.add(FollowEvent)
def handle_follow(event):
    """友達追加時の処理"""
    try:
        user_id = event.source.user_id
        logger.info(f"New user followed: {user_id}")
        
        # ユーザープロフィールを取得
        profile = line_bot_service.line_bot_api.get_profile(user_id)
        user_name = profile.display_name
        logger.info(f"User profile: {user_name} ({user_id})")
        
        # ユーザー情報を保存
        user_management_service.set_user_info(user_id, {
            "display_name": user_name,
            "profile_picture": profile.picture_url,
            "status_message": profile.status_message,
            "followed_at": datetime.now().isoformat()
        })
        
        # 既存ユーザーか判定
        user_type = user_management_service.get_user_type(user_id)
        if user_type == UserType.UNKNOWN:
            welcome_message = TextSendMessage(text=WELCOME_GUIDE)
            line_bot_service.line_bot_api.reply_message(event.reply_token, welcome_message)
            logger.info(f"Sent welcome message to {user_id}")
        else:
            notify_message = TextSendMessage(text="シフト依頼があったら、今後はBotから通知が届きます！")
            line_bot_service.line_bot_api.reply_message(event.reply_token, notify_message)
            logger.info(f"Sent notify message to registered user {user_id}")
    except Exception as e:
        logger.error(f"Error handling follow event: {e}")
        # エラー時は基本的なメッセージを送信
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
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)


@line_bot_service.handler.add(UnfollowEvent)
def handle_unfollow(event):
    """友達削除時の処理"""
    try:
        user_id = event.source.user_id
        logger.info(f"User unfollowed: {user_id}")
        
        # 必要に応じてデータベースから削除
        # TODO: 薬剤師情報をデータベースから削除
        
    except Exception as e:
        logger.error(f"Error handling unfollow event: {e}")


@line_bot_service.handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_id = event.source.user_id
    # 追加: user_id, user_typeのデバッグ出力
    session = user_management_service.get_or_create_session(user_id)
    user_type = session.user_type
    print(f"[DEBUG] handle_text_message: user_id={user_id}, user_type={user_type}")
    print(f"get_temp_data check: user_id={user_id}, key=custom_date_waiting, value={user_management_service.get_temp_data(user_id, 'custom_date_waiting')}")
    # カスタム日付入力待ちの場合は最優先で処理
    if user_management_service.get_temp_data(user_id, "custom_date_waiting"):
        try:
            input_text = event.message.text.strip()
            dt = parse_date(input_text, fuzzy=True)
            user_management_service.set_temp_data(user_id, "date", dt.date())
            user_management_service.set_temp_data(user_id, "date_text", input_text)
            user_management_service.set_temp_data(user_id, "custom_date_waiting", False)
            # 次のステップへ
            messages = handle_start_time_period_selection(event)
            if messages:
                line_bot_service.line_bot_api.reply_message(event.reply_token, messages[0])
                for m in messages[1:]:
                    line_bot_service.line_bot_api.push_message(user_id, m)
            return
        except Exception:
            response = TextSendMessage(text="日付の形式が正しくありません。例: 4/15, 4月15日, 2024/4/15")
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
    try:
        message_text = event.message.text
        
        logger.info(f"Received text message from {user_id}: {message_text}")
        
        # ユーザーセッションを取得
        session = user_management_service.get_or_create_session(user_id)
        user_type = session.user_type
        
        logger.info(f"User {user_id} type: {user_type.value}")
        
        # テスト用コマンドの処理
        if message_text.startswith("テスト"):
            handle_test_commands(event, message_text)
            return
        
        # デバッグ用コマンドの処理
        if message_text.startswith("デバッグ"):
            handle_debug_commands(event, message_text)
            return
        
        # ユーザータイプ登録処理
        if message_text == "店舗登録":
            handle_store_registration(event)
            return
        
        # 店舗登録処理（詳細情報）
        if message_text.startswith("店舗登録"):
            handle_store_registration_detailed(event, message_text)
            return
        
        if message_text == "薬剤師登録":
            handle_pharmacist_registration_prompt(event)
            return
        
        # 薬剤師登録処理（詳細情報）
        if message_text.startswith("登録"):
            if user_type == UserType.UNKNOWN or user_type == UserType.PHARMACIST:
                # 柔軟な区切り文字対応
                parts = re.split(r'[ ,、\u3000]+', message_text)
                if len(parts) < 4:
                    help_message = TextSendMessage(
                        text="📝 登録フォーマットが正しくありません。\n\n"
                             "正しいフォーマット：\n"
                             "登録 [名前] [電話番号] [対応可能時間]\n\n"
                             "例：登録 田中太郎 090-1234-5678 午前,午後\n\n"
                             "対応可能時間の選択肢：\n"
                             "• 午前 (9:00-13:00)\n"
                             "• 午後 (13:00-17:00)\n"
                             "• 夜間 (17:00-21:00)\n"
                             "• 終日"
                    )
                    line_bot_service.line_bot_api.reply_message(event.reply_token, help_message)
                    return
                name = parts[1]
                phone = parts[2]
                availability = parts[3:]
                # ユーザープロフィールを取得
                profile = line_bot_service.line_bot_api.get_profile(user_id)
                
                # 薬剤師情報をGoogle Sheetsに登録
                pharmacist_data = {
                    "id": f"pharm_{user_id[-8:]}",  # ユーザーIDの後8文字を使用
                    "user_id": user_id,
                    "name": name,
                    "phone": phone,
                    "availability": availability,
                    "rating": 0.0,
                    "experience_years": 0,
                    "registered_at": datetime.now().isoformat()
                }
                
                # Google Sheetsに登録
                success = google_sheets_service.register_pharmacist(pharmacist_data)
                
                if success:
                    user_management_service.set_user_type(user_id, UserType.PHARMACIST)
                    confirmation_message = TextSendMessage(
                        text=f"✅ 薬剤師登録が完了しました！\n\n"
                             f"📋 登録情報：\n"
                             f"• 名前: {name}\n"
                             f"• 電話番号: {phone}\n"
                             f"• 対応可能時間: {', '.join(availability)}\n\n"
                             f"これで勤務依頼の通知を受け取ることができます。\n"
                             f"「勤務依頼」と入力してテストしてみてください。"
                    )
                    line_bot_service.line_bot_api.reply_message(event.reply_token, confirmation_message)
                    # 追加: 登録済みユーザー案内をpush_messageで送信
                    line_bot_service.line_bot_api.push_message(user_id, TextSendMessage(text="シフト依頼があったら、今後はBotから通知が届きます！"))
                else:
                    confirmation_message = TextSendMessage(
                        text="❌ 登録処理中にエラーが発生しました。\n"
                             "しばらく時間をおいて再度お試しください。"
                    )
                
                line_bot_service.line_bot_api.reply_message(event.reply_token, confirmation_message)
                
                logger.info(f"Pharmacist registration completed for {name} ({user_id})")
            else:
                response = TextSendMessage(
                    text="店舗ユーザーは薬剤師登録できません。\n"
                         "勤務依頼の送信のみ可能です。"
                )
                line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return

        # 確認応答の処理（最優先）
        if message_text in ["はい", "確認", "確定"]:
            print(f"[DEBUG] handle_text_message: entering handle_confirmation_yes for user_id={user_id}, message_text={message_text}")
            handle_confirmation_yes(event)
            return

        # 登録済み店舗ユーザーは何か送ったら即シフト依頼
        if user_type == UserType.STORE:
            handle_shift_request(event, message_text)
            return

        # 従来の勤務依頼ワード判定・薬剤師ユーザー向け分岐は不要になる
        # その他のメッセージ
        handle_other_messages(event, message_text)
        
    except Exception as e:
        logger.error(f"Error handling text message: {e}")
        # 既にreply_messageが呼ばれている可能性があるため、push_messageを使用
        try:
            error_message = TextSendMessage(text="申し訳ございません。エラーが発生しました。")
            line_bot_service.line_bot_api.push_message(event.source.user_id, error_message)
        except Exception as push_error:
            logger.error(f"Error sending error message: {push_error}")


@line_bot_service.handler.add(PostbackEvent)
def handle_postback(event):
    """ポストバックイベントの処理（ボタンクリックなど）"""
    user_id = event.source.user_id
    postback_data = event.postback.data
    print(f"handle_postback: postback_data={postback_data!r}")
    try:
        if postback_data in ["はい", "確認", "確定", "accept", "ok", "yes"] or postback_data.startswith("accept:"):
            print(f"[DEBUG] handle_postback: entering handle_confirmation_yes for user_id={user_id}, postback_data={postback_data}")
            handle_confirmation_yes(event)
            return
        if postback_data.startswith("decline:"):
            print(f"[DEBUG] handle_postback: entering handle_decline_response for user_id={user_id}, postback_data={postback_data}")
            handle_decline_response(event, postback_data)
            return
        if postback_data.startswith("conditional:"):
            print(f"[DEBUG] handle_postback: entering handle_conditional_response for user_id={user_id}, postback_data={postback_data}")
            handle_conditional_response(event, postback_data)
            return
        logger.info(f"Received postback from {user_id}: {postback_data}")
        # シフト依頼ボタン押下時の処理を追加
        if postback_data == "shift_request_start":
            handle_shift_request(event, "")
            return
        # 既存の分岐はそのまま
        if postback_data == "select_date":
            handle_date_selection(event)
        elif postback_data == "date_custom":
            print(f"handle_postback: postback_data={postback_data}")
            print("INTO date_custom branch")
            print(f"set_temp_data called: user_id={user_id}, key=custom_date_waiting, value=True")
            user_management_service.set_temp_data(user_id, "custom_date_waiting", True)
            print(f"set_temp_data finished")
            response = TextSendMessage(
                text="日付を入力してください。\n例: 4/15, 4月15日, 2024/4/15"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            print("REPLY sent, RETURNING")
            return
        elif postback_data.startswith("date_"):
            handle_date_choice(event, postback_data)
        elif postback_data == "select_start_time":
            handle_start_time_period_selection(event)
        elif postback_data == "start_time_morning":
            messages = handle_start_time_detail_selection(event, "morning")
            if messages:
                line_bot_service.line_bot_api.reply_message(event.reply_token, messages[0])
                for m in messages[1:]:
                    line_bot_service.line_bot_api.push_message(user_id, m)
        elif postback_data == "start_time_afternoon":
            messages = handle_start_time_detail_selection(event, "afternoon")
            if messages:
                line_bot_service.line_bot_api.reply_message(event.reply_token, messages[0])
                for m in messages[1:]:
                    line_bot_service.line_bot_api.push_message(user_id, m)
        elif postback_data.startswith("start_time_"):
            # 細かい時間を一時保存し、次のステップ（終了時間選択など）へ
            user_management_service.set_temp_data(user_id, "start_time", postback_data)
            # 勤務終了時間選択フローへ
            messages = handle_end_time_selection(event)
            if messages:
                line_bot_service.line_bot_api.reply_message(event.reply_token, messages[0])
                for m in messages[1:]:
                    line_bot_service.line_bot_api.push_message(user_id, m)
            return
        elif postback_data.startswith("accept:"):
            handle_accept_response(event, postback_data)
        elif postback_data.startswith("decline:"):
            handle_decline_response(event, postback_data)
        elif postback_data.startswith("conditional:"):
            handle_conditional_response(event, postback_data)
        elif postback_data.startswith("pharmacist_apply:"):
            print(f"[DEBUG] Calling handle_pharmacist_apply with data: {postback_data}")
            handle_pharmacist_apply(event, postback_data)
        elif postback_data.startswith("pharmacist_decline:"):
            print(f"[DEBUG] Calling handle_pharmacist_decline with data: {postback_data}")
            handle_pharmacist_decline(event, postback_data)
        elif postback_data.startswith("pharmacist_details:"):
            print(f"[DEBUG] Calling handle_pharmacist_details with data: {postback_data}")
            handle_pharmacist_details(event, postback_data)
        elif postback_data == "select_time":
            handle_time_selection(event)
        elif postback_data == "select_count":
            handle_count_selection(event)
        elif postback_data.startswith("time_"):
            handle_time_choice(event, postback_data)
        elif postback_data.startswith("count_"):
            handle_count_choice(event, postback_data)
        elif postback_data in ["end_band_day", "end_band_evening", "end_band_night"]:
            messages = handle_end_time_band_detail_selection(event, postback_data)
            if messages:
                line_bot_service.line_bot_api.reply_message(event.reply_token, messages[0])
                for m in messages[1:]:
                    line_bot_service.line_bot_api.push_message(user_id, m)
            return
        elif postback_data.startswith("end_time_"):
            # 勤務終了時間を一時保存し、次のステップへ
            user_management_service.set_temp_data(user_id, "end_time", postback_data)
            messages = handle_break_time_selection(event)
            if messages:
                line_bot_service.line_bot_api.reply_message(event.reply_token, messages[0])
                for m in messages[1:]:
                    line_bot_service.line_bot_api.push_message(user_id, m)
            return
        elif postback_data.startswith("break_"):
            # 休憩時間を一時保存し、次のステップ（人数設定）へ
            user_management_service.set_temp_data(user_id, "break_time", postback_data)
            messages = handle_count_selection(event)
            if messages:
                line_bot_service.line_bot_api.reply_message(event.reply_token, messages[0])
                for m in messages[1:]:
                    line_bot_service.line_bot_api.push_message(user_id, m)
            return
        elif postback_data.startswith("pharmacist_confirm_accept:"):
            handle_pharmacist_confirm_accept(event, postback_data)
        elif postback_data.startswith("pharmacist_confirm_reject:"):
            handle_pharmacist_confirm_reject(event, postback_data)
        else:
            print(f"[DEBUG] Unknown postback data: {postback_data}")
            logger.warning(f"Unknown postback data: {postback_data}")
            
    except Exception as e:
        print(f"[DEBUG] Error in handle_postback: {e}")
        logger.error(f"Error handling postback: {e}")
        # 既にreply_messageが呼ばれている可能性があるため、push_messageを使用
        try:
            error_response = TextSendMessage(text="エラーが発生しました。もう一度お試しください。")
            line_bot_service.line_bot_api.push_message(event.source.user_id, error_response)
        except Exception as push_error:
            logger.error(f"Error sending error message: {push_error}")


def handle_shift_request(event, message_text: str, use_push: bool = False):
    user_id = event.source.user_id
    print(f"[DEBUG] handle_shift_request: user_id={user_id}, message_text='{message_text}'")
    store = get_store_by_user_id(user_id)
    print(f"[DEBUG] handle_shift_request: store={store}")
    logger.info(f"[DEBUG] handle_shift_request called with message_text='{message_text}'")
    with open("debug.txt", "a") as f:
        f.write("handle_shift_request called\n")
    print('[handle_shift_request] called')
    try:
        print("[DEBUG] handle_shift_request: calling get_store_by_user_id...")
        if not store:
            logger.info(f"[handle_shift_request] get_store_by_user_id failed for user_id={user_id}")
            print(f"[handle_shift_request] get_store_by_user_id failed for user_id={user_id}")
            response = TextSendMessage(
                text="🏪 勤務依頼を送信するには、まず店舗登録が必要です。\n\n"
                     "以下のいずれかの方法で登録してください：\n\n"
                     "1️⃣ 店舗登録（勤務依頼を送信）\n"
                     "→ 「店舗登録」と入力\n\n"
                     "2️⃣ 薬剤師登録（勤務依頼を受信）\n"
                     "→ 「薬剤師登録」と入力\n\n"
                     "どちらを選択されますか？"
            )
            if use_push:
                line_bot_service.line_bot_api.push_message(user_id, response)
            else:
                line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        logger.info(f"[handle_shift_request] store found: {store}")
        print(f"[handle_shift_request] store found: {store}")
        # 登録済み店舗ユーザーは何か送ったら即シフト依頼フロー開始
        parsed_data = parse_shift_request(message_text)
        if parsed_data:
            # シフト依頼内容を解析できた場合
            handle_parsed_shift_request(event, parsed_data, store)
        else:
            # 解析できない場合は選択式のフォームを表示
            template = create_shift_request_template()
            if use_push:
                line_bot_service.line_bot_api.push_message(user_id, template)
            else:
                line_bot_service.line_bot_api.reply_message(event.reply_token, template)
    except Exception as e:
        logger.error(f"Error in handle_shift_request: {e}")
        error_response = TextSendMessage(text="シフト依頼処理中にエラーが発生しました。")
        if use_push:
            line_bot_service.line_bot_api.push_message(user_id, error_response)
        else:
            line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_registration(event, message_text: str):
    """ユーザー登録の処理"""
    try:
        # 簡易的な登録処理（実際はデータベースに保存）
        user_id = event.source.user_id
        
        # 店舗として登録（実際はユーザータイプを判定する必要がある）
        store = Store(
            id=f"store_{user_id}",
            user_id=user_id,
            store_number="001",
            store_name="メイプル薬局",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        response = TextSendMessage(
            text="店舗登録が完了しました。\n"
                 "勤務依頼を送信できます。\n"
                 "例: 【勤務依頼】6/28（火）AM 1名 9:00スタート希望"
        )
        
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling registration: {e}")
        error_response = TextSendMessage(text="登録処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_accept_response(event, postback_data: str):
    """薬剤師の承諾応答を処理"""
    try:
        shift_request_id = postback_data.split(":")[1]
        user_id = event.source.user_id
        
        pharmacist = get_pharmacist_by_user_id(user_id)
        if not pharmacist:
            response = TextSendMessage(text="薬剤師登録が必要です。")
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 応答を処理
        success = schedule_service.handle_pharmacist_response(
            pharmacist=pharmacist,
            shift_request_id=shift_request_id,
            response=ResponseStatus.ACCEPTED
        )
        
        if success:
            response = TextSendMessage(text="勤務を承諾しました。確定次第、ご連絡いたします。")
        else:
            response = TextSendMessage(text="申し訳ございません。既に他の薬剤師が確定しました。")
        
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling accept response: {e}")
        error_response = TextSendMessage(text="応答処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_decline_response(event, postback_data: str):
    """薬剤師の辞退応答を処理"""
    try:
        shift_request_id = postback_data.split(":")[1]
        user_id = event.source.user_id
        
        pharmacist = get_pharmacist_by_user_id(user_id)
        if not pharmacist:
            response = TextSendMessage(text="薬剤師登録が必要です。")
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 応答を処理
        success = schedule_service.handle_pharmacist_response(
            pharmacist=pharmacist,
            shift_request_id=shift_request_id,
            response=ResponseStatus.DECLINED
        )
        
        response = TextSendMessage(text="ご回答ありがとうございました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling decline response: {e}")
        error_response = TextSendMessage(text="応答処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_conditional_response(event, postback_data: str):
    """薬剤師の条件付き応答を処理"""
    try:
        shift_request_id = postback_data.split(":")[1]
        user_id = event.source.user_id
        
        pharmacist = get_pharmacist_by_user_id(user_id)
        if not pharmacist:
            response = TextSendMessage(text="薬剤師登録が必要です。")
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 条件を入力してもらうメッセージを送信
        response = TextSendMessage(text="条件を入力してください。\n例: 10時以降可")
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling conditional response: {e}")
        error_response = TextSendMessage(text="応答処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def create_shift_request_template() -> TemplateSendMessage:
    """シフト依頼用のテンプレートを作成（日付選択を直接表示）"""
    template = ButtonsTemplate(
        title="シフト依頼",
        text="日付を選択してください",
        actions=[
            PostbackAction(label="今日", data="date_today"),
            PostbackAction(label="明日", data="date_tomorrow"),
            PostbackAction(label="明後日", data="date_day_after_tomorrow"),
            PostbackAction(label="日付を指定", data="date_custom")
        ]
    )
    return TemplateSendMessage(alt_text="日付を選択してください", template=template)


def get_store_by_user_id(user_id: str) -> Optional[Store]:
    stores = google_sheets_service.get_store_list(sheet_name="店舗登録")
    logger.info(f"[DEBUG] get_store_by_user_id: searching for user_id='{user_id}'")
    print(f"[DEBUG] get_store_by_user_id: searching for user_id='{user_id}'")
    for store in stores:
        logger.info(f"[DEBUG] store: number='{store.get('number')}', name='{store.get('name')}', user_id='{store.get('user_id')}'")
        print(f"[DEBUG] store: number='{store.get('number')}', name='{store.get('name')}', user_id='{store.get('user_id')}'")
        if store.get("user_id", "").strip() == user_id.strip():
            logger.info(f"[DEBUG] MATCHED user_id: '{user_id}' with store: {store}")
            print(f"[DEBUG] MATCHED user_id: '{user_id}' with store: {store}")
            return Store(
                id=f"store_{store['number']}",
                user_id=user_id,
                store_number=store["number"],
                store_name=store["name"],
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
    logger.info(f"[DEBUG] get_store_by_user_id: no match for user_id='{user_id}'")
    print(f"[DEBUG] get_store_by_user_id: no match for user_id='{user_id}'")
    return None


def get_pharmacist_by_user_id(user_id: str) -> Optional[Pharmacist]:
    """ユーザーIDから薬剤師を取得（簡易実装）"""
    # 実際はデータベースから取得
    return Pharmacist(
        id=f"pharmacist_{user_id}",
        user_id=user_id,
        name="薬剤師太郎",
        phone="090-1234-5678",
        created_at=datetime.now(),
        updated_at=datetime.now()
    )


def handle_date_selection(event):
    """日付選択の処理"""
    try:
        # 日付選択のテンプレートを作成
        template = TemplateSendMessage(
            alt_text="日付を選択してください",
            template=ButtonsTemplate(
                title="勤務日を選択",
                text="どの日を希望されますか？",
                actions=[
                    PostbackAction(
                        label="今日",
                        data="date_today"
                    ),
                    PostbackAction(
                        label="明日", 
                        data="date_tomorrow"
                    ),
                    PostbackAction(
                        label="明後日",
                        data="date_day_after_tomorrow"
                    ),
                    PostbackAction(
                        label="日付を指定",
                        data="date_custom"
                    )
                ]
            )
        )
        
        line_bot_service.line_bot_api.reply_message(event.reply_token, template)
        
    except Exception as e:
        logger.error(f"Error handling date selection: {e}")
        error_response = TextSendMessage(text="日付選択でエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_time_selection(event):
    """時間選択の処理"""
    try:
        # 時間選択のテンプレートを作成
        template = TemplateSendMessage(
            alt_text="時間帯を選択してください",
            template=ButtonsTemplate(
                title="勤務時間帯を選択",
                text="どの時間帯を希望されますか？",
                actions=[
                    PostbackAction(
                        label="午前 (9:00-13:00)",
                        data="time_morning"
                    ),
                    PostbackAction(
                        label="午後 (13:00-17:00)",
                        data="time_afternoon"
                    ),
                    PostbackAction(
                        label="夜間 (17:00-21:00)",
                        data="time_evening"
                    ),
                    PostbackAction(
                        label="終日 (9:00-18:00)",
                        data="time_full_day"
                    )
                ]
            )
        )
        
        line_bot_service.line_bot_api.reply_message(event.reply_token, template)
        
    except Exception as e:
        logger.error(f"Error handling time selection: {e}")
        error_response = TextSendMessage(text="時間選択でエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_count_selection(event):
    """人数選択の処理"""
    try:
        # 人数選択のテンプレートを送信（遅延なしで直接送信）
        count_template = TemplateSendMessage(
            alt_text="必要人数を選択してください",
            template=ButtonsTemplate(
                title="必要人数を選択",
                text="何名必要ですか？",
                actions=[
                    PostbackAction(
                        label="1名",
                        data="count_1"
                    ),
                    PostbackAction(
                        label="2名",
                        data="count_2"
                    ),
                    PostbackAction(
                        label="3名以上",
                        data="count_3_plus"
                    )
                ]
            )
        )
        # 直接push_messageで送信
        line_bot_service.line_bot_api.push_message(event.source.user_id, count_template)
    except Exception as e:
        logger.error(f"Error handling count selection: {e}")
        error_response = TextSendMessage(text="人数選択でエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_date_choice(event, postback_data: str):
    """日付選択の処理"""
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
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        else:
            response = TextSendMessage(text="無効な日付選択です。")
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        # ユーザー管理サービスに日付を保存
        user_management_service.set_temp_data(user_id, "date", selected_date)
        user_management_service.set_temp_data(user_id, "date_text", selected_date.strftime('%Y/%m/%d'))
        logger.info(f"Saved date for user {user_id}: {selected_date}")
        # 次のステップ（勤務開始時間帯選択）に進む
        response = TextSendMessage(
            text=f"✅日付: {selected_date.strftime('%Y/%m/%d')}\n次に勤務開始時間帯を選択してください。"
        )
        messages = handle_start_time_period_selection(event)
        reply_msgs = [response]
        if messages:
            reply_msgs.append(messages[0])
        line_bot_service.line_bot_api.reply_message(event.reply_token, reply_msgs)
    except Exception as e:
        logger.error(f"Error handling date choice: {e}")
        error_response = TextSendMessage(text="日付選択でエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_time_choice(event, postback_data: str):
    """時間選択の処理"""
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
        
        # ユーザー管理サービスに時間を保存
        user_management_service.set_temp_data(user_id, "time", postback_data)
        user_management_service.set_temp_data(user_id, "time_text", selected_time)
        
        logger.info(f"Saved time for user {user_id}: {selected_time}")
        
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
                    PostbackAction(
                        label="1名",
                        data="count_1"
                    ),
                    PostbackAction(
                        label="2名",
                        data="count_2"
                    ),
                    PostbackAction(
                        label="3名",
                        data="count_3"
                    ),
                    PostbackAction(
                        label="4名以上",
                        data="count_4_plus"
                    )
                ]
            )
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, [response, count_template])
        
    except Exception as e:
        logger.error(f"Error handling time choice: {e}")
        error_response = TextSendMessage(text="時間選択でエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_count_choice(event, postback_data: str):
    try:
        user_id = event.source.user_id
        count_mapping = {
            "count_1": "1名",
            "count_2": "2名",
            "count_3_plus": "3名以上"
        }
        selected_count = count_mapping.get(postback_data, "不明")
        user_management_service.set_temp_data(user_id, "count", postback_data)
        user_management_service.set_temp_data(user_id, "count_text", selected_count)
        logger.info(f"Saved count for user {user_id}: {selected_count}")
        date = user_management_service.get_temp_data(user_id, "date")
        if date:
            date_str = date.strftime('%Y/%m/%d')
        else:
            date_str = "未選択"
        start_time_data = user_management_service.get_temp_data(user_id, "start_time")
        end_time_data = user_management_service.get_temp_data(user_id, "end_time")
        break_time_data = user_management_service.get_temp_data(user_id, "break_time")
        def time_label(data, prefix):
            if not data or not data.startswith(prefix):
                return "未選択"
            t = data.replace(prefix, "")
            if len(t) == 3:
                return f"{t[0]}:{t[1:]}"
            elif len(t) == 4:
                return f"{t[:2]}:{t[2:]}"
            return t
        start_time_label = time_label(start_time_data, "start_time_")
        end_time_label = time_label(end_time_data, "end_time_")
        break_time_mapping = {
            "break_30": "30分",
            "break_60": "1時間",
            "break_90": "1時間30分",
            "break_120": "2時間"
        }
        break_time_label = break_time_mapping.get(break_time_data, "未選択")
        
                # --- ここから追加: time_slot, required_countの保存 ---
        time_slot = None
        if start_time_data:
            if start_time_data.startswith("start_time_8") or start_time_data.startswith("start_time_9") or start_time_data.startswith("start_time_10") or start_time_data.startswith("start_time_11") or start_time_data.startswith("start_time_12"):
                time_slot = "time_morning"
            elif start_time_data.startswith("start_time_13") or start_time_data.startswith("start_time_14") or start_time_data.startswith("start_time_15") or start_time_data.startswith("start_time_16"):
                time_slot = "time_afternoon"
            elif start_time_data.startswith("start_time_17") or start_time_data.startswith("start_time_18") or start_time_data.startswith("start_time_19") or start_time_data.startswith("start_time_20") or start_time_data.startswith("start_time_21") or start_time_data.startswith("start_time_22"):
                time_slot = "time_evening"
            else:
                time_slot = "time_full_day"
        else:
            time_slot = "time_full_day"
        user_management_service.set_temp_data(user_id, "time_slot", time_slot)

        count_num = 1
        if postback_data == "count_2":
            count_num = 2
        elif postback_data == "count_3_plus":
            count_num = 3
        user_management_service.set_temp_data(user_id, "required_count", count_num)
        # --- ここまで追加 ---

        # テキストで見やすく整形
        response = TextSendMessage(
            text=(
                "【依頼内容の確認】\n\n"
                f"📅 日付: {date_str}\n"
                f"🕒 開始: {start_time_label}\n"
                f"🕓 終了: {end_time_label}\n"
                f"⏸️ 休憩: {break_time_label}\n"
                f"👥 人数: {selected_count}\n\n"
                "この内容で依頼を送信しますか？\n"
                "「はい」または「いいえ」でお答えください。"
            )
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
    except Exception as e:
        logger.error(f"Error handling count choice: {e}")
        error_response = TextSendMessage(text="人数選択でエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_confirmation_yes(event):
    """依頼内容の確定処理"""
    try:
        user_id = event.source.user_id
        print(f"[DEBUG] handle_confirmation_yes: user_id={user_id}")
        print(f"[DEBUG] temp_data: {user_management_service.get_or_create_session(user_id).temp_data}")
        
        # 保存された依頼内容を取得
        date = user_management_service.get_temp_data(user_id, "date")
        time_slot = user_management_service.get_temp_data(user_id, "time_slot")
        required_count = user_management_service.get_temp_data(user_id, "required_count")
        notes = user_management_service.get_temp_data(user_id, "notes")
        
        # 必須項目が揃っているかチェック
        if not (date and time_slot and required_count):
            response = TextSendMessage(text="依頼内容が見つかりません。最初からやり直してください。")
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 依頼IDを生成
        request_id = f"req_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 店舗情報を取得
        store = get_store_by_user_id(user_id)
        if not store:
            response = TextSendMessage(text="店舗情報の取得に失敗しました。")
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 依頼内容を保存
        # start_time_label, end_time_label, break_time_label, count_text を追加
        start_time_data = user_management_service.get_temp_data(user_id, "start_time")
        end_time_data = user_management_service.get_temp_data(user_id, "end_time")
        break_time_data = user_management_service.get_temp_data(user_id, "break_time")
        def time_label(data, prefix):
            if not data or not data.startswith(prefix):
                return "未選択"
            t = data.replace(prefix, "")
            if len(t) == 3:
                return f"{t[0]}:{t[1:]}"
            elif len(t) == 4:
                return f"{t[:2]}:{t[2:]}"
            return t
        start_time_label = time_label(start_time_data, "start_time_")
        end_time_label = time_label(end_time_data, "end_time_")
        break_time_mapping = {
            "break_30": "30分",
            "break_60": "1時間",
            "break_90": "1時間30分",
            "break_120": "2時間"
        }
        break_time_label = break_time_mapping.get(break_time_data, "未選択")
        count_text = f"{required_count}名"
        request_data = {
            "date": date,
            "date_text": date.strftime('%Y/%m/%d'),
            "time_slot": time_slot,
            "required_count": required_count,
            "notes": notes,
            "store": store.store_name,
            "store_user_id": user_id,
            "start_time_label": start_time_label,
            "end_time_label": end_time_label,
            "break_time_label": break_time_label,
            "count_text": count_text
        }
        
        # 依頼内容をrequest_managerに保存
        request_manager.save_request(request_id, request_data)
        logger.info(f"Confirmed request {request_id} for user {user_id}: {request_data}")
        
        # 空き薬剤師検索・通知処理
        available_pharmacists = google_sheets_service.get_available_pharmacists(date, time_slot)
        logger.info(f"Found {len(available_pharmacists)} available pharmacists for {date} {time_slot}")
        
        count_num = int(required_count) if isinstance(required_count, str) else required_count
        selected_pharmacists = available_pharmacists[:count_num]
        
        notify_result = pharmacist_notification_service.notify_pharmacists_of_request(
            selected_pharmacists, request_data, request_id
        )
        logger.info(f"Pharmacist notification result: {notify_result}")
        
        # スプレッドシートに書き込み（開始時刻〜終了時刻 薬局名形式）
        time_slot_mapping = {
            "time_morning": "9:00-13:00",
            "time_afternoon": "13:00-17:00", 
            "time_evening": "17:00-21:00",
            "time_full_day": "9:00-21:00"
        }
        time_range = time_slot_mapping.get(time_slot, time_slot)
        sheet_entry = f"{time_range} {store.store_name}"
        
        # Google Sheetsに記入
        try:
            # スプレッドシートに書き込み（開始時刻〜終了時刻 薬局名形式）
            time_slot_mapping = {
                "time_morning": "9:00-13:00",
                "time_afternoon": "13:00-17:00", 
                "time_evening": "17:00-21:00",
                "time_full_day": "9:00-21:00"
            }
            time_range = time_slot_mapping.get(time_slot, time_slot)
            sheet_entry = f"{time_range} {store.store_name}"
            
            # 簡易的なGoogle Sheets記入（実際の実装では適切なメソッドを使用）
            logger.info(f"Would add shift request to Google Sheets: {sheet_entry}")
        except Exception as e:
            logger.error(f"Error adding to Google Sheets: {e}")
        
        response = TextSendMessage(
            text="✅ 依頼を受け付けました！\n\n薬剤師に通知を送信しました。\n応募があったらご連絡いたします。"
        )
        
        # 一時データをクリア
        user_management_service.clear_temp_data(user_id)
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling confirmation yes: {e}")
        error_response = TextSendMessage(text="確定処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_confirmation_no(event):
    """依頼内容のキャンセル処理"""
    try:
        user_id = event.source.user_id
        
        # 一時データをクリア
        user_management_service.clear_temp_data(user_id)
        logger.info(f"Cleared temp request for user {user_id}")
        
        response = TextSendMessage(
            text="依頼をキャンセルしました。\n"
                 "再度「勤務依頼」と入力して、最初からやり直してください。"
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling confirmation no: {e}")
        error_response = TextSendMessage(text="キャンセル処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_pharmacist_apply(event, postback_data: str):
    """薬剤師の応募処理"""
    print(f"[DEBUG] handle_pharmacist_apply called with postback_data: {postback_data}")
    try:
        user_id = event.source.user_id
        user_type = user_management_service.get_user_type(user_id)
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        print(f"[DEBUG] handle_pharmacist_apply: user_id={user_id}, user_type={user_type}, request_id={request_id}")
        logger.info(f"Pharmacist apply button clicked: user_id={user_id}, request_id={request_id}")
        # 未登録ユーザーの場合は登録促進メッセージを表示
        if user_type == UserType.UNKNOWN:
            print(f"[DEBUG] handle_pharmacist_apply: User type is UNKNOWN, showing registration prompt")
            response = TextSendMessage(
                text="💊 勤務依頼に応募するには、まず薬剤師登録が必要です。\n\n"
                     "以下のいずれかの方法で登録してください：\n\n"
                     "1️⃣ 薬剤師登録（勤務依頼を受信・応募）\n"
                     "→ 「薬剤師登録」と入力\n\n"
                     "2️⃣ 店舗登録（勤務依頼を送信）\n"
                     "→ 「店舗登録」と入力\n\n"
                     "どちらを選択されますか？"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        # 店舗ユーザーの場合は応募不可
        if user_type == UserType.STORE:
            print(f"[DEBUG] handle_pharmacist_apply: User type is STORE, showing error message")
            response = TextSendMessage(
                text="🏪 店舗ユーザーは勤務依頼に応募できません。\n"
                     "勤務依頼の送信のみ可能です。\n\n"
                     "「勤務依頼」と入力して依頼を送信してください。"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        # 薬剤師情報を取得（実際はDBから取得）
        pharmacist_name = "薬剤師A"  # 仮の
        print(f"[DEBUG] handle_pharmacist_apply: Processing application from pharmacist: {pharmacist_name}")
        logger.info(f"Processing application from pharmacist: {pharmacist_name}")
        # 依頼内容を取得
        request_data = request_manager.get_request(request_id)
        # 応募者リストに追加
        request_manager.add_applicant(request_id, user_id)
        
        # 応募処理を実行
        result = pharmacist_notification_service.handle_pharmacist_response(
            user_id, 
            pharmacist_name, 
            "apply", 
            request_id
        )
        print(f"[DEBUG] handle_pharmacist_apply: Result: {result}")
        # --- ここからスプレッドシート記入処理 ---
        if result["success"]:
            logger.info(f"Application processed successfully: {result.get('message')}")
            
            # 依頼内容から実際の値を取得
            if request_data and request_data.get('date'):
                date = request_data.get('date')
                start_time_label = request_data.get('start_time_label', '9:00')
                end_time_label = request_data.get('end_time_label', '18:00')
                store_name = request_data.get('store', 'サンライズ薬局')
            else:
                # フォールバック用のデフォルト値
                from datetime import datetime
                date = datetime.now().date()
                start_time_label = "9:00"
                end_time_label = "18:00"
                store_name = "サンライズ薬局"
            
            # dateがNoneでないことを確認
            if not date:
                from datetime import datetime
                date = datetime.now().date()
            # スプレッドシートに記入
            try:
                sheet_name = google_sheets_service.get_sheet_name(date)
                pharmacists = google_sheets_service._get_pharmacist_list(sheet_name)
                pharmacist_row = None
                for p in pharmacists:
                    if p["user_id"] == user_id:
                        pharmacist_row = p["row_number"]
                        break
                if pharmacist_row:
                    day_column = google_sheets_service._get_day_column(date)
                    range_name = f"{sheet_name}!{chr(65 + day_column)}{pharmacist_row}"
                    cell_value = f"{start_time_label}〜{end_time_label} {store_name}"
                    body = {'values': [[cell_value]]}
                    google_sheets_service.service.spreadsheets().values().update(
                        spreadsheetId=google_sheets_service.spreadsheet_id,
                        range=range_name,
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                    logger.info(f"Wrote schedule to sheet: {range_name} = {cell_value}")
            except Exception as e:
                logger.error(f"Error writing schedule to sheet: {e}")
            # --- 記入処理ここまで ---
            response = TextSendMessage(
                text=f"✅ 応募処理が完了しました！\n"
                     f"依頼ID: {request_id}\n"
                     f"薬剤師: {pharmacist_name}\n"
                     f"結果: {result.get('message', '成功')}"
            )
        else:
            logger.error(f"Failed to handle pharmacist application: {result.get('error')}")
            response = TextSendMessage(
                text=f"❌ 応募処理でエラーが発生しました。\n"
                     f"エラー: {result.get('error', '不明')}"
            )
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
    except Exception as e:
        print(f"[DEBUG] handle_pharmacist_apply: Exception occurred: {e}")
        logger.error(f"Error handling pharmacist apply: {e}")
        error_response = TextSendMessage(text="応募処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_pharmacist_decline(event, postback_data: str):
    """薬剤師の辞退処理"""
    try:
        user_id = event.source.user_id
        user_type = user_management_service.get_user_type(user_id)
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        logger.info(f"Pharmacist decline button clicked: user_id={user_id}, request_id={request_id}")
        
        # 未登録ユーザーの場合は登録促進メッセージを表示
        if user_type == UserType.UNKNOWN:
            response = TextSendMessage(
                text="💊 勤務依頼に辞退を申し出るには、まず薬剤師登録が必要です。\n\n"
                     "以下のいずれかの方法で登録してください：\n\n"
                     "1️⃣ 薬剤師登録（勤務依頼を受信・応募・辞退）\n"
                     "→ 「薬剤師登録」と入力\n\n"
                     "2️⃣ 店舗登録（勤務依頼を送信）\n"
                     "→ 「店舗登録」と入力\n\n"
                     "どちらを選択されますか？"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 店舗ユーザーの場合は辞退不可
        if user_type == UserType.STORE:
            response = TextSendMessage(
                text="🏪 店舗ユーザーは勤務依頼に辞退を申し出ることはできません。\n"
                     "勤務依頼の送信のみ可能です。\n\n"
                     "「勤務依頼」と入力して依頼を送信してください。"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 薬剤師情報を取得（実際はDBから取得）
        # TODO: 実際の実装では、user_idから薬剤師情報をDBから取得
        pharmacist_name = "薬剤師A"  # 仮の名前
        
        logger.info(f"Processing declination from pharmacist: {pharmacist_name}")
        
        # 辞退処理を実行
        result = pharmacist_notification_service.handle_pharmacist_response(
            user_id, 
            pharmacist_name, 
            "decline", 
            request_id
        )
        
        if result["success"]:
            logger.info(f"Declination processed successfully: {result.get('message')}")
            # 辞退確認メッセージは薬剤師通知サービス内で送信済み
            response = TextSendMessage(
                text=f"✅ 辞退処理が完了しました！\n"
                     f"依頼ID: {request_id}\n"
                     f"薬剤師: {pharmacist_name}\n"
                     f"結果: {result.get('message', '成功')}"
            )
        else:
            logger.error(f"Failed to handle pharmacist declination: {result.get('error')}")
            response = TextSendMessage(
                text=f"❌ 辞退処理でエラーが発生しました。\n"
                     f"エラー: {result.get('error', '不明')}"
            )
        
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling pharmacist decline: {e}")
        error_response = TextSendMessage(text="辞退処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_pharmacist_details(event, postback_data: str):
    """薬剤師の詳細確認処理"""
    try:
        user_id = event.source.user_id
        user_type = user_management_service.get_user_type(user_id)
        request_id = postback_data.split(":", 1)[1] if ":" in postback_data else ""
        
        logger.info(f"Pharmacist details button clicked: user_id={user_id}, request_id={request_id}")
        
        # 未登録ユーザーの場合は登録促進メッセージを表示
        if user_type == UserType.UNKNOWN:
            response = TextSendMessage(
                text="💊 勤務依頼の詳細を確認するには、まず薬剤師登録が必要です。\n\n"
                     "以下のいずれかの方法で登録してください：\n\n"
                     "1️⃣ 薬剤師登録（勤務依頼を受信・詳細確認）\n"
                     "→ 「薬剤師登録」と入力\n\n"
                     "2️⃣ 店舗登録（勤務依頼を送信）\n"
                     "→ 「店舗登録」と入力\n\n"
                     "どちらを選択されますか？"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 店舗ユーザーの場合は詳細確認不可
        if user_type == UserType.STORE:
            response = TextSendMessage(
                text="🏪 店舗ユーザーは勤務依頼の詳細を確認することはできません。\n"
                     "勤務依頼の送信のみ可能です。\n\n"
                     "「勤務依頼」と入力して依頼を送信してください。"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
        
        # 薬剤師情報を取得（実際はDBから取得）
        # TODO: 実際の実装では、user_idから薬剤師情報をDBから取得
        pharmacist_name = "薬剤師A"  # 仮の名前
        
        logger.info(f"Processing details request from pharmacist: {pharmacist_name}")
        
        # 詳細確認処理を実行
        result = pharmacist_notification_service.handle_pharmacist_response(
            user_id, 
            pharmacist_name, 
            "details", 
            request_id
        )
        
        if result["success"]:
            logger.info(f"Details request processed successfully: {result.get('message')}")
            # 詳細確認メッセージは薬剤師通知サービス内で送信済み
            response = TextSendMessage(
                text=f"✅ 詳細確認処理が完了しました！\n"
                     f"依頼ID: {request_id}\n"
                     f"薬剤師: {pharmacist_name}\n"
                     f"結果: {result.get('message', '成功')}"
            )
        else:
            logger.error(f"Failed to handle pharmacist details request: {result.get('error')}")
            response = TextSendMessage(
                text=f"❌ 詳細確認処理でエラーが発生しました。\n"
                     f"エラー: {result.get('error', '不明')}"
            )
        
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
    except Exception as e:
        logger.error(f"Error handling pharmacist details: {e}")
        error_response = TextSendMessage(text="詳細確認処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_debug_commands(event, message_text: str):
    """デバッグ用コマンドの処理"""
    user_id = event.source.user_id
    logger.info(f"Debug command from {user_id}: {message_text}")
    
    if message_text == "デバッグ":
        response = TextSendMessage(
            text="🔧 デバッグモード\n\n"
                 "利用可能なデバッグコマンド:\n"
                 "• デバッグ - このメッセージを表示\n"
                 "• デバッグ依頼 - 保存された依頼内容を表示\n"
                 "• デバッグクリア - 保存された依頼内容をクリア"
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        return
    
    elif message_text == "デバッグ依頼":
        # 保存された依頼内容を表示
        all_requests = request_manager.get_all_requests()
        if all_requests:
            response_text = "📋 保存された依頼内容:\n\n"
            for req_id, req_data in all_requests.items():
                response_text += f"依頼ID: {req_id}\n"
                response_text += f"店舗: {req_data.get('store', '不明')}\n"
                response_text += f"日付: {req_data.get('date_text', '不明')}\n"
                response_text += f"時間: {req_data.get('start_time_label', '不明')}〜{req_data.get('end_time_label', '不明')}\n"
                response_text += f"ステータス: {req_data.get('status', '不明')}\n"
                response_text += "━━━━━━━━━━━━━━━━━━━━\n"
        else:
            response_text = "📋 保存された依頼はありません"
        
        response = TextSendMessage(text=response_text)
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        return
    
    elif message_text == "デバッグクリア":
        # 保存された依頼内容をクリア
        all_requests = request_manager.get_all_requests()
        for req_id in all_requests.keys():
            request_manager.delete_request(req_id)
        
        response = TextSendMessage(text="🗑️ 保存された依頼内容をクリアしました")
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        return


def handle_test_commands(event, message_text: str):
    """テスト用コマンドの処理"""
    try:
        user_id = event.source.user_id
        
        if message_text == "テスト応募":
            # テスト用の応募処理をシミュレート
            test_request_id = "test_req_001"
            test_pharmacist_name = "テスト薬剤師"
            
            result = pharmacist_notification_service.handle_pharmacist_response(
                user_id, 
                test_pharmacist_name, 
                "apply", 
                test_request_id
            )
            
            if result["success"]:
                response = TextSendMessage(
                    text=f"✅ テスト応募処理が完了しました！\n"
                         f"依頼ID: {test_request_id}\n"
                         f"薬剤師: {test_pharmacist_name}\n"
                         f"結果: {result.get('message', '成功')}"
                )
            else:
                response = TextSendMessage(
                    text=f"❌ テスト応募処理でエラーが発生しました。\n"
                         f"エラー: {result.get('error', '不明')}"
                )
            
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
            
        elif message_text == "テスト辞退":
            # テスト用の辞退処理をシミュレート
            test_request_id = "test_req_002"
            test_pharmacist_name = "テスト薬剤師"
            
            result = pharmacist_notification_service.handle_pharmacist_response(
                user_id, 
                test_pharmacist_name, 
                "decline", 
                test_request_id
            )
            
            if result["success"]:
                response = TextSendMessage(
                    text=f"✅ テスト辞退処理が完了しました！\n"
                         f"依頼ID: {test_request_id}\n"
                         f"薬剤師: {test_pharmacist_name}\n"
                         f"結果: {result.get('message', '成功')}"
                )
            else:
                response = TextSendMessage(
                    text=f"❌ テスト辞退処理でエラーが発生しました。\n"
                         f"エラー: {result.get('error', '不明')}"
                )
            
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
            
        elif message_text == "テスト詳細":
            # テスト用の詳細確認処理をシミュレート
            test_request_id = "test_req_003"
            test_pharmacist_name = "テスト薬剤師"
            
            result = pharmacist_notification_service.handle_pharmacist_response(
                user_id, 
                test_pharmacist_name, 
                "details", 
                test_request_id
            )
            
            if result["success"]:
                response = TextSendMessage(
                    text=f"✅ テスト詳細確認処理が完了しました！\n"
                         f"依頼ID: {test_request_id}\n"
                         f"薬剤師: {test_pharmacist_name}\n"
                         f"結果: {result.get('message', '成功')}"
                )
            else:
                response = TextSendMessage(
                    text=f"❌ テスト詳細確認処理でエラーが発生しました。\n"
                         f"エラー: {result.get('error', '不明')}"
                )
            
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
            
        elif message_text == "テストヘルプ":
            # テストコマンドのヘルプを表示
            response = TextSendMessage(
                text="🧪 テストコマンド一覧\n"
                     "━━━━━━━━━━━━━━━━━━━━\n"
                     "「テスト応募」: 応募処理のテスト\n"
                     "「テスト辞退」: 辞退処理のテスト\n"
                     "「テスト詳細」: 詳細確認処理のテスト\n"
                     "「テストヘルプ」: このヘルプを表示\n"
                     "━━━━━━━━━━━━━━━━━━━━\n"
                     "実際のボタンクリックもテストできます。"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
            
        else:
            # 不明なテストコマンド
            response = TextSendMessage(
                text="❓ 不明なテストコマンドです。\n"
                     "「テストヘルプ」で利用可能なコマンドを確認してください。"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
            return
            
    except Exception as e:
        logger.error(f"Error handling test command: {e}")
        error_response = TextSendMessage(text="テストコマンドの処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)


def handle_pharmacist_registration(event, message_text: str):
    """薬剤師登録処理"""
    try:
        user_id = event.source.user_id
        
        # メッセージを解析
        parts = message_text.split()
        if len(parts) < 4:
            # 登録フォーマットが不完全な場合
            help_message = TextSendMessage(
                text="📝 登録フォーマットが正しくありません。\n\n"
                     f"正しいフォーマット：\n"
                     f"登録 [名前] [電話番号] [対応可能時間]\n\n"
                     f"例：登録 田中太郎 090-1234-5678 午前,午後\n\n"
                     f"対応可能時間の選択肢：\n"
                     f"• 午前 (9:00-13:00)\n"
                     f"• 午後 (13:00-17:00)\n"
                     f"• 夜間 (17:00-21:00)\n"
                     f"• 終日"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, help_message)
            return
        
        # 情報を抽出
        name = parts[1]
        phone = parts[2]
        availability = parts[3].split(",")
        
        # ユーザープロフィールを取得
        profile = line_bot_service.line_bot_api.get_profile(user_id)
        
        # 薬剤師情報をGoogle Sheetsに登録
        pharmacist_data = {
            "id": f"pharm_{user_id[-8:]}",  # ユーザーIDの後8文字を使用
            "user_id": user_id,
            "name": name,
            "phone": phone,
            "availability": availability,
            "rating": 0.0,
            "experience_years": 0,
            "registered_at": datetime.now().isoformat()
        }
        
        # Google Sheetsに登録
        success = google_sheets_service.register_pharmacist(pharmacist_data)
        
        if success:
            user_management_service.set_user_type(user_id, UserType.PHARMACIST)
            confirmation_message = TextSendMessage(
                text=f"✅ 薬剤師登録が完了しました！\n\n"
                     f"📋 登録情報：\n"
                     f"• 名前: {name}\n"
                     f"• 電話番号: {phone}\n"
                     f"• 対応可能時間: {', '.join(availability)}\n\n"
                     f"これで勤務依頼の通知を受け取ることができます。\n"
                     f"「勤務依頼」と入力してテストしてみてください。"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, confirmation_message)
            # 追加: 登録済みユーザー案内をpush_messageで送信
            line_bot_service.line_bot_api.push_message(user_id, TextSendMessage(text="シフト依頼があったら、今後はBotから通知が届きます！"))
        else:
            confirmation_message = TextSendMessage(
                text="❌ 登録処理中にエラーが発生しました。\n"
                     "しばらく時間をおいて再度お試しください。"
            )
        
        line_bot_service.line_bot_api.reply_message(event.reply_token, confirmation_message)
        
        logger.info(f"Pharmacist registration completed for {name} ({user_id})")
        
    except Exception as e:
        logger.error(f"Error in pharmacist registration: {e}")
        error_message = TextSendMessage(
            text="申し訳ございません。登録処理中にエラーが発生しました。\n"
                 "正しいフォーマットで再度お試しください。"
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)


def handle_other_messages(event, message_text: str):
    """その他のメッセージ処理"""
    try:
        user_id = event.source.user_id
        session = user_management_service.get_or_create_session(user_id)
        user_type = session.user_type
        if user_type == UserType.UNKNOWN:
            response = TextSendMessage(text=WELCOME_GUIDE)
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        else:
            response = TextSendMessage(text="ご質問内容が認識できませんでした。必要な操作を選択してください。")
            line_bot_service.line_bot_api.reply_message(event.reply_token, response)
    except Exception as e:
        logger.error(f"Error handling other messages: {e}")
        error_message = TextSendMessage(text="申し訳ございません。エラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)


def handle_store_registration(event):
    """店舗登録処理"""
    try:
        user_id = event.source.user_id
        # ユーザータイプを店舗に設定
        user_management_service.set_user_type(user_id, UserType.STORE)
        # 店舗情報を設定
        store_name = "メイプル薬局"
        store_number = "001"
        user_management_service.set_user_info(user_id, {
            "store_name": store_name,
            "store_number": store_number,
            "registered_at": datetime.now().isoformat()
        })
        response = TextSendMessage(
            text=f"✅ 店舗登録が完了しました！\n\n"
                 f"🏪 店舗名: {store_name}\n"
                 f"📋 店舗番号: {store_number}"
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        logger.info(f"Store registration completed for user {user_id}")
    except Exception as e:
        logger.error(f"Error in store registration: {e}")
        error_message = TextSendMessage(
            text="申し訳ございません。店舗登録中にエラーが発生しました。"
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)


def handle_pharmacist_registration_prompt(event):
    """薬剤師登録プロンプト"""
    try:
        user_id = event.source.user_id
        
        # ユーザータイプを薬剤師に設定
        user_management_service.set_user_type(user_id, UserType.PHARMACIST)
        
        response = TextSendMessage(
            text="💊 薬剤師登録を開始します。\n\n"
                 "以下の情報を教えてください：\n\n"
                 "📝 登録フォーマット：\n"
                 "登録 [名前] [電話番号] [対応可能時間]\n\n"
                 "例：登録 田中太郎 090-1234-5678 午前,午後\n\n"
                 "対応可能時間の選択肢：\n"
                 "• 午前 (9:00-13:00)\n"
                 "• 午後 (13:00-17:00)\n"
                 "• 夜間 (17:00-21:00)\n"
                 "• 終日\n\n"
                 "登録が完了すると、勤務依頼の通知を受け取ることができます。"
        )
        
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
        
        logger.info(f"Pharmacist registration prompt sent to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in pharmacist registration prompt: {e}")
        error_message = TextSendMessage(
            text="申し訳ございません。エラーが発生しました。"
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)


def handle_store_registration_detailed(event, message_text: str):
    """店舗登録詳細処理（番号・店舗名でのuserId自動登録）"""
    try:
        import re
        user_id = event.source.user_id
        print(f"[DEBUG] handle_store_registration_detailed: user_id={user_id}, message_text='{message_text}'")
        # 柔軟な区切り文字対応
        text = message_text.replace("店舗登録", "").strip()
        parts = list(filter(None, re.split(r'[ ,、\u3000]+', text)))
        if len(parts) >= 2:
            store_number = parts[0]
            store_name = parts[1]
            logger.info(f"Attempting to register store: number={store_number}, name={store_name}, user_id={user_id}")
            # Google Sheetsに店舗userIdを登録（必ず「店舗登録」シートを参照）
            success = google_sheets_service.register_store_user_id(
                number=store_number,
                name=store_name,
                user_id=user_id,
                sheet_name="店舗登録"
            )
            if success:
                # ユーザータイプを店舗に設定
                user_management_service.set_user_type(user_id, UserType.STORE)
                # 店舗情報を設定
                user_management_service.set_user_info(user_id, {
                    "store_name": store_name,
                    "store_number": store_number,
                    "registered_at": datetime.now().isoformat()
                })
                # 登録完了メッセージ（push_messageでエラー回避）
                response = TextSendMessage(
                    text=f"✅ 店舗登録が完了しました！\n\n"
                         f"🏪 店舗名: {store_name}\n"
                         f"📋 店舗番号: {store_number}"
                )
                # push_messageを使用してエラー回避
                line_bot_service.line_bot_api.push_message(user_id, response)
                # 自動でシフト依頼フロー開始
                handle_shift_request(event, "", use_push=True)
                logger.info(f"Store registration completed for {store_name} ({user_id})")
            else:
                error_message = TextSendMessage(
                    text=f"❌ 店舗登録に失敗しました。\n\n"
                         f"店舗番号「{store_number}」と店舗名「{store_name}」の組み合わせが\n"
                         f"正しいかご確認ください。"
                )
                line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)
        else:
            error_message = TextSendMessage(
                text="❌ 店舗登録フォーマットが正しくありません。\n\n"
                     "正しいフォーマット：\n"
                     "店舗登録 [店舗番号] [店舗名]\n\n"
                     "例：店舗登録 002 サンライズ薬局"
            )
            line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)
    except Exception as e:
        logger.error(f"Error in store registration detailed: {e}")
        error_message = TextSendMessage(
            text="申し訳ございません。店舗登録中にエラーが発生しました。"
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_message)


def handle_start_time_period_selection(event):
    template = ButtonsTemplate(
        title="勤務開始時間帯を選択",
        text="どの時間帯を希望されますか？",
        actions=[
            PostbackAction(label="午前（8:00〜13:00）", data="start_time_morning"),
            PostbackAction(label="午後（13:00〜19:00）", data="start_time_afternoon")
        ]
    )
    message = TemplateSendMessage(
        alt_text="勤務開始時間帯を選択してください",
        template=template
    )
    return [message]

def handle_start_time_detail_selection(event, period):
    if period == "morning":
        # 8:00〜13:00（30分刻み）
        time_labels = [
            "8:00", "8:30", "9:00", "9:30", "10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "13:00"
        ]
    else:
        # 13:00〜19:00（30分刻み）
        time_labels = [
            "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00"
        ]
    quick_reply_items = [
        QuickReplyButton(action=PostbackAction(label=label, data=f"start_time_{label.replace(':','')}") )
        for label in time_labels
    ]
    messages = []
    for i in range(0, len(quick_reply_items), 13):
        items = quick_reply_items[i:i+13]
        msg = TextSendMessage(
            text="勤務開始時間を選択してください",
            quick_reply=QuickReply(items=items)
        )
        messages.append(msg)
    return messages

def handle_end_time_selection(event):
    """勤務終了時間帯の選択肢をボタンテンプレートで表示する"""
    user_id = event.source.user_id
    start_time_data = user_management_service.get_temp_data(user_id, "start_time")
    if not start_time_data:
        return [TextSendMessage(text="開始時間が未設定です。最初からやり直してください。")]
    # 例: start_time_830 → 8:30
    start_time_str = start_time_data.replace("start_time_", "")
    if len(start_time_str) == 3:
        start_hour = int(start_time_str[0])
        start_minute = int(start_time_str[1:])
    else:
        start_hour = int(start_time_str[:2])
        start_minute = int(start_time_str[2:])
    # ボタンテンプレートで帯を選択
    template = ButtonsTemplate(
        title="勤務終了時間帯を選択",
        text="勤務終了時間帯をお選びください",
        actions=[
            PostbackAction(label="日中（10:00〜16:00）", data="end_band_day"),
            PostbackAction(label="夕方（16:00〜19:00）", data="end_band_evening"),
            PostbackAction(label="夜（19:00〜22:00）", data="end_band_night")
        ]
    )
    msg = TemplateSendMessage(
        alt_text="勤務終了時間帯を選択",
        template=template
    )
    return [msg]

def handle_end_time_band_detail_selection(event, band_data):
    """選択された帯に応じて勤務終了時間リストを出す"""
    user_id = event.source.user_id
    start_time_data = user_management_service.get_temp_data(user_id, "start_time")
    if not start_time_data:
        return [TextSendMessage(text="開始時間が未設定です。最初からやり直してください。")]
    start_time_str = start_time_data.replace("start_time_", "")
    if len(start_time_str) == 3:
        start_hour = int(start_time_str[0])
        start_minute = int(start_time_str[1:])
    else:
        start_hour = int(start_time_str[:2])
        start_minute = int(start_time_str[2:])
    # 各帯の時間リスト
    if band_data == "end_band_day":
        end_times = [(10,0),(10,30),(11,0),(11,30),(12,0),(12,30),(13,0),(13,30),(14,0),(14,30),(15,0),(15,30),(16,0)]
    elif band_data == "end_band_evening":
        end_times = [(16,0),(16,30),(17,0),(17,30),(18,0),(18,30),(19,0)]
    else:
        end_times = [(19,0),(19,30),(20,0),(20,30),(21,0),(21,30),(22,0)]
    # 開始時間より後の時刻のみを選択肢に
    selectable = [(h,m) for (h,m) in end_times if (h > start_hour or (h == start_hour and m > start_minute))]
    if not selectable:
        return [TextSendMessage(text="終了時間は開始時間より後を選択してください。別の帯を選んでください。")]
    quick_reply_items = [
        QuickReplyButton(action=PostbackAction(label=f"{h}:{str(m).zfill(2)}", data=f"end_time_{h}{str(m).zfill(2)}"))
        for (h,m) in selectable
    ]
    messages = []
    for i in range(0, len(quick_reply_items), 13):
        items = quick_reply_items[i:i+13]
        msg = TextSendMessage(
            text="勤務終了時間を選択してください",
            quick_reply=QuickReply(items=items)
        )
        messages.append(msg)
    return messages

def handle_break_time_selection(event):
    """休憩時間の選択肢をボタンテンプレートで表示する（4つまで）"""
    template = ButtonsTemplate(
        title="休憩時間を選択",
        text="休憩時間をお選びください",
        actions=[
            PostbackAction(label="30分", data="break_30"),
            PostbackAction(label="1時間", data="break_60"),
            PostbackAction(label="1時間30分", data="break_90"),
            PostbackAction(label="2時間", data="break_120")
        ]
    )
    msg = TemplateSendMessage(
        alt_text="休憩時間を選択",
        template=template
    )
    return [msg]

def handle_pharmacist_confirm_accept(event, postback_data):
    """店舗が応募を承諾した場合の処理"""
    try:
        _, request_id, pharmacist_user_id = postback_data.split(":", 2)
        # 依頼内容取得
        request_data = request_manager.get_request(request_id)
        if not request_data:
            line_bot_service.line_bot_api.reply_message(event.reply_token, TextSendMessage(text="依頼内容が見つかりませんでした。"))
            return
        # デバッグ: user_idとpharmacist_user_idの一致を出力
        logger.info(f"[CONFIRM] pharmacist_user_id={pharmacist_user_id}, request_data={request_data}")
        # スプレッドシート記入（必ず上書き）
        try:
            date = request_data.get('date')
            if not date:
                logger.error("dateがNoneのためスプレッドシート記入をスキップ")
            else:
                start_time_label = request_data.get('start_time_label', '9:00')
                end_time_label = request_data.get('end_time_label', '18:00')
                store_name = request_data.get('store', 'サンライズ薬局')
                sheet_name = google_sheets_service.get_sheet_name(date)
                pharmacists = google_sheets_service._get_pharmacist_list(sheet_name)
                pharmacist_row = None
                for p in pharmacists:
                    logger.info(f"[CONFIRM] pharmacist_row_check: p['user_id']={p['user_id']} vs pharmacist_user_id={pharmacist_user_id}")
                    if p["user_id"] == pharmacist_user_id:
                        pharmacist_row = p["row_number"]
                        break
                if pharmacist_row:
                    day_column = google_sheets_service._get_day_column(date)
                    range_name = f"{sheet_name}!{chr(65 + day_column)}{pharmacist_row}"
                    cell_value = f"{start_time_label}〜{end_time_label} {store_name}"
                    body = {'values': [[cell_value]]}
                    if google_sheets_service.service:
                        google_sheets_service.service.spreadsheets().values().update(
                            spreadsheetId=google_sheets_service.spreadsheet_id,
                            range=range_name,
                            valueInputOption='RAW',
                            body=body
                        ).execute()
                        logger.info(f"[CONFIRM] Overwrote schedule to sheet: {range_name} = {cell_value}")
                    else:
                        logger.error("google_sheets_service.serviceがNoneのため記入スキップ")
                else:
                    logger.error(f"[CONFIRM] pharmacist_row not found for user_id={pharmacist_user_id}")
        except Exception as e:
            logger.error(f"Error writing schedule to sheet (確定): {e}")
        # 薬剤師に確定連絡
        from pharmacist_bot.services.line_bot_service import pharmacist_line_bot_service
        date = request_data.get('date')
        if date and hasattr(date, 'strftime'):
            date_str = date.strftime('%Y/%m/%d')
        else:
            date_str = str(date)
        msg = f"✅ 勤務確定のお知らせ\n\n"
        msg += f"日付: {date_str}\n"
        msg += f"時間: {request_data.get('start_time_label','')}〜{request_data.get('end_time_label','')}\n"
        msg += f"店舗: {request_data.get('store','')}\n"
        pharmacist_line_bot_service.send_message(pharmacist_user_id, TextSendMessage(text=msg))
        # 店舗にも完了通知
        line_bot_service.line_bot_api.reply_message(event.reply_token, TextSendMessage(text="確定処理が完了しました。"))
        # 確定者リストに追加
        request_manager.add_confirmed(request_id, pharmacist_user_id)
        # 必要人数分確定したら未確定応募者に見送り通知
        confirmed = request_manager.get_confirmed(request_id)
        applicants = request_manager.get_applicants(request_id)
        count = request_data.get('count', 'count_1')
        count_num = 1
        if count == 'count_2':
            count_num = 2
        elif count == 'count_3_plus':
            count_num = 3
        if len(confirmed) >= count_num:
            from pharmacist_bot.services.line_bot_service import pharmacist_line_bot_service
            for applicant_id in applicants:
                if applicant_id not in confirmed:
                    msg = "今回は他の方で確定しました。またのご応募をお待ちしております。"
                    pharmacist_line_bot_service.send_message(applicant_id, TextSendMessage(text=msg))
    except Exception as e:
        logger.error(f"Error in handle_pharmacist_confirm_accept: {e}")
        line_bot_service.line_bot_api.reply_message(event.reply_token, TextSendMessage(text="確定処理中にエラーが発生しました。"))

def handle_pharmacist_confirm_reject(event, postback_data):
    """店舗が応募を拒否した場合の処理"""
    try:
        _, request_id, pharmacist_user_id = postback_data.split(":", 2)
        # 薬剤師に見送り連絡
        from pharmacist_bot.services.line_bot_service import pharmacist_line_bot_service
        msg = "申し訳ありませんが、今回は見送りとなりました。\nまたのご応募をお待ちしております。"
        pharmacist_line_bot_service.send_message(pharmacist_user_id, TextSendMessage(text=msg))
        # 店舗にも完了通知
        line_bot_service.line_bot_api.reply_message(event.reply_token, TextSendMessage(text="見送り連絡を送信しました。"))
    except Exception as e:
        logger.error(f"Error in handle_pharmacist_confirm_reject: {e}")
        line_bot_service.line_bot_api.reply_message(event.reply_token, TextSendMessage(text="見送り処理中にエラーが発生しました。"))

@router.post("/webhook")
async def debug_webhook(request: Request):
    body = await request.body()
    print("DEBUG: LINEから受信:", body)
    return JSONResponse(content={"status": "ok"}, status_code=200)

def handle_parsed_shift_request(event, parsed_data, store):
    """解析済みシフト依頼の処理"""
    user_id = event.source.user_id
    print(f"[DEBUG] handle_parsed_shift_request: user_id={user_id}, parsed_data={parsed_data}")
    try:
        # 依頼内容を一時保存
        user_management_service.set_temp_data(user_id, "date", parsed_data["date"])
        user_management_service.set_temp_data(user_id, "time_slot", parsed_data["time_slot"])
        user_management_service.set_temp_data(user_id, "required_count", parsed_data["required_count"])
        user_management_service.set_temp_data(user_id, "notes", parsed_data.get("notes", ""))
        
        # 依頼内容確認メッセージを見やすく整形
        response = TextSendMessage(
            text=(
                "【依頼内容の確認】\n\n"
                f"📅 日付: {parsed_data['date'].strftime('%Y/%m/%d')}\n"
                f"🕒 開始: {parsed_data.get('start_time_label', '未指定')}\n"
                f"🕓 終了: {parsed_data.get('end_time_label', '未指定')}\n"
                f"⏸️ 休憩: {parsed_data.get('break_time_label', '未指定')}\n"
                f"👥 人数: {parsed_data['required_count']}名\n"
                f"📝 備考: {parsed_data.get('notes', 'なし')}\n\n"
                "この内容で依頼を送信しますか？\n"
                "「はい」または「いいえ」でお答えください。"
            )
        )
        line_bot_service.line_bot_api.reply_message(event.reply_token, response)
    except Exception as e:
        logger.error(f"Error in handle_parsed_shift_request: {e}")
        error_response = TextSendMessage(text="依頼内容の処理中にエラーが発生しました。")
        line_bot_service.line_bot_api.reply_message(event.reply_token, error_response)