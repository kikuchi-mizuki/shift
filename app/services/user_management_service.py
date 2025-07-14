import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum
from app.services.google_sheets_service import GoogleSheetsService
from app.models.user import User, UserType as ModelUserType

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
        # ユーザータイプのマッピング（キャッシュ）
        self.user_type_mapping: Dict[str, UserType] = {}
        # Google Sheetsサービス
        self.google_sheets_service = GoogleSheetsService()
        # データベーステーブルを作成
        User.create_table()
    
    def get_or_create_session(self, user_id: str) -> UserSession:
        """ユーザーセッションを取得または作成"""
        if user_id not in self.user_sessions:
            # メモリキャッシュから取得を試行
            user_type = self.user_type_mapping.get(user_id, UserType.UNKNOWN)
            
            # キャッシュにない場合は永続化ストレージから取得
            if user_type == UserType.UNKNOWN:
                user_type = self._get_user_type_from_persistent_storage(user_id)
                # 取得したuser_typeをキャッシュに保存
                self.user_type_mapping[user_id] = user_type
            
            self.user_sessions[user_id] = UserSession(user_id, user_type)
            logger.info(f"Created new session for user {user_id} (type: {user_type.value})")
        else:
            self.user_sessions[user_id].update_activity()
        
        return self.user_sessions[user_id]
    
    def _get_user_type_from_persistent_storage(self, user_id: str) -> UserType:
        """永続化ストレージ（DB + Google Sheets）からuser_typeを取得"""
        try:
            # まずデータベースから取得を試行
            db_user = User.get_by_line_user_id(user_id)
            if db_user:
                logger.info(f"Found user_type in database: {db_user.user_type.value}")
                return self._convert_model_user_type(db_user.user_type)
            
            # データベースにない場合はGoogle Sheetsから取得
            user_type_str = self.google_sheets_service.get_user_type_from_sheets(user_id)
            if user_type_str:
                if user_type_str == "store":
                    return UserType.STORE
                elif user_type_str == "pharmacist":
                    return UserType.PHARMACIST
                else:
                    logger.warning(f"Unknown user_type from sheets: {user_type_str}")
                    return UserType.UNKNOWN
            else:
                logger.info(f"User type not found in persistent storage for user_id: {user_id}")
                return UserType.UNKNOWN
                
        except Exception as e:
            logger.error(f"Error getting user type from persistent storage: {e}")
            return UserType.UNKNOWN
    
    def _convert_model_user_type(self, model_user_type: ModelUserType) -> UserType:
        """ModelUserTypeをUserTypeに変換"""
        if model_user_type == ModelUserType.STORE:
            return UserType.STORE
        elif model_user_type == ModelUserType.PHARMACIST:
            return UserType.PHARMACIST
        else:
            return UserType.UNKNOWN
    
    def _convert_user_type_to_model(self, user_type: UserType) -> ModelUserType:
        """UserTypeをModelUserTypeに変換"""
        if user_type == UserType.STORE:
            return ModelUserType.STORE
        elif user_type == UserType.PHARMACIST:
            return ModelUserType.PHARMACIST
        else:
            return ModelUserType.ADMIN  # デフォルト
    
    def set_user_type(self, user_id: str, user_type: UserType, user_name: str = ""):
        """ユーザータイプを設定（メモリ + 永続化）"""
        # メモリキャッシュに保存
        self.user_type_mapping[user_id] = user_type
        
        # 既存のセッションがある場合は更新
        if user_id in self.user_sessions:
            self.user_sessions[user_id].user_type = user_type
        
        # データベースに保存
        try:
            # 既存ユーザーを取得
            db_user = User.get_by_line_user_id(user_id)
            if db_user:
                # 既存ユーザーのuser_typeを更新
                success = User.update_user_type(user_id, self._convert_user_type_to_model(user_type))
                if success:
                    logger.info(f"Successfully updated user_type in database for {user_id}: {user_type.value}")
                else:
                    logger.warning(f"Failed to update user_type in database for {user_id}")
            else:
                # 新規ユーザーを作成
                new_user = User(
                    id=f"user_{user_id[-8:]}",
                    line_user_id=user_id,
                    user_type=self._convert_user_type_to_model(user_type),
                    name=user_name or f"User_{user_id[-8:]}",
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                    is_active=True
                )
                success = new_user.save()
                if success:
                    logger.info(f"Successfully created user in database: {user_id}")
                else:
                    logger.warning(f"Failed to create user in database: {user_id}")
        except Exception as e:
            logger.error(f"Error persisting user_type to database: {e}")
        
        # Google Sheetsにも保存
        try:
            user_type_str = user_type.value
            success = self.google_sheets_service.set_user_type_in_sheets(user_id, user_type_str)
            if success:
                logger.info(f"Successfully persisted user_type to sheets for {user_id}: {user_type.value}")
            else:
                logger.warning(f"Failed to persist user_type to sheets for {user_id}: {user_type.value}")
        except Exception as e:
            logger.error(f"Error persisting user_type to sheets: {e}")
        
        logger.info(f"Set user type for {user_id}: {user_type.value}")
    
    def get_user_type(self, user_id: str) -> UserType:
        """ユーザータイプを取得（メモリキャッシュ優先）"""
        # まずメモリキャッシュから取得
        user_type = self.user_type_mapping.get(user_id, UserType.UNKNOWN)
        
        # キャッシュにない場合は永続化ストレージから取得
        if user_type == UserType.UNKNOWN:
            user_type = self._get_user_type_from_persistent_storage(user_id)
            # 取得したuser_typeをキャッシュに保存
            self.user_type_mapping[user_id] = user_type
        
        return user_type
    
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