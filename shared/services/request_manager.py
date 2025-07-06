import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RequestManager:
    """依頼内容をrequest_idで管理するサービス"""
    
    def __init__(self):
        # 実際の運用ではRedisやDBを使用
        self._requests: Dict[str, Dict[str, Any]] = {}
    
    def save_request(self, request_id: str, request_data: Dict[str, Any]) -> bool:
        """依頼内容を保存"""
        try:
            self._requests[request_id] = {
                **request_data,
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            }
            logger.info(f"Request saved: {request_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save request {request_id}: {e}")
            return False
    
    def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """依頼内容を取得"""
        try:
            request = self._requests.get(request_id)
            if request:
                logger.info(f"Request retrieved: {request_id}")
            else:
                logger.warning(f"Request not found: {request_id}")
            return request
        except Exception as e:
            logger.error(f"Failed to get request {request_id}: {e}")
            return None
    
    def update_request_status(self, request_id: str, status: str) -> bool:
        """依頼ステータスを更新"""
        try:
            if request_id in self._requests:
                self._requests[request_id]["status"] = status
                self._requests[request_id]["updated_at"] = datetime.now().isoformat()
                logger.info(f"Request status updated: {request_id} -> {status}")
                return True
            else:
                logger.warning(f"Request not found for status update: {request_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to update request status {request_id}: {e}")
            return False
    
    def delete_request(self, request_id: str) -> bool:
        """依頼内容を削除"""
        try:
            if request_id in self._requests:
                del self._requests[request_id]
                logger.info(f"Request deleted: {request_id}")
                return True
            else:
                logger.warning(f"Request not found for deletion: {request_id}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete request {request_id}: {e}")
            return False
    
    def get_all_requests(self) -> Dict[str, Dict[str, Any]]:
        """全依頼内容を取得（デバッグ用）"""
        return self._requests.copy()

    def add_applicant(self, request_id: str, user_id: str):
        """応募者を追加"""
        if request_id not in self._requests:
            return
        applicants = self._requests[request_id].setdefault("applicants", [])
        if user_id not in applicants:
            applicants.append(user_id)

    def add_confirmed(self, request_id: str, user_id: str):
        """確定者を追加"""
        if request_id not in self._requests:
            return
        confirmed = self._requests[request_id].setdefault("confirmed", [])
        if user_id not in confirmed:
            confirmed.append(user_id)

    def get_applicants(self, request_id: str):
        if request_id not in self._requests:
            return []
        return self._requests[request_id].get("applicants", [])

    def get_confirmed(self, request_id: str):
        if request_id not in self._requests:
            return []
        return self._requests[request_id].get("confirmed", [])


# グローバルインスタンス
request_manager = RequestManager() 