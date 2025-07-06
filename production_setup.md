# 本番環境でのLINE接続設定

## 1. 環境変数ファイルの作成

プロジェクトルートに `.env` ファイルを作成し、以下の内容を設定してください：

```bash
# LINE Bot設定（実際の値に置き換えてください）
LINE_CHANNEL_ACCESS_TOKEN=your_actual_channel_access_token_here
LINE_CHANNEL_SECRET=your_actual_channel_secret_here

# Google Sheets設定
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
SPREADSHEET_ID=your_actual_spreadsheet_id_here

# Redis設定
REDIS_URL=redis://localhost:6379

# データベース設定
DATABASE_URL=sqlite:///./pharmacy_schedule.db

# アプリケーション設定
DEBUG=False
SECRET_KEY=your_secure_secret_key_here

# 本番環境設定
ENVIRONMENT=production
```

## 2. LINE Developers Console設定

### A. プロバイダー・チャネル作成
1. https://developers.line.biz/ にアクセス
2. プロバイダーを選択または新規作成
3. Messaging APIチャネルを新規作成

### B. チャネル基本設定
- チャネル名: 薬局シフト管理Bot
- チャネル説明: 薬局のシフト管理を自動化するLINE Bot
- 大分類: ビジネス
- 小分類: その他

### C. Messaging API設定
- Webhook URL: `https://your-domain.com/line/webhook`
- Webhookの利用: 有効
- 検証: 有効

### D. 取得する情報
- Channel Secret
- Channel Access Token（長期）

## 3. 本番サーバー設定

### A. ドメイン・SSL証明書
- ドメインを取得（例: your-domain.com）
- SSL証明書を設定（Let's Encrypt推奨）

### B. サーバー環境
- Python 3.9以上
- Redis
- プロセス管理（systemd, supervisor等）

### C. リバースプロキシ設定（Nginx例）
```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 4. アプリケーション起動

### A. 本番用起動コマンド
```bash
# 環境変数を読み込んで起動
source .env && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### B. systemdサービス設定例
```ini
[Unit]
Description=Pharmacy Schedule Bot
After=network.target

[Service]
Type=exec
User=your-user
WorkingDirectory=/path/to/sche_input
Environment=PATH=/path/to/sche_input/.venv/bin
ExecStart=/path/to/sche_input/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always

[Install]
WantedBy=multi-user.target
```

## 5. 薬剤師登録フロー

### A. 薬剤師のLINE Bot友達追加
1. 薬剤師がLINE Botを友達追加
2. システムがユーザーIDを取得
3. Google Sheetsに薬剤師情報を登録

### B. 薬剤師情報のGoogle Sheets登録
以下の列を含むシートを作成：
- 薬剤師ID
- 名前
- LINEユーザーID
- 電話番号
- 対応可能時間
- 評価
- 経験年数

## 6. 動作確認

### A. Webhook URL検証
LINE Developers Consoleで「検証」ボタンをクリック

### B. テストメッセージ
1. LINE Botに「勤務依頼」と送信
2. フローが正常に動作することを確認

### C. ログ確認
```bash
# アプリケーションログを確認
tail -f /var/log/pharmacy-bot.log
```

## 7. トラブルシューティング

### A. よくある問題
1. **Webhook URLエラー**: SSL証明書、ドメイン設定を確認
2. **認証エラー**: Channel Access Token、Channel Secretを確認
3. **メッセージ送信エラー**: ユーザーIDの形式を確認

### B. ログ確認
```bash
# エラーログを確認
grep ERROR /var/log/pharmacy-bot.log
```

## 8. セキュリティ考慮事項

1. **環境変数の保護**: .envファイルの権限を600に設定
2. **SSL/TLS**: 必ずHTTPSで通信
3. **アクセス制限**: 必要に応じてIP制限を設定
4. **ログ管理**: 機密情報がログに出力されないよう注意 