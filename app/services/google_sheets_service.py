import os
import json
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, date
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

from app.config import settings
from app.models.schedule import Schedule, TimeSlot
from app.models.user import Store, Pharmacist

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    def __init__(self):
        self.credentials = None
        self.service = None
        self.spreadsheet_id = settings.spreadsheet_id
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
        """指定日時で空きのある薬剤師を取得（該当日付セルが空欄、かつ勤務不可でない薬剤師のみ）"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, using mock data")
                return self._get_mock_pharmacists(target_date, time_slot)
            sheet_name = self.get_sheet_name(target_date)
            day_column = self._get_day_column(target_date)
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
            available_pharmacists = []
            for i, pharmacist in enumerate(pharmacists):
                schedule = schedules[i][0] if i < len(schedules) and schedules[i] else ""
                # 空欄かつ勤務不可でない場合のみ
                if (not schedule or schedule.strip() == "") or (schedule.strip() not in ["勤務不可", "×", "休み", "不可"] and schedule.strip() == ""):
                    available_pharmacists.append(pharmacist)
            logger.info(f"Found {len(available_pharmacists)} available pharmacists for {target_date} (空欄のみ)" )
            return available_pharmacists
        except Exception as e:
            logger.error(f"Error getting available pharmacists: {e}")
            return self._get_mock_pharmacists(target_date, time_slot)
    
    def _get_pharmacist_list(self, sheet_name: str) -> List[Dict[str, Any]]:
        """薬剤師リストを取得"""
        try:
            # 薬剤師情報の範囲を取得（A列: 名前, B列: LINE ID, C列: 電話番号, D列: user_type）
            range_name = f"{sheet_name}!A2:D100"  # 最大100名まで
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
                        "user_type": row[3].strip() if len(row) > 3 else "pharmacist",  # デフォルトはpharmacist
                        "row_number": i + 2  # 実際の行番号（ヘッダー行を考慮）
                    }
                    pharmacists.append(pharmacist)
            
            logger.info(f"Found {len(pharmacists)} pharmacists in sheet {sheet_name}")
            return pharmacists
            
        except Exception as e:
            logger.error(f"Error getting pharmacist list: {e}")
            return []

    def get_user_type_from_sheets(self, user_id: str) -> Optional[str]:
        """Google Sheetsからuser_typeを取得"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available")
                return None
            
            # 薬剤師リストから検索
            today = datetime.now().date()
            sheet_name = self.get_sheet_name(today)
            pharmacists = self._get_pharmacist_list(sheet_name)
            
            for pharmacist in pharmacists:
                if pharmacist["user_id"] == user_id:
                    logger.info(f"Found user_type in pharmacist list: {pharmacist['user_type']}")
                    return pharmacist["user_type"]
            
            # 店舗リストから検索
            stores = self.get_store_list("店舗登録")
            for store in stores:
                if store["user_id"] == user_id:
                    logger.info(f"Found user_type in store list: store")
                    return "store"
            
            logger.info(f"User type not found for user_id: {user_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting user type from sheets: {e}")
            return None

    def set_user_type_in_sheets(self, user_id: str, user_type: str) -> bool:
        """Google Sheetsにuser_typeを設定"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available")
                return False
            
            # 薬剤師リストから検索して更新
            today = datetime.now().date()
            sheet_name = self.get_sheet_name(today)
            pharmacists = self._get_pharmacist_list(sheet_name)
            
            for pharmacist in pharmacists:
                if pharmacist["user_id"] == user_id:
                    # user_type列（D列）を更新
                    range_name = f"{sheet_name}!D{pharmacist['row_number']}"
                    body = {'values': [[user_type]]}
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=range_name,
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                    logger.info(f"Updated user_type for pharmacist {pharmacist['name']}: {user_type}")
                    return True
            
            # 店舗リストから検索して更新
            stores = self.get_store_list("店舗登録")
            for store in stores:
                if store["user_id"] == user_id:
                    # user_type列（E列）を更新
                    range_name = f"店舗登録!E{store['row_number']}"
                    body = {'values': [[user_type]]}
                    self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=range_name,
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                    logger.info(f"Updated user_type for store {store['name']}: {user_type}")
                    return True
            
            logger.warning(f"User not found for user_id: {user_id}")
            return False
            
        except Exception as e:
            logger.error(f"Error setting user type in sheets: {e}")
            return False
    
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
        """スケジュールをGoogle Sheetsに記入"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, skipping update")
                return False
            
            sheet_name = self.get_sheet_name(schedule.date)
            day_column = self._get_day_column(schedule.date)
            
            # 薬剤師の行を特定
            pharmacist_row = self._find_pharmacist_row(schedule.pharmacist_id, sheet_name)
            if pharmacist_row is None:
                logger.error(f"Pharmacist row not found for ID: {schedule.pharmacist_id}")
                return False
            
            # 記入する内容を作成
            cell_value = self._create_schedule_entry(schedule, store)
            
            # セルを更新
            range_name = f"{sheet_name}!{chr(65 + day_column)}{pharmacist_row}"
            body = {
                'values': [[cell_value]]
            }
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            logger.info(f"Schedule updated successfully: {result.get('updatedCells')} cells updated")
            return True
            
        except Exception as e:
            logger.error(f"Error updating Google Sheets: {e}")
            return False
    
    def _create_schedule_entry(self, schedule: Schedule, store: Store) -> str:
        """スケジュール記入内容を作成"""
        # 時間帯のテキスト変換
        time_text = {
            TimeSlot.AM: "AM",
            TimeSlot.PM: "PM", 
            TimeSlot.FULL_DAY: "終日"
        }.get(schedule.time_slot, "不明")
        
        # 記入内容を作成
        entry = f"{store.store_number} {store.store_name} {time_text}"
        
        if schedule.notes:
            entry += f" ({schedule.notes})"
        
        return entry
    
    def _find_pharmacist_row(self, pharmacist_id: str, sheet_name: str) -> Optional[int]:
        """薬剤師IDから行番号を取得"""
        try:
            # 薬剤師リストを取得してIDで検索
            pharmacists = self._get_pharmacist_list(sheet_name)
            
            for pharmacist in pharmacists:
                if pharmacist["id"] == pharmacist_id:
                    return pharmacist["row_number"]
            
            logger.warning(f"Pharmacist {pharmacist_id} not found in sheet {sheet_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding pharmacist row: {e}")
            return None
    
    def record_application(self, request_id: str, pharmacist_id: str, pharmacist_name: str, 
                          store_name: str, date: date, time_slot: str) -> bool:
        """応募記録をGoogle Sheetsに記入"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, skipping application record")
                return False
            
            # 応募記録用のシート名
            applications_sheet = "応募記録"
            
            # 応募記録を作成
            application_record = [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # 応募日時
                request_id,                                    # 依頼ID
                pharmacist_name,                              # 薬剤師名
                store_name,                                   # 店舗名
                date.strftime("%Y-%m-%d"),                    # 勤務日
                time_slot,                                    # 時間帯
                "応募"                                        # ステータス
            ]
            
            # 応募記録シートに追加
            range_name = f"{applications_sheet}!A:G"
            body = {
                'values': [application_record]
            }
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            logger.info(f"Application recorded successfully: {result.get('updates', {}).get('updatedCells')} cells updated")
            return True
            
        except Exception as e:
            logger.error(f"Error recording application: {e}")
            return False
    
    def update_application_status(self, request_id: str, pharmacist_name: str, status: str) -> bool:
        """応募ステータスを更新"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, skipping status update")
                return False
            
            # 応募記録用のシート名
            applications_sheet = "応募記録"
            
            # 応募記録を検索して更新
            range_name = f"{applications_sheet}!A:G"
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            
            # 該当する応募記録を検索
            for i, row in enumerate(values):
                if len(row) >= 2 and row[1] == request_id and row[2] == pharmacist_name:
                    # ステータスを更新
                    update_range = f"{applications_sheet}!G{i+1}"
                    body = {
                        'values': [[status]]
                    }
                    
                    update_result = self.service.spreadsheets().values().update(
                        spreadsheetId=self.spreadsheet_id,
                        range=update_range,
                        valueInputOption='RAW',
                        body=body
                    ).execute()
                    
                    logger.info(f"Application status updated successfully: {update_result.get('updatedCells')} cells updated")
                    return True
            
            logger.warning(f"Application record not found: {request_id} - {pharmacist_name}")
            return False
            
        except Exception as e:
            logger.error(f"Error updating application status: {e}")
            return False

    def _get_day_column(self, target_date: date) -> int:
        """日付から列番号を取得（A=0, B=1, ...）"""
        # 月の1日を基準として、該当日までの日数を計算
        month_start = date(target_date.year, target_date.month, 1)
        day_offset = (target_date - month_start).days
        
        # 1列目は薬剤師名なので、2列目から開始
        return day_offset + 1

    def _is_available(self, schedule: str, time_slot: TimeSlot) -> bool:
        """スケジュールが指定時間帯で利用可能かチェック"""
        if not schedule or schedule.strip() == "":
            return True
        
        # 勤務不可の場合は利用不可
        if "勤務不可" in schedule or "×" in schedule:
            return False
        
        # 時間帯のチェック
        if time_slot == TimeSlot.AM:
            return "AM" in schedule or "午前" in schedule or "終日" in schedule
        elif time_slot == TimeSlot.PM:
            return "PM" in schedule or "午後" in schedule or "終日" in schedule
        elif time_slot == TimeSlot.FULL_DAY:
            return "終日" in schedule
        
        return True

    def update_pharmacist_availability(self, pharmacist_id: str, date: date, time_slot: str, is_available: bool):
        """薬剤師の空き状況を更新"""
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, skipping update")
                return False
            
            # 実際のGoogle Sheets更新処理
            # ここでは簡易実装として、ログのみ出力
            logger.info(f"Updated availability for pharmacist {pharmacist_id}: {date} {time_slot} = {is_available}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating pharmacist availability: {e}")
            return False

    def register_pharmacist(self, pharmacist_data: Dict[str, Any]) -> bool:
        """
        薬剤師をGoogle Sheetsに登録
        
        Args:
            pharmacist_data: 薬剤師情報
            
        Returns:
            登録成功時True
        """
        try:
            logger.info(f"Registering pharmacist: {pharmacist_data['name']}")
            
            # 現在の年月のシート名を取得
            current_date = datetime.now()
            sheet_name = current_date.strftime("%Y-%m")
            
            # 薬剤師情報をシートに追加（user_type列を含む）
            values = [
                [
                    pharmacist_data["id"],
                    pharmacist_data["name"],
                    pharmacist_data["user_id"],
                    pharmacist_data["phone"],
                    "pharmacist",  # user_type
                    ",".join(pharmacist_data["availability"]),
                    pharmacist_data["rating"],
                    pharmacist_data["experience_years"],
                    pharmacist_data["registered_at"]
                ]
            ]
            
            # シートに追加
            range_name = f"{sheet_name}!A:I"
            body = {
                'values': values
            }
            
            result = self.service.spreadsheets().values().append(
                spreadsheetId=self.spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body=body
            ).execute()
            
            logger.info(f"Successfully registered pharmacist {pharmacist_data['name']} to Google Sheets")
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
                if pharmacist["name"].strip() == name.strip() and pharmacist["phone"].strip() == phone.strip():
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
            # 店舗情報の範囲を取得（A列: 番号, B列: 店舗名, C列: LINE ID, D列: 電話番号, E列: user_type）
            range_name = f"{sheet_name}!A2:E100"  # 最大100店舗まで
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            stores = []
            
            for i, row in enumerate(values):
                if len(row) >= 2 and row[0].strip() and row[1].strip():  # 番号と店舗名が存在する場合
                    store = {
                        "id": f"store_{i+1:03d}",
                        "number": row[0].strip(),
                        "name": row[1].strip(),
                        "user_id": row[2].strip() if len(row) > 2 else "",
                        "phone": row[3].strip() if len(row) > 3 else "",
                        "user_type": row[4].strip() if len(row) > 4 else "store",  # デフォルトはstore
                        "row_number": i + 2  # 実際の行番号（ヘッダー行を考慮）
                    }
                    stores.append(store)
            
            logger.info(f"Found {len(stores)} stores in sheet {sheet_name}")
            return stores
            
        except Exception as e:
            logger.error(f"Error getting store list: {e}")
            return []

    def register_store_user_id(self, number: str, name: str, user_id: str, sheet_name: Optional[str] = None) -> bool:
        """
        店舗番号＋店舗名一致で該当行を特定し、そのuser_idカラムにLINEのuserIdを書き込む
        sheet_nameを省略した場合は'店舗登録'をデフォルトで使用
        """
        try:
            if not self.service:
                logger.warning("Google Sheets service not available, skipping user_id registration")
                return False
            if not sheet_name:
                sheet_name = '店舗登録'
            # 店舗リストを取得
            stores = self.get_store_list(sheet_name)
            logger.info(f"Found {len(stores)} stores in sheet {sheet_name}")
            
            # デバッグ用：読み取ったデータをログ出力
            for i, store in enumerate(stores):
                logger.info(f"Store {i+1}: number='{store['number']}', name='{store['name']}'")
            
            target_row = None
            for store in stores:
                if store["number"].strip() == number.strip() and store["name"].strip() == name.strip():
                    target_row = store["row_number"]
                    break
            if target_row:
                # user_idカラム（C列）に書き込み
                range_name = f"{sheet_name}!C{target_row}"
                self.service.spreadsheets().values().update(
                    spreadsheetId=self.spreadsheet_id,
                    range=range_name,
                    valueInputOption='RAW',
                    body={'values': [[user_id]]}
                ).execute()
                logger.info(f"Registered user_id for store {name} ({number}) at row {target_row}: {user_id}")
                return True
            else:
                logger.warning(f"Store not found for number={number}, name={name} in sheet {sheet_name}")
                return False
        except Exception as e:
            logger.error(f"Error registering store user_id: {e}")
            return False 