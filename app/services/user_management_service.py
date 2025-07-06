import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class UserType(Enum):
    """ユーザータイプ"""
    STORE = "store"           # 店舗
    PHARMACIST = "pharmacist" # 薬剤師
    UNKNOWN = "unknown"       # 未分類


class UserSession:
    """ユーザーセッション情報"""
    def __init__(self, user_id: str, user_type: UserType = UserType.UNKNOWN):
        self.user_id = user_id
        self.user_type = user_type
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.temp_data: Dict[str, Any] = {}
        self.user_info: Dict[str, Any] = {}
    
    def update_activity(self):
        """最終アクティビティを更新"""
        self.last_activity = datetime.now()
    
    def set_temp_data(self, key: str, value: Any):
        """一時データを設定"""
        logger.info(f"[set_temp_data] user_id={self.user_id}, key={key}, value={value}")
        self.temp_data[key] = value
        self.update_activity()
    
    def get_temp_data(self, key: str) -> Any:
        """一時データを取得"""
        value = self.temp_data.get(key)
        logger.info(f"[get_temp_data] user_id={self.user_id}, key={key}, value={value}")
        self.update_activity()
        return value
    
    def clear_temp_data(self):
        """一時データをクリア"""
        self.temp_data.clear()
        self.update_activity()


class UserManagementService:
    """ユーザー管理サービス"""
    
    def __init__(self):
        # ユーザーセッションを保存（実際はRedis/DBを使用）
        self.user_sessions: Dict[str, UserSession] = {}
        # ユーザータイプのマッピング
        self.user_type_mapping: Dict[str, UserType] = {}
    
    def get_or_create_session(self, user_id: str) -> UserSession:
        """ユーザーセッションを取得または作成"""
        if user_id not in self.user_sessions:
            user_type = self.user_type_mapping.get(user_id, UserType.UNKNOWN)
            self.user_sessions[user_id] = UserSession(user_id, user_type)
            logger.info(f"Created new session for user {user_id} (type: {user_type.value})")
        else:
            self.user_sessions[user_id].update_activity()
        
        return self.user_sessions[user_id]
    
    def set_user_type(self, user_id: str, user_type: UserType):
        """ユーザータイプを設定"""
        self.user_type_mapping[user_id] = user_type
        
        # 既存のセッションがある場合は更新
        if user_id in self.user_sessions:
            self.user_sessions[user_id].user_type = user_type
        
        logger.info(f"Set user type for {user_id}: {user_type.value}")
    
    def get_user_type(self, user_id: str) -> UserType:
        """ユーザータイプを取得"""
        return self.user_type_mapping.get(user_id, UserType.UNKNOWN)
    
    def is_store(self, user_id: str) -> bool:
        """店舗ユーザーかチェック"""
        return self.get_user_type(user_id) == UserType.STORE
    
    def is_pharmacist(self, user_id: str) -> bool:
        """薬剤師ユーザーかチェック"""
        return self.get_user_type(user_id) == UserType.PHARMACIST
    
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """ユーザー情報を取得"""
        session = self.get_or_create_session(user_id)
        return session.user_info
    
    def set_user_info(self, user_id: str, info: Dict[str, Any]):
        """ユーザー情報を設定"""
        session = self.get_or_create_session(user_id)
        session.user_info.update(info)
        session.update_activity()
    
    def get_temp_data(self, user_id: str, key: str) -> Any:
        """一時データを取得"""
        session = self.get_or_create_session(user_id)
        return session.get_temp_data(key)
    
    def set_temp_data(self, user_id: str, key: str, value: Any):
        """一時データを設定"""
        session = self.get_or_create_session(user_id)
        session.set_temp_data(key, value)
    
    def clear_temp_data(self, user_id: str):
        """一時データをクリア"""
        session = self.get_or_create_session(user_id)
        session.clear_temp_data()
    
    def get_all_sessions(self) -> List[UserSession]:
        """全セッションを取得"""
        return list(self.user_sessions.values())
    
    def get_active_sessions(self, minutes: int = 30) -> List[UserSession]:
        """アクティブなセッションを取得"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        return [
            session for session in self.user_sessions.values()
            if session.last_activity > cutoff_time
        ]
    
    def remove_session(self, user_id: str):
        """セッションを削除"""
        if user_id in self.user_sessions:
            del self.user_sessions[user_id]
            logger.info(f"Removed session for user {user_id}")
    
    def get_session_count(self) -> int:
        """セッション数を取得"""
        return len(self.user_sessions)
    
    def get_user_type_count(self, user_type: UserType) -> int:
        """特定タイプのユーザー数を取得"""
        return sum(1 for session in self.user_sessions.values() 
                  if session.user_type == user_type) 