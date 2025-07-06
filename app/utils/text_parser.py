import re
import logging
from datetime import datetime, date
from typing import Dict, Optional, Any
import dateparser
from dateutil import parser as date_parser

from app.models.schedule import TimeSlot

logger = logging.getLogger(__name__)


def parse_shift_request(text: str) -> Optional[Dict[str, Any]]:
    """シフト依頼のテキストを解析"""
    try:
        # 日付の抽出
        date_match = re.search(r'(\d{1,2})/(\d{1,2})', text)
        if not date_match:
            return None
        
        month, day = int(date_match.group(1)), int(date_match.group(2))
        current_year = datetime.now().year
        
        # 年を推定（過去の日付の場合は来年）
        target_date = date(current_year, month, day)
        if target_date < date.today():
            target_date = date(current_year + 1, month, day)
        
        # 時間帯の抽出
        time_slot = None
        if re.search(r'\bAM\b|\b午前\b', text, re.IGNORECASE):
            time_slot = TimeSlot.AM
        elif re.search(r'\bPM\b|\b午後\b', text, re.IGNORECASE):
            time_slot = TimeSlot.PM
        elif re.search(r'\b終日\b|\bフル\b', text):
            time_slot = TimeSlot.FULL_DAY
        
        if not time_slot:
            return None
        
        # 人数の抽出
        count_match = re.search(r'(\d+)\s*名', text)
        if not count_match:
            count_match = re.search(r'人数[：:]\s*(\d+)', text)
        
        required_count = 1  # デフォルト
        if count_match:
            required_count = int(count_match.group(1))
            if required_count > 3:
                required_count = 3  # 最大3名まで
        
        # 備考の抽出
        notes = None
        notes_match = re.search(r'備考[：:]\s*(.+)', text)
        if notes_match:
            notes = notes_match.group(1).strip()
        else:
            # 時間に関する記述を備考として抽出
            time_notes = re.search(r'(\d{1,2}:\d{2}|\d{1,2}時).*?(スタート|開始|希望)', text)
            if time_notes:
                notes = time_notes.group(0)
        
        return {
            "date": target_date,
            "time_slot": time_slot,
            "required_count": required_count,
            "notes": notes
        }
        
    except Exception as e:
        logger.error(f"Error parsing shift request: {e}")
        return None


def parse_pharmacist_response(text: str) -> Optional[Dict[str, Any]]:
    """薬剤師の応答テキストを解析"""
    try:
        # 応答の種類を判定
        response_type = None
        conditions = None
        
        # 承諾
        if re.search(r'\bはい\b|\b承諾\b|\bOK\b|\b可\b', text, re.IGNORECASE):
            response_type = "accepted"
        # 辞退
        elif re.search(r'\bいいえ\b|\b辞退\b|\b不可\b|\b×\b', text, re.IGNORECASE):
            response_type = "declined"
        # 条件付き
        elif re.search(r'\b条件付き\b|\b条件\b|\bただし\b', text):
            response_type = "conditional"
        else:
            return None
        
        # 条件の抽出
        if response_type == "conditional":
            # 時間条件
            time_condition = re.search(r'(\d{1,2}:\d{2}|\d{1,2}時).*?(以降|から|より)', text)
            if time_condition:
                conditions = f"{time_condition.group(1)}以降"
            
            # その他の条件
            if not conditions:
                condition_match = re.search(r'条件[：:]\s*(.+)', text)
                if condition_match:
                    conditions = condition_match.group(1).strip()
        
        return {
            "response_type": response_type,
            "conditions": conditions
        }
        
    except Exception as e:
        logger.error(f"Error parsing pharmacist response: {e}")
        return None


def parse_date_japanese(text: str) -> Optional[date]:
    """日本語の日付表現を解析"""
    try:
        # 日本語の日付パターン
        patterns = [
            r'(\d{1,2})月(\d{1,2})日',
            r'(\d{1,2})/(\d{1,2})',
            r'(\d{1,2})-(\d{1,2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                month, day = int(match.group(1)), int(match.group(2))
                current_year = datetime.now().year
                
                # 年を推定
                target_date = date(current_year, month, day)
                if target_date < date.today():
                    target_date = date(current_year + 1, month, day)
                
                return target_date
        
        # dateparserを使用した解析
        parsed_date = dateparser.parse(text, languages=['ja'])
        if parsed_date:
            return parsed_date.date()
        
        return None
        
    except Exception as e:
        logger.error(f"Error parsing date: {e}")
        return None


def parse_time_slot(text: str) -> Optional[TimeSlot]:
    """時間帯を解析"""
    try:
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['am', '午前', '朝']):
            return TimeSlot.AM
        elif any(word in text_lower for word in ['pm', '午後', '夕方']):
            return TimeSlot.PM
        elif any(word in text_lower for word in ['終日', 'フル', '一日']):
            return TimeSlot.FULL_DAY
        
        return None
        
    except Exception as e:
        logger.error(f"Error parsing time slot: {e}")
        return None


def extract_store_info(text: str) -> Optional[Dict[str, str]]:
    """店舗情報を抽出"""
    try:
        # 店舗番号
        store_number_match = re.search(r'店舗[番号]*[：:]\s*(\d+)', text)
        store_number = store_number_match.group(1) if store_number_match else None
        
        # 店舗名
        store_name_match = re.search(r'店舗名[：:]\s*(.+)', text)
        if not store_name_match:
            # 薬局名のパターン
            store_name_match = re.search(r'(.+薬局)', text)
        
        store_name = store_name_match.group(1).strip() if store_name_match else None
        
        if store_number or store_name:
            return {
                "store_number": store_number,
                "store_name": store_name
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Error extracting store info: {e}")
        return None


def validate_shift_request_data(data: Dict[str, Any]) -> bool:
    """シフト依頼データの妥当性を検証"""
    try:
        required_fields = ["date", "time_slot", "required_count"]
        
        for field in required_fields:
            if field not in data:
                return False
        
        # 日付の妥当性
        if not isinstance(data["date"], date):
            return False
        
        if data["date"] < date.today():
            return False
        
        # 時間帯の妥当性
        if data["time_slot"] not in [slot.value for slot in TimeSlot]:
            return False
        
        # 人数の妥当性
        if not isinstance(data["required_count"], int):
            return False
        
        if data["required_count"] < 1 or data["required_count"] > 3:
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating shift request data: {e}")
        return False 