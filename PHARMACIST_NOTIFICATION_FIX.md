# 薬剤師Bot通知機能修正

## 🔧 修正内容

### 1. アクセストークンの修正
**問題**: `PharmacistNotificationService`で店舗Botのアクセストークンを使用していた
**修正**: 薬剤師Bot専用のアクセストークンを使用するように変更

```python
# 修正前
self.line_bot_api = LineBotApi(settings.line_channel_access_token)

# 修正後
self.line_bot_api = LineBotApi(settings.pharmacist_line_channel_access_token)
```

### 2. 環境変数マッピングの追加
**問題**: app/config.pyで環境変数名が正しくマッピングされていなかった
**修正**: 環境変数名の明示的なマッピングを追加

```python
class Config:
    env_file = ".env"
    fields = {
        "line_channel_access_token": {"env": "STORE_LINE_CHANNEL_ACCESS_TOKEN"},
        "line_channel_secret": {"env": "STORE_LINE_CHANNEL_SECRET"},
        "pharmacist_line_channel_access_token": {"env": "PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN"},
        "pharmacist_line_channel_secret": {"env": "PHARMACIST_LINE_CHANNEL_SECRET"},
        # ...
    }
```

### 3. エラーハンドリングの改善
**問題**: LINE APIエラーの詳細情報が取得できなかった
**修正**: LineBotApiErrorの詳細情報をログ出力

```python
except LineBotApiError as e:
    logger.error(f"Error sending notification to pharmacist {pharmacist_name}: {e}")
    if hasattr(e, 'status_code'):
        logger.error(f"Error status code: {e.status_code}")
    if hasattr(e, 'error_response'):
        logger.error(f"Error response: {e.error_response}")
    if hasattr(e, 'request_id'):
        logger.error(f"Request ID: {e.request_id}")
```

### 4. デバッグログの追加
**問題**: アクセストークンの設定状況が確認できなかった
**修正**: 初期化時にアクセストークンの設定状況をログ出力

```python
if pharmacist_token:
    logger.info(f"Pharmacist notification service initialized with token: {pharmacist_token[:10]}...")
else:
    logger.warning("Pharmacist LINE channel access token is not set!")
```

## 📋 必要な設定

### .envファイルの設定
```bash
# 店舗Bot用LINE設定
STORE_LINE_CHANNEL_ACCESS_TOKEN=your_store_line_channel_access_token_here
STORE_LINE_CHANNEL_SECRET=your_store_line_channel_secret_here

# 薬剤師Bot用LINE設定
PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN=your_pharmacist_line_channel_access_token_here
PHARMACIST_LINE_CHANNEL_SECRET=your_pharmacist_line_channel_secret_here
```

### LINE Developersでの設定
1. **薬剤師Bot用チャネル**を作成
2. **チャネルシークレット**と**アクセストークン（長期）**を取得
3. **Webhook URL**を設定: `https://<your-domain>/pharmacist/line/webhook`

## 🧪 テスト方法

### テストスクリプトの実行
```bash
python test_pharmacist_notification.py
```

### 手動テスト
1. 薬剤師BotのLINE公式アカウントを友だち追加
2. 店舗Botから勤務依頼を送信
3. 薬剤師Botに通知が届くことを確認

## 🔍 トラブルシューティング

### よくある問題

1. **"Failed to send messages" エラー**
   - 薬剤師Botのアクセストークンが正しく設定されているか確認
   - 薬剤師BotのLINE公式アカウントが正しく設定されているか確認
   - 送信先のuser_idが薬剤師Botの友だち追加されているか確認

2. **"Invalid signature" エラー**
   - 薬剤師Botのチャネルシークレットが正しく設定されているか確認

3. **通知が届かない**
   - 薬剤師BotのWebhook URLが正しく設定されているか確認
   - 薬剤師Botのサーバーが起動しているか確認

### ログ確認
```bash
# アプリケーションログの確認
tail -f app.log

# 薬剤師Botのログ確認
docker-compose logs pharmacist-bot
```

## ✅ 修正後の動作確認

1. **設定確認**
   - 環境変数が正しく設定されているか
   - LINE Developersの設定が正しいか

2. **通知送信テスト**
   - テストスクリプトで通知送信をテスト
   - 実際のLINE Botで通知送信をテスト

3. **エラーログ確認**
   - 詳細なエラー情報がログに出力されるか確認

---

**修正完了後は、必ずサーバーを再起動してからテストしてください。** 