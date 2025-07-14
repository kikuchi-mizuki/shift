from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum
import sqlite3
import logging

logger = logging.getLogger(__name__)


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

    @classmethod
    def create_table(cls, db_path: str = "pharmacy_schedule.db"):
        """データベーステーブルを作成"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    line_user_id TEXT UNIQUE NOT NULL,
                    user_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("Users table created successfully")
            
        except Exception as e:
            logger.error(f"Error creating users table: {e}")
    
    @classmethod
    def get_by_line_user_id(cls, line_user_id: str, db_path: str = "pharmacy_schedule.db") -> Optional['User']:
        """LINEユーザーIDでユーザーを取得"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT id, line_user_id, user_type, name, created_at, updated_at, is_active
                FROM users
                WHERE line_user_id = ? AND is_active = 1
            ''', (line_user_id,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return cls(
                    id=row[0],
                    line_user_id=row[1],
                    user_type=UserType(row[2]),
                    name=row[3],
                    created_at=datetime.fromisoformat(row[4]),
                    updated_at=datetime.fromisoformat(row[5]),
                    is_active=bool(row[6])
                )
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by line_user_id: {e}")
            return None
    
    def save(self, db_path: str = "pharmacy_schedule.db") -> bool:
        """ユーザーをデータベースに保存"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO users 
                (id, line_user_id, user_type, name, created_at, updated_at, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                self.id,
                self.line_user_id,
                self.user_type.value,
                self.name,
                self.created_at.isoformat(),
                self.updated_at.isoformat(),
                self.is_active
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"User saved to database: {self.line_user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving user to database: {e}")
            return False
    
    @classmethod
    def update_user_type(cls, line_user_id: str, user_type: UserType, db_path: str = "pharmacy_schedule.db") -> bool:
        """ユーザータイプを更新"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE users 
                SET user_type = ?, updated_at = ?
                WHERE line_user_id = ?
            ''', (
                user_type.value,
                datetime.now().isoformat(),
                line_user_id
            ))
            
            conn.commit()
            conn.close()
            logger.info(f"User type updated in database: {line_user_id} -> {user_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating user type in database: {e}")
            return False


class Store(BaseModel):
    id: str
    user_id: str
    store_number: str
    store_name: str
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