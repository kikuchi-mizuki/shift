import logging
from typing import List, Optional, Dict
from datetime import datetime, date
import uuid

from app.models.schedule import ShiftRequest, PharmacistResponse, Schedule, TimeSlot, ResponseStatus
from app.models.user import Store, Pharmacist
from app.services.google_sheets_service import GoogleSheetsService
from app.services.line_bot_service import LineBotService

logger = logging.getLogger(__name__)


class ScheduleService:
    def __init__(self):
        self.google_sheets_service = GoogleSheetsService()
        self.line_bot_service = LineBotService()
        
        # メモリ内でリクエストとレスポンスを管理（実際はデータベースを使用）
        self.shift_requests: Dict[str, ShiftRequest] = {}
        self.pharmacist_responses: Dict[str, List[PharmacistResponse]] = {}
        self.schedules: Dict[str, Schedule] = {}

    def create_shift_request(
        self, 
        store: Store, 
        target_date: date, 
        time_slot: TimeSlot, 
        required_count: int, 
        notes: Optional[str] = None
    ) -> ShiftRequest:
        """シフト依頼を作成"""
        request_id = str(uuid.uuid4())
        
        shift_request = ShiftRequest(
            id=request_id,
            store_id=store.id,
            date=target_date,
            time_slot=time_slot,
            required_count=required_count,
            notes=notes,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.shift_requests[request_id] = shift_request
        self.pharmacist_responses[request_id] = []
        
        logger.info(f"Shift request created: {request_id}")
        return shift_request

    def process_shift_request(self, shift_request: ShiftRequest, store: Store) -> bool:
        """シフト依頼を処理（空き薬剤師の抽出と通知）"""
        try:
            logger.info(f"[process_shift_request] called for shift_request.id={shift_request.id}, store={store}")
            # 空き薬剤師を取得
            available_pharmacists = self.google_sheets_service.get_available_pharmacists(
                shift_request.date, 
                shift_request.time_slot
            )
            logger.info(f"[process_shift_request] available_pharmacists count: {len(available_pharmacists) if available_pharmacists else 0}")
            if not available_pharmacists:
                logger.warning(f"No available pharmacists for {shift_request.date} {shift_request.time_slot}")
                return False
            # 必要人数分の薬剤師に依頼を送信
            pharmacists_to_contact_dicts = available_pharmacists[:shift_request.required_count * 2]  # 余裕を持って2倍
            logger.info(f"[process_shift_request] pharmacists_to_contact count: {len(pharmacists_to_contact_dicts)}")
            # DictからPharmacistインスタンスへ変換
            pharmacists_to_contact = [
                Pharmacist(
                    id=p.get("id", ""),
                    user_id=p.get("user_id", ""),
                    name=p.get("name", ""),
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                ) for p in pharmacists_to_contact_dicts
            ]
            # LINE Botで薬剤師に通知
            success = self.line_bot_service.send_shift_request_to_pharmacists(
                pharmacists_to_contact,
                shift_request,
                store
            )
            logger.info(f"[process_shift_request] send_shift_request_to_pharmacists result: {success}")
            if success:
                shift_request.status = "processing"
                self.shift_requests[shift_request.id] = shift_request
                logger.info(f"Shift request processing started: {shift_request.id}")
            return success
        except Exception as e:
            logger.error(f"Error processing shift request: {e}")
            return False

    def handle_pharmacist_response(
        self, 
        pharmacist: Pharmacist, 
        shift_request_id: str, 
        response: ResponseStatus, 
        conditions: Optional[str] = None
    ) -> bool:
        """薬剤師の応答を処理"""
        try:
            if shift_request_id not in self.shift_requests:
                logger.error(f"Shift request not found: {shift_request_id}")
                return False
            
            shift_request = self.shift_requests[shift_request_id]
            
            # 応答を記録
            pharmacist_response = PharmacistResponse(
                id=str(uuid.uuid4()),
                shift_request_id=shift_request_id,
                pharmacist_id=pharmacist.id,
                response=response,
                conditions=conditions,
                response_time=datetime.now(),
                created_at=datetime.now()
            )
            
            self.pharmacist_responses[shift_request_id].append(pharmacist_response)
            
            # 最初の「はい」の応答を確定
            if response == ResponseStatus.ACCEPTED:
                return self._confirm_shift(shift_request, pharmacist, conditions)
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling pharmacist response: {e}")
            return False

    def _confirm_shift(self, shift_request: ShiftRequest, pharmacist: Pharmacist, conditions: Optional[str] = None) -> bool:
        """シフトを確定"""
        try:
            # スケジュールを作成
            schedule = Schedule(
                id=str(uuid.uuid4()),
                shift_request_id=shift_request.id,
                pharmacist_id=pharmacist.id,
                store_id=shift_request.store_id,
                date=shift_request.date,
                time_slot=shift_request.time_slot,
                notes=conditions,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            # 追加: 開始・終了時刻ラベルをshift_requestから引き継ぐ
            if hasattr(shift_request, 'start_time_label'):
                schedule.start_time_label = shift_request.start_time_label
            if hasattr(shift_request, 'end_time_label'):
                schedule.end_time_label = shift_request.end_time_label
            self.schedules[schedule.id] = schedule
            
            # Google Sheetsに応募確定を記録
            store = self._get_store(shift_request.store_id)  # 実際はデータベースから取得
            if store:
                # 1. スケジュール確定をGoogle Sheetsに反映
                success = self.google_sheets_service.update_schedule(schedule, store)
                if not success:
                    logger.error(f"Failed to update Google Sheets for schedule: {schedule.id}")
                    return False
                # 2. 応募確定記録（必要に応じてrecord_applicationも呼ぶ）
                try:
                    self.google_sheets_service.record_application(
                        request_id=shift_request.id,
                        pharmacist_id=pharmacist.id,
                        pharmacist_name=pharmacist.name,
                        store_name=store.store_name,
                        date=shift_request.date,
                        time_slot=shift_request.time_slot.value if hasattr(shift_request.time_slot, 'value') else str(shift_request.time_slot)
                    )
                except Exception as e:
                    logger.error(f"Failed to record application in Google Sheets: {e}")
                # 3. 店舗に確定通知
            confirmed_pharmacists = [pharmacist]
            self.line_bot_service.send_confirmation_to_store(store, shift_request, confirmed_pharmacists)
            else:
                logger.error(f"Store not found for store_id: {shift_request.store_id}. Skipping confirmation notification.")
            # 4. 他の応募者に辞退通知
            self._notify_other_applicants(shift_request, pharmacist)
            # 5. リクエストステータスを完了に更新
            shift_request.status = "completed"
            self.shift_requests[shift_request.id] = shift_request
            logger.info(f"Shift confirmed: {schedule.id}")
            return True
        except Exception as e:
            logger.error(f"Error confirming shift: {e}")
            return False

    def _notify_other_applicants(self, shift_request: ShiftRequest, confirmed_pharmacist: Pharmacist):
        """他の応募者に辞退通知を送信"""
        try:
            responses = self.pharmacist_responses.get(shift_request.id, [])
            store = self._get_store(shift_request.store_id)  # 実際はデータベースから取得
            if not store:
                logger.error(f"Store not found for store_id: {shift_request.store_id}. Skipping decline notifications.")
                return
            for response in responses:
                if (response.pharmacist_id != confirmed_pharmacist.id and 
                    response.response == ResponseStatus.ACCEPTED):
                    pharmacist = self._get_pharmacist(response.pharmacist_id)  # 実際はデータベースから取得
                    if pharmacist:
                        self.line_bot_service.send_decline_notification(pharmacist, shift_request, store)
        except Exception as e:
            logger.error(f"Error notifying other applicants: {e}")

    def get_shift_request_status(self, shift_request_id: str) -> Optional[str]:
        """シフト依頼のステータスを取得"""
        if shift_request_id in self.shift_requests:
            return self.shift_requests[shift_request_id].status
        return None

    def get_pharmacist_responses(self, shift_request_id: str) -> List[PharmacistResponse]:
        """薬剤師の応答一覧を取得"""
        return self.pharmacist_responses.get(shift_request_id, [])

    def _get_store(self, store_id: str) -> Optional[Store]:
        """店舗情報を取得（実際はデータベースから取得）"""
        # 簡易実装
        return Store(
            id=store_id,
            user_id="user_1",
            store_number="001",
            store_name="メイプル薬局",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    def _get_pharmacist(self, pharmacist_id: str) -> Optional[Pharmacist]:
        """薬剤師情報を取得（実際はデータベースから取得）"""
        # 簡易実装
        return Pharmacist(
            id=pharmacist_id,
            user_id="user_2",
            name="薬剤師A",
            created_at=datetime.now(),
            updated_at=datetime.now()
        ) 