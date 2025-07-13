import re
import logging
from datetime import datetime, date
from typing import Dict, Optional, Any
import dateparser
from dateutil import parser as date_parser

from app.models.schedule import TimeSlot

logger = logging.getLogger(__name__)


def parse_pharmacist_registration(text: str) -> Optional[Dict[str, Any]]:
    """薬剤師登録情報を解析（柔軟な区切り文字対応）"""
    try:
        # 柔軟な区切り文字対応
        parts = re.split(r'[ ,、\u3000]+', text.strip())
        if len(parts) >= 2:
            return {
                "name": parts[0],
                "phone": parts[1],
                "availability": parts[2:] if len(parts) > 2 else []
            }
    except Exception:
        pass
    return None

def parse_store_registration(text: str) -> Optional[Dict[str, Any]]:
    """店舗登録情報を解析（柔軟な区切り文字対応）"""
    try:
        # "店舗登録"を除去
        text = text.replace("店舗登録", "").strip()
        
        # 柔軟な区切り文字対応
        parts = re.split(r'[ ,、\u3000]+', text)
        if len(parts) >= 2:
            return {
                "number": parts[0],
                "name": parts[1]
            }
    except Exception:
        pass
    return None

def parse_shift_request(text: str) -> Optional[Dict[str, Any]]:
    """シフト依頼を解析"""
    try:
        # 日付の抽出
        date_match = re.search(r'(\d{1,2})[/\-](\d{1,2})', text)
        if not date_match:
            return None
        
        month, day = map(int, date_match.groups())
        year = datetime.now().year
        target_date = date(year, month, day)
        
        # 時間帯の抽出
        time_slot = None
        if re.search(r'午前|AM|am|9:00|10:00|11:00|12:00', text):
            time_slot = "time_morning"
        elif re.search(r'午後|PM|pm|13:00|14:00|15:00|16:00|17:00', text):
            time_slot = "time_afternoon"
        elif re.search(r'夜間|18:00|19:00|20:00|21:00', text):
            time_slot = "time_evening"
        else:
            time_slot = "time_full_day"
        
        # 人数の抽出
        count_match = re.search(r'(\d+)名?', text)
        required_count = int(count_match.group(1)) if count_match else 1
        
        # 備考の抽出
        notes = ""
        if "備考" in text or "メモ" in text:
            notes_match = re.search(r'(備考|メモ)[:：]\s*(.+)', text)
            if notes_match:
                notes = notes_match.group(2).strip()
        
        return {
            "date": target_date,
            "time_slot": time_slot,
            "required_count": required_count,
            "notes": notes
        }
    except Exception:
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


def parse_date_flexible(text: str) -> Optional[date]:
    """柔軟な日付解析"""
    try:
        # 様々な日付形式に対応
        date_patterns = [
            r'(\d{1,2})[/\-](\d{1,2})',  # 4/15, 4-15
            r'(\d{1,2})月(\d{1,2})日',   # 4月15日
            r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})',  # 2024/4/15
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 2:
                    month, day = map(int, match.groups())
                    year = datetime.now().year
                    return date(year, month, day)
                elif len(match.groups()) == 3:
                    year, month, day = map(int, match.groups())
                    return date(year, month, day)
        
        # dateutil.parserを使用した柔軟な解析
        return date_parser.parse(text, fuzzy=True).date()
    except Exception:
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


def extract_store_info(text: str) -> Optional[Dict[str, Any]]:
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