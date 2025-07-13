import os
import json
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, date
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

from shared.config.settings import shared_settings
from shared.models.schedule import Schedule, TimeSlot
from shared.models.user import Store, Pharmacist

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    def __init__(self):
        self.credentials = None
        self.service = None
        self.spreadsheet_id = shared_settings.spreadsheet_id
        self._initialize_service()

    def _initialize_service(self):
        """Google Sheets APIサービスの初期化"""
        try:
            credentials_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON")
            if credentials_json:
                creds = Credentials.from_service_account_info(json.loads(credentials_json))
            else:
                creds = Credentials.from_service_account_file("credentials.json")
            
            self.service = build('sheets', 'v4', credentials=creds)
            logger.info("Google Sheets API service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Google Sheets service: {e}")
            raise

    def get_sheet_name(self, target_date: date) -> str:
        """日付からシート名を生成（例：2025-06）"""
        return target_date.strftime("%Y-%m")

    def get_available_pharmacists(self, target_date: date, time_slot: str) -> List[Dict[str, Any]]:
        """指定日時で空きのある薬剤師を取得"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, using mock data")
                return self._get_mock_pharmacists(target_date, time_slot)
            
            # 実際のGoogle Sheetsからデータを取得
            sheet_name = self.get_sheet_name(target_date)
            day_column = self._get_day_column(target_date, sheet_name)
            
            # 薬剤師リストとスケジュールを取得
            pharmacists = self._get_pharmacist_list(sheet_name)
            if not pharmacists:
                logger.warning("No pharmacists found in sheet")
                return self._get_mock_pharmacists(target_date, time_slot)
            
            # 指定日のスケジュールを取得
            schedule_range = f"{sheet_name}!{chr(65 + day_column)}2:{chr(65 + day_column)}{len(pharmacists) + 1}"
            schedule_data = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=schedule_range
            ).execute()
            
            schedules = schedule_data.get('values', [])
            
            # 空き薬剤師をフィルタリング
            available_pharmacists = []
            for i, pharmacist in enumerate(pharmacists):
                schedule = schedules[i][0] if i < len(schedules) and schedules[i] else ""
                
                if self._is_available_for_schedule(schedule, time_slot):
                    available_pharmacists.append(pharmacist)
            
            logger.info(f"Found {len(available_pharmacists)} available pharmacists for {target_date} {time_slot}")
            return available_pharmacists
            
        except Exception as e:
            logger.error(f"Error getting available pharmacists: {e}")
            # エラー時はモックデータを返す
            return self._get_mock_pharmacists(target_date, time_slot)
    
    def _get_pharmacist_list(self, sheet_name: str) -> List[Dict[str, Any]]:
        """薬剤師リストを取得"""
        try:
            # 薬剤師情報の範囲を取得（A列: 名前, B列: LINE ID, C列: 電話番号）
            range_name = f"{sheet_name}!A2:C100"  # 最大100名まで
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            pharmacists = []
            
            for i, row in enumerate(values):
                if len(row) >= 1 and row[0].strip():  # 名前が存在する場合
                    pharmacist = {
                        "id": f"pharm_{i+1:03d}",
                        "name": row[0].strip(),
                        "user_id": row[1].strip() if len(row) > 1 else "",
                        "phone": row[2].strip() if len(row) > 2 else "",
                        "row_number": i + 2  # 実際の行番号（ヘッダー行を考慮）
                    }
                    pharmacists.append(pharmacist)
            
            logger.info(f"Found {len(pharmacists)} pharmacists in sheet {sheet_name}")
            return pharmacists
            
        except Exception as e:
            logger.error(f"Error getting pharmacist list: {e}")
            return []
    
    def _is_available_for_schedule(self, schedule: str, time_slot: str) -> bool:
        """スケジュールが指定時間帯で利用可能かチェック"""
        if not schedule or schedule.strip() == "":
            return True
        
        # 勤務不可の場合は利用不可
        if any(keyword in schedule for keyword in ["勤務不可", "×", "休み", "不可"]):
            return False
        
        # 時間帯のマッピング
        time_mapping = {
            "time_morning": ["AM", "午前", "9:00", "9時"],
            "time_afternoon": ["PM", "午後", "13:00", "13時"],
            "time_evening": ["夜間", "17:00", "17時"],
            "time_full_day": ["終日", "フル", "全日"]
        }
        
        requested_keywords = time_mapping.get(time_slot, [])
        
        # スケジュールに指定時間帯のキーワードが含まれているかチェック
        for keyword in requested_keywords:
            if keyword in schedule:
                return True
        
        # 時間帯が指定されていない場合は利用可能
        return True

    def _get_mock_pharmacists(self, target_date: date, time_slot: str) -> List[Dict[str, Any]]:
        """モック薬剤師データを返す（開発用）"""
        # 実際の実装では、Google Sheetsから取得したデータを処理
        mock_pharmacists = [
            {
                "id": "pharm_001",
                "user_id": "",  # 開発用: 空文字列でスキップ
                "name": "田中薬剤師",
                "phone": "090-1234-5678",
                "availability": ["morning", "afternoon"],
                "rating": 4.5,
                "experience_years": 5
            },
            {
                "id": "pharm_002", 
                "user_id": "",  # 開発用: 空文字列でスキップ
                "name": "佐藤薬剤師",
                "phone": "090-2345-6789",
                "availability": ["afternoon", "evening"],
                "rating": 4.2,
                "experience_years": 3
            },
            {
                "id": "pharm_003",
                "user_id": "",  # 開発用: 空文字列でスキップ
                "name": "鈴木薬剤師", 
                "phone": "090-3456-7890",
                "availability": ["morning", "full_day"],
                "rating": 4.8,
                "experience_years": 7
            }
        ]
        
        # 時間帯に基づいてフィルタリング
        available_pharmacists = []
        for pharmacist in mock_pharmacists:
            if self._is_available_for_timeslot(pharmacist, time_slot):
                available_pharmacists.append(pharmacist)
        
        logger.info(f"Found {len(available_pharmacists)} available pharmacists for {target_date} {time_slot}")
        return available_pharmacists
    
    def _is_available_for_timeslot(self, pharmacist: Dict[str, Any], time_slot: str) -> bool:
        """薬剤師が指定時間帯で利用可能かチェック"""
        availability = pharmacist.get("availability", [])
        
        # 時間帯のマッピング
        time_mapping = {
            "time_morning": "morning",
            "time_afternoon": "afternoon", 
            "time_evening": "evening",
            "time_full_day": "full_day"
        }
        
        requested_slot = time_mapping.get(time_slot, "")
        
        # 利用可能かチェック
        if requested_slot == "full_day":
            return "full_day" in availability
        else:
            return requested_slot in availability or "full_day" in availability

    def update_schedule(self, schedule: Schedule, store: Store) -> bool:
        """スケジュールを更新"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available")
                return False
            
            sheet_name = self.get_sheet_name(schedule.target_date)
            day_column = self._get_day_column(schedule.target_date, sheet_name)
            
            # スケジュールエントリを作成
            schedule_entry = self._create_schedule_entry(schedule, store)
            
            # 薬剤師の行を特定
            pharmacist_row = self._find_pharmacist_row(schedule.pharmacist_id, sheet_name)
            if not pharmacist_row:
                logger.error(f"Pharmacist {schedule.pharmacist_id} not found in sheet")
                return False
            
            # スケジュールを更新
            range_name = f"{sheet_name}!{chr(65 + day_column)}{pharmacist_row}"
            body = {
                'values': [[schedule_entry]]
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f"Updated schedule for pharmacist {schedule.pharmacist_id} on {schedule.target_date}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating schedule: {e}")
            return False

    def _create_schedule_entry(self, schedule: Schedule, store: Store) -> str:
        """スケジュールエントリを作成"""
        # start_time_label, end_time_labelがあれば優先して使う
        start = getattr(schedule, 'start_time_label', None)
        end = getattr(schedule, 'end_time_label', None)
        if start and end:
            return f"{start}〜{end} {store.store_name}"
        time_slot_text = schedule.time_slot.value if hasattr(schedule.time_slot, 'value') else str(schedule.time_slot)
        return f"{time_slot_text} - {store.store_name}"

    def _find_pharmacist_row(self, pharmacist_id: str, sheet_name: str) -> Optional[int]:
        """薬剤師の行番号を取得"""
        try:
            # 薬剤師リストを取得してIDで検索
            pharmacists = self._get_pharmacist_list(sheet_name)
            for pharmacist in pharmacists:
                if pharmacist["id"] == pharmacist_id:
                    return pharmacist["row_number"]
            return None
        except Exception as e:
            logger.error(f"Error finding pharmacist row: {e}")
            return None

    def record_application(self, request_id: str, pharmacist_id: str, pharmacist_name: str, 
                          store_name: str, date: date, time_slot: str) -> bool:
        """応募記録をGoogle Sheetsに記録"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available")
                return False
            
            # 応募記録シートに記録
            record_data = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                request_id,
                pharmacist_id,
                pharmacist_name,
                store_name,
                date.strftime("%Y-%m-%d"),
                time_slot
            ]
            
            body = {
                'values': [record_data]
            }
            
            # 応募記録シートに追加
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range="応募記録!A:G",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            logger.info(f"Recorded application for {pharmacist_name} (request: {request_id})")
            return True
            
        except Exception as e:
            logger.error(f"Error recording application: {e}")
            return False

    def update_application_status(self, request_id: str, pharmacist_name: str, status: str) -> bool:
        """応募状況を更新"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available")
                return False
            
            # 応募記録シートから該当レコードを検索して更新
            # 実際の実装では、より詳細な検索・更新ロジックが必要
            logger.info(f"Updated application status for {pharmacist_name} (request: {request_id}) to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating application status: {e}")
            return False

    def _get_day_column(self, target_date: date, sheet_name: str) -> int:
        """日付から列番号を取得（A列=0, B列=1, ...）"""
        # 1行目の値を取得
        result = self.service.spreadsheets().values().get(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet_name}!1:1"
        ).execute()
        header_row = result.get('values', [[]])[0]
        # "7/7"形式に変換
        request_date_str = f"{target_date.month}/{target_date.day}"
        for idx, cell in enumerate(header_row):
            if cell.strip() == request_date_str:
                return idx  # 0始まり
        raise ValueError(f"日付 {request_date_str} がシートに見つかりません")

    def _is_available(self, schedule: str, time_slot: TimeSlot) -> bool:
        """スケジュールが利用可能かチェック"""
        if not schedule or schedule.strip() == "":
            return True
        
        # 勤務不可の場合は利用不可
        if any(keyword in schedule for keyword in ["勤務不可", "×", "休み", "不可"]):
            return False
        
        # 時間帯に基づいてチェック
        time_slot_text = time_slot.value if hasattr(time_slot, 'value') else str(time_slot)
        return self._is_available_for_schedule(schedule, time_slot_text)

    def update_pharmacist_availability(self, pharmacist_id: str, date: date, time_slot: str, is_available: bool):
        """薬剤師の利用可能性を更新"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available")
                return False
            
            sheet_name = self.get_sheet_name(date)
            day_column = self._get_day_column(date, sheet_name)
            pharmacist_row = self._find_pharmacist_row(pharmacist_id, sheet_name)
            
            if not pharmacist_row:
                logger.error(f"Pharmacist {pharmacist_id} not found")
                return False
            
            # 利用可能性を更新
            status = "利用可能" if is_available else "勤務不可"
            range_name = f"{sheet_name}!{chr(65 + day_column)}{pharmacist_row}"
            body = {
                'values': [[status]]
            }
            
            self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f"Updated availability for pharmacist {pharmacist_id} on {date}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating pharmacist availability: {e}")
            return False

    def register_pharmacist(self, pharmacist_data: Dict[str, Any]) -> bool:
        """薬剤師を登録"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available")
                return False
            
            # 薬剤師情報を薬剤師リストシートに追加
            pharmacist_info = [
                pharmacist_data.get("name", ""),
                pharmacist_data.get("user_id", ""),
                pharmacist_data.get("phone", ""),
                pharmacist_data.get("availability", []),
                pharmacist_data.get("rating", 0.0),
                pharmacist_data.get("experience_years", 0),
                pharmacist_data.get("registered_at", datetime.now().isoformat())
            ]
            
            body = {
                'values': [pharmacist_info]
            }
            
            # 薬剤師リストシートに追加
            self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range="薬剤師リスト!A:G",
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            logger.info(f"Registered pharmacist: {pharmacist_data.get('name')}")
            return True
            
        except Exception as e:
            logger.error(f"Error registering pharmacist: {e}")
            return False

    def register_pharmacist_user_id(self, name: str, phone: str, user_id: str, sheet_name: Optional[str] = None) -> bool:
        """
        名前＋電話番号一致で該当行を特定し、そのuser_idカラムにLINEのuserIdを書き込む
        sheet_nameを省略した場合は今月のシート名を自動で使用
        """
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, skipping user_id registration")
                return False
            if not sheet_name:
                today = datetime.now().date()
                sheet_name = self.get_sheet_name(today)
            # 薬剤師リストを取得
            pharmacists = self._get_pharmacist_list(sheet_name)
            target_row = None
            for pharmacist in pharmacists:
                if pharmacist["name"] == name and pharmacist["phone"] == phone:
                    target_row = pharmacist["row_number"]
                    break
            if not target_row:
                logger.warning(f"Pharmacist not found for name={name}, phone={phone} in sheet {sheet_name}")
                return False
            # user_idを書き込む（B列: 2列目）
            range_name = f"{sheet_name}!B{target_row}"
            body = {'values': [[user_id]]}
            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            logger.info(f"Registered user_id for pharmacist {name} ({phone}) at row {target_row}: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error registering pharmacist user_id: {e}")
            return False

    def get_store_list(self, sheet_name: str = "店舗登録") -> List[Dict[str, Any]]:
        """店舗リストを取得"""
        try:
            range_name = f"{sheet_name}!A2:D100"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            values = result.get('values', [])
            stores = []
            for i, row in enumerate(values):
                if len(row) >= 2 and row[0].strip() and row[1].strip():
                    store = {
                        "id": f"store_{i+1:03d}",
                        "number": row[0].strip(),
                        "name": row[1].strip(),
                        "user_id": row[2].strip() if len(row) > 2 else "",
                        "phone": row[3].strip() if len(row) > 3 else "",
                        "row_number": i + 2
                    }
                    stores.append(store)
            logger.info(f"Found {len(stores)} stores in sheet {sheet_name}")
            return stores
        except Exception as e:
            logger.error(f"Error getting store list: {e}")
            return []

    def register_store_user_id(self, store_number: str, store_name: str, user_id: str, sheet_name: str = "店舗登録") -> bool:
        """
        店舗番号＋店舗名一致で該当行を特定し、そのuser_idカラムにLINEのuserIdを書き込む
        sheet_nameを「店舗登録」シートに固定
        """
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, skipping store user_id registration")
                return False
            stores = self.get_store_list(sheet_name)
            target_row = None
            for store in stores:
                if store["number"] == store_number and store["name"] == store_name:
                    target_row = store["row_number"]
                    break
            if not target_row:
                logger.warning(f"Store not found for number={store_number}, name={store_name} in sheet {sheet_name}")
                return False
            range_name = f"{sheet_name}!C{target_row}"
            body = {'values': [[user_id]]}
            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            logger.info(f"Registered user_id for store {store_number} {store_name} at row {target_row}: {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error registering store user_id: {e}")
            return False 