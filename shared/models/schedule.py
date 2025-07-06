from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class TimeSlot(str, Enum):
    AM = "AM"
    PM = "PM"
    FULL_DAY = "終日"


class ResponseStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    CONDITIONAL = "conditional"


class ShiftRequest(BaseModel):
    id: str
    store_id: str
    date: date
    time_slot: TimeSlot
    required_count: int = Field(ge=1, le=3)
    notes: Optional[str] = None
    status: str = "pending"  # pending, processing, completed, cancelled
    created_at: datetime
    updated_at: datetime


class PharmacistResponse(BaseModel):
    id: str
    shift_request_id: str
    pharmacist_id: str
    response: ResponseStatus
    conditions: Optional[str] = None
    response_time: datetime
    created_at: datetime


class Schedule(BaseModel):
    id: str
    shift_request_id: str
    pharmacist_id: str
    store_id: str
    date: date
    time_slot: TimeSlot
    notes: Optional[str] = None
    status: str = "confirmed"  # confirmed, completed, cancelled
    created_at: datetime
    updated_at: datetime 