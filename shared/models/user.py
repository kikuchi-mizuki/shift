from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class UserType(str, Enum):
    STORE = "store"
    PHARMACIST = "pharmacist"
    ADMIN = "admin"


class User(BaseModel):
    id: str
    line_user_id: str
    user_type: UserType
    name: str
    created_at: datetime
    updated_at: datetime
    is_active: bool = True


class Store(BaseModel):
    id: str
    user_id: str
    store_number: str
    store_name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    contact_person: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class Pharmacist(BaseModel):
    id: str
    user_id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    preferred_areas: List[str] = []
    preferred_time_slots: List[str] = []
    priority_level: int = 1  # 1: 高, 2: 中, 3: 低
    is_available: bool = True
    created_at: datetime
    updated_at: datetime 