#!/usr/bin/env python3
"""
薬剤師Bot通知機能テストスクリプト
"""
import os
import sys
from datetime import datetime

# プロジェクトのルートディレクトリをパスに追加
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.pharmacist_notification_service import PharmacistNotificationService
from app.config import settings

def test_pharmacist_notification():
    """薬剤師Botの通知機能をテスト"""
    print("🧪 薬剤師Bot通知機能テスト開始")
    
    # 設定の確認
    print(f"\n📋 設定確認:")
    print(f"薬剤師Botアクセストークン: {'設定済み' if settings.pharmacist_line_channel_access_token else '未設定'}")
    print(f"薬剤師Botシークレット: {'設定済み' if settings.pharmacist_line_channel_secret else '未設定'}")
    
    if not settings.pharmacist_line_channel_access_token:
        print("❌ 薬剤師Botのアクセストークンが設定されていません")
        print("   .envファイルにPHARMACIST_LINE_CHANNEL_ACCESS_TOKENを設定してください")
        return False
    
    if not settings.pharmacist_line_channel_secret:
        print("❌ 薬剤師Botのシークレットが設定されていません")
        print("   .envファイルにPHARMACIST_LINE_CHANNEL_SECRETを設定してください")
        return False
    
    # 通知サービスの初期化
    try:
        notification_service = PharmacistNotificationService()
        print("✅ 通知サービス初期化成功")
    except Exception as e:
        print(f"❌ 通知サービス初期化失敗: {e}")
        return False
    
    # テスト用の依頼データ
    test_request_data = {
        "date": datetime.now().date(),
        "start_time_label": "9:00",
        "end_time_label": "18:00",
        "break_time_label": "1時間",
        "count_text": "1名",
        "store": "テスト薬局"
    }
    
    # テスト用の薬剤師データ（実際のuser_idに置き換えてください）
    test_pharmacists = [
        {
            "user_id": "U32985fe83988007da045f7b65c3bb90f",  # 実際のuser_id
            "name": "田中薬剤師"
        }
    ]
    
    print(f"\n📤 通知送信テスト:")
    print(f"送信先: {test_pharmacists[0]['name']} ({test_pharmacists[0]['user_id']})")
    
    # 通知送信テスト
    try:
        result = notification_service.notify_pharmacists_of_request(
            test_pharmacists,
            test_request_data,
            "test_request_001"
        )
        
        print(f"\n📊 通知結果:")
        print(f"総薬剤師数: {result['total_pharmacists']}")
        print(f"通知成功数: {result['notified_count']}")
        print(f"通知失敗数: {result['failed_count']}")
        
        if result['failed_count'] > 0:
            print(f"失敗詳細: {result['failed_pharmacists']}")
        
        if result['notified_count'] > 0:
            print("✅ 通知送信テスト成功")
            return True
        else:
            print("❌ 通知送信テスト失敗")
            return False
            
    except Exception as e:
        print(f"❌ 通知送信テスト中にエラー: {e}")
        return False

if __name__ == "__main__":
    success = test_pharmacist_notification()
    if success:
        print("\n🎉 テスト完了: 薬剤師Botの通知機能は正常に動作しています")
    else:
        print("\n💥 テスト失敗: 設定を確認してください")
        print("\n🔧 確認事項:")
        print("1. .envファイルにPHARMACIST_LINE_CHANNEL_ACCESS_TOKENが設定されているか")
        print("2. .envファイルにPHARMACIST_LINE_CHANNEL_SECRETが設定されているか")
        print("3. 薬剤師BotのLINE公式アカウントが正しく設定されているか")
        print("4. テスト用のuser_idが薬剤師Botの友だち追加されているか") 