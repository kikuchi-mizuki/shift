import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from shared.services.google_sheets_service import GoogleSheetsService
from shared.models.schedule import Schedule, TimeSlot, ShiftRequest
from shared.models.user import Store

logger = logging.getLogger(__name__)


class StoreScheduleService:
    def __init__(self):
        self.google_sheets_service = GoogleSheetsService()
        logger.info("Store schedule service initialized")

    def create_shift_request(self, store: Store, target_date: date, time_slot: str, 
                           required_count: int, notes: str = None) -> ShiftRequest:
        """シフト依頼を作成"""
        request_id = f"store_req_{store.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        shift_request = ShiftRequest(
            id=request_id,
            store_id=store.id,
            store_name=store.store_name,
            target_date=target_date,
            time_slot=time_slot,
            required_count=required_count,
            notes=notes,
            status="pending",
            created_at=datetime.now()
        )
        
        logger.info(f"Created shift request: {request_id} for store {store.store_name}")
        return shift_request

    def process_shift_request(self, shift_request: ShiftRequest, store: Store) -> bool:
        """シフト依頼を処理"""
        try:
            # 空き薬剤師を検索
            available_pharmacists = self.google_sheets_service.get_available_pharmacists(
                shift_request.target_date, 
                shift_request.time_slot
            )
            
            if not available_pharmacists:
                logger.warning(f"No available pharmacists found for request {shift_request.id}")
                return False
            
            # 薬剤師Botに通知を送信（実際の実装では、薬剤師BotのAPIを呼び出す）
            notification_sent = self._notify_pharmacist_bot(shift_request, available_pharmacists)
            
            if notification_sent:
                logger.info(f"Shift request {shift_request.id} processed successfully")
                return True
            else:
                logger.error(f"Failed to process shift request {shift_request.id}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing shift request: {e}")
            return False

    def _notify_pharmacist_bot(self, shift_request: ShiftRequest, 
                              available_pharmacists: List[Dict[str, Any]]) -> bool:
        """薬剤師Botに通知を送信"""
        try:
            # 実際の実装では、薬剤師BotのAPIエンドポイントを呼び出す
            # ここでは簡易的にログ出力のみ
            pharmacist_names = [p["name"] for p in available_pharmacists]
            logger.info(f"Notifying pharmacist bot for request {shift_request.id}")
            logger.info(f"Available pharmacists: {pharmacist_names}")
            
            # TODO: 薬剤師BotのAPIを呼び出して通知を送信
            # pharmacist_bot_api.notify_pharmacists(shift_request, available_pharmacists)
            
            return True
            
        except Exception as e:
            logger.error(f"Error notifying pharmacist bot: {e}")
            return False

    def get_request_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """依頼状況を取得"""
        try:
            # Google Sheetsから応募状況を取得
            # 実際の実装では、応募記録シートから該当依頼の状況を取得
            logger.info(f"Getting status for request: {request_id}")
            
            # モックデータ
            status_data = {
                "request_id": request_id,
                "status": "pending",
                "applications": 0,
                "confirmed": 0,
                "created_at": datetime.now().isoformat()
            }
            
            return status_data
            
        except Exception as e:
            logger.error(f"Error getting request status: {e}")
            return None

    def confirm_application(self, request_id: str, pharmacist_id: str) -> bool:
        """応募を確定"""
        try:
            # Google Sheetsに確定情報を記録
            success = self.google_sheets_service.update_application_status(
                request_id, 
                "薬剤師名",  # 実際は薬剤師名を取得
                "confirmed"
            )
            
            if success:
                logger.info(f"Application confirmed for request {request_id}, pharmacist {pharmacist_id}")
                return True
            else:
                logger.error(f"Failed to confirm application for request {request_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error confirming application: {e}")
            return False


# グローバルインスタンス
store_schedule_service = StoreScheduleService() 