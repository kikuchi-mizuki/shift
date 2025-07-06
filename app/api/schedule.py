import logging
from typing import List, Optional
from datetime import date, datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.services.schedule_service import ScheduleService
from app.services.google_sheets_service import GoogleSheetsService
from app.models.schedule import ShiftRequest, Schedule, TimeSlot
from app.models.user import Store, Pharmacist

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])

schedule_service = ScheduleService()
google_sheets_service = GoogleSheetsService()


class ShiftRequestCreate(BaseModel):
    store_id: str
    date: date
    time_slot: TimeSlot
    required_count: int
    notes: Optional[str] = None


class ShiftRequestResponse(BaseModel):
    id: str
    store_id: str
    date: date
    time_slot: TimeSlot
    required_count: int
    notes: Optional[str] = None
    status: str
    created_at: str


class ScheduleResponse(BaseModel):
    id: str
    shift_request_id: str
    pharmacist_id: str
    store_id: str
    date: date
    time_slot: TimeSlot
    notes: Optional[str] = None
    status: str
    created_at: str


@router.post("/shift-requests", response_model=ShiftRequestResponse)
async def create_shift_request(request: ShiftRequestCreate):
    """シフト依頼を作成"""
    try:
        # 店舗情報を取得（実際はデータベースから取得）
        store = Store(
            id=request.store_id,
            user_id="user_1",
            store_number="001",
            store_name="メイプル薬局",
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # シフト依頼を作成
        shift_request = schedule_service.create_shift_request(
            store=store,
            target_date=request.date,
            time_slot=request.time_slot,
            required_count=request.required_count,
            notes=request.notes
        )
        
        # シフト依頼を処理
        success = schedule_service.process_shift_request(shift_request, store)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to process shift request")
        
        return ShiftRequestResponse(
            id=shift_request.id,
            store_id=shift_request.store_id,
            date=shift_request.date,
            time_slot=shift_request.time_slot,
            required_count=shift_request.required_count,
            notes=shift_request.notes,
            status=shift_request.status,
            created_at=shift_request.created_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error creating shift request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/shift-requests/{request_id}", response_model=ShiftRequestResponse)
async def get_shift_request(request_id: str):
    """シフト依頼の詳細を取得"""
    try:
        if request_id not in schedule_service.shift_requests:
            raise HTTPException(status_code=404, detail="Shift request not found")
        
        shift_request = schedule_service.shift_requests[request_id]
        
        return ShiftRequestResponse(
            id=shift_request.id,
            store_id=shift_request.store_id,
            date=shift_request.date,
            time_slot=shift_request.time_slot,
            required_count=shift_request.required_count,
            notes=shift_request.notes,
            status=shift_request.status,
            created_at=shift_request.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting shift request: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/shift-requests/{request_id}/responses")
async def get_pharmacist_responses(request_id: str):
    """薬剤師の応答一覧を取得"""
    try:
        responses = schedule_service.get_pharmacist_responses(request_id)
        
        return {
            "request_id": request_id,
            "responses": [
                {
                    "id": response.id,
                    "pharmacist_id": response.pharmacist_id,
                    "response": response.response.value,
                    "conditions": response.conditions,
                    "response_time": response.response_time.isoformat()
                }
                for response in responses
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting pharmacist responses: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/schedules", response_model=List[ScheduleResponse])
async def get_schedules(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    store_id: Optional[str] = None,
    pharmacist_id: Optional[str] = None
):
    """スケジュール一覧を取得"""
    try:
        schedules = list(schedule_service.schedules.values())
        
        # フィルタリング
        if start_date:
            schedules = [s for s in schedules if s.date >= start_date]
        if end_date:
            schedules = [s for s in schedules if s.date <= end_date]
        if store_id:
            schedules = [s for s in schedules if s.store_id == store_id]
        if pharmacist_id:
            schedules = [s for s in schedules if s.pharmacist_id == pharmacist_id]
        
        return [
            ScheduleResponse(
                id=schedule.id,
                shift_request_id=schedule.shift_request_id,
                pharmacist_id=schedule.pharmacist_id,
                store_id=schedule.store_id,
                date=schedule.date,
                time_slot=schedule.time_slot,
                notes=schedule.notes,
                status=schedule.status,
                created_at=schedule.created_at.isoformat()
            )
            for schedule in schedules
        ]
        
    except Exception as e:
        logger.error(f"Error getting schedules: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/available-pharmacists")
async def get_available_pharmacists(target_date: date, time_slot: TimeSlot):
    """指定日時で空きのある薬剤師を取得"""
    try:
        available_pharmacists = google_sheets_service.get_available_pharmacists(
            target_date, time_slot
        )
        
        return {
            "date": target_date.isoformat(),
            "time_slot": time_slot.value,
            "available_pharmacists": [
                {
                    "id": pharmacist.id,
                    "name": pharmacist.name,
                    "priority_level": pharmacist.priority_level
                }
                for pharmacist in available_pharmacists
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting available pharmacists: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/schedules/{schedule_id}/cancel")
async def cancel_schedule(schedule_id: str):
    """スケジュールをキャンセル"""
    try:
        if schedule_id not in schedule_service.schedules:
            raise HTTPException(status_code=404, detail="Schedule not found")
        
        schedule = schedule_service.schedules[schedule_id]
        schedule.status = "cancelled"
        schedule.updated_at = datetime.now()
        
        # Google Sheetsから削除（実際の実装では削除処理を追加）
        
        return {"message": "Schedule cancelled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling schedule: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/statistics")
async def get_statistics(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """統計情報を取得"""
    try:
        schedules = list(schedule_service.schedules.values())
        
        # フィルタリング
        if start_date:
            schedules = [s for s in schedules if s.date >= start_date]
        if end_date:
            schedules = [s for s in schedules if s.date <= end_date]
        
        # 統計を計算
        total_schedules = len(schedules)
        confirmed_schedules = len([s for s in schedules if s.status == "confirmed"])
        cancelled_schedules = len([s for s in schedules if s.status == "cancelled"])
        
        # 時間帯別統計
        time_slot_stats = {}
        for time_slot in TimeSlot:
            time_slot_stats[time_slot.value] = len([
                s for s in schedules 
                if s.time_slot == time_slot and s.status == "confirmed"
            ])
        
        return {
            "period": {
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            },
            "total_schedules": total_schedules,
            "confirmed_schedules": confirmed_schedules,
            "cancelled_schedules": cancelled_schedules,
            "confirmation_rate": confirmed_schedules / total_schedules if total_schedules > 0 else 0,
            "time_slot_statistics": time_slot_stats
        }
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") 