# 薬剤師Bot・店舗Bot 分離設定ガイド

## 📋 概要

薬剤師Botと店舗Botを完全に分離して、それぞれ独立したLINE公式アカウントで運用するための設定ガイドです。

## 🏗️ アーキテクチャ

```
┌─────────────────┐    ┌─────────────────┐
│   薬剤師Bot     │    │    店舗Bot      │
│  LINE Channel   │    │  LINE Channel   │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          ▼                      ▼
┌─────────────────┐    ┌─────────────────┐
│ /pharmacist/    │    │   /store/       │
│ line/webhook    │    │   webhook       │
└─────────┬───────┘    └─────────┬───────┘
          │                      │
          ▼                      ▼
┌─────────────────┐    ┌─────────────────┐
│ 薬剤師Botサーバー│    │ 店舗Botサーバー │
│   Port: 8002    │    │   Port: 8001    │
└─────────────────┘    └─────────────────┘
```

## 🔧 設定手順

### 1. LINE公式アカウントの作成

#### 薬剤師Bot用
1. [LINE Developers](https://developers.line.biz/) にアクセス
2. 新しいプロバイダーまたは既存プロバイダーを選択
3. 「Messaging API」チャネルを作成
4. チャネル名: 「薬局シフト管理Bot（薬剤師版）」
5. チャネルシークレットとアクセストークン（長期）を取得

#### 店舗Bot用
1. 同様に新しい「Messaging API」チャネルを作成
2. チャネル名: 「薬局シフト管理Bot（店舗版）」
3. チャネルシークレットとアクセストークン（長期）を取得

### 2. 環境変数の設定

#### ローカル開発用 (.env)
```bash
# 店舗Bot用LINE設定
STORE_LINE_CHANNEL_ACCESS_TOKEN=your_store_line_channel_access_token_here
STORE_LINE_CHANNEL_SECRET=your_store_line_channel_secret_here

# 薬剤師Bot用LINE設定
PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN=your_pharmacist_line_channel_access_token_here
PHARMACIST_LINE_CHANNEL_SECRET=your_pharmacist_line_channel_secret_here

# Google Sheets設定（共有）
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
SPREADSHEET_ID=your_spreadsheet_id_here

# Redis設定（共有）
REDIS_URL=redis://localhost:6379

# データベース設定（共有）
DATABASE_URL=sqlite:///./pharmacy_schedule.db

# アプリケーション設定
DEBUG=True
ENVIRONMENT=development
SECRET_KEY=your-secret-key-here
```

#### Railway用
各Botのプロジェクトで以下の環境変数を設定：

**薬剤師Botプロジェクト:**
- `PHARMACIST_LINE_CHANNEL_ACCESS_TOKEN`
- `PHARMACIST_LINE_CHANNEL_SECRET`
- `GOOGLE_SHEETS_CREDENTIALS_FILE`
- `SPREADSHEET_ID`
- `REDIS_URL`
- `DATABASE_URL`
- `DEBUG`
- `ENVIRONMENT`

**店舗Botプロジェクト:**
- `STORE_LINE_CHANNEL_ACCESS_TOKEN`
- `STORE_LINE_CHANNEL_SECRET`
- `GOOGLE_SHEETS_CREDENTIALS_FILE`
- `SPREADSHEET_ID`
- `REDIS_URL`
- `DATABASE_URL`
- `DEBUG`
- `ENVIRONMENT`

### 3. Webhook URLの設定

#### LINE Developersでの設定

**薬剤師Bot:**
- Webhook URL: `https://<your-pharmacist-app>.railway.app/pharmacist/line/webhook`
- Webhookの利用: 有効
- 応答メッセージ: 無効
- グループ・複数人チャットへの参加: 有効

**店舗Bot:**
- Webhook URL: `https://<your-store-app>.railway.app/store/webhook`
- Webhookの利用: 有効
- 応答メッセージ: 無効
- グループ・複数人チャットへの参加: 有効

## 🚀 起動方法

### ローカル開発

#### 個別起動
```bash
# 薬剤師Bot
python run_pharmacist_bot.py

# 店舗Bot
python run_store_bot.py
```

#### Docker Compose起動
```bash
# 両方のBotを同時起動
docker-compose up

# バックグラウンド起動
docker-compose up -d
```

### Railwayデプロイ

#### 薬剤師Bot
1. 新しいRailwayプロジェクトを作成
2. GitHubリポジトリを接続
3. 環境変数を設定
4. `railway-pharmacist.json` を使用してデプロイ

#### 店舗Bot
1. 新しいRailwayプロジェクトを作成
2. GitHubリポジトリを接続
3. 環境変数を設定
4. `railway-store.json` を使用してデプロイ

## 📱 使用方法

### 薬剤師Bot
- 友だち追加後、名前と電話番号を送信
- 例: `田中薬剤師,090-1234-5678`
- 勤務依頼の通知を受信・応募

### 店舗Bot
- 友だち追加後、店舗登録情報を送信
- 例: `店舗登録 002 サンライズ薬局`
- 勤務依頼の作成・管理

## 🔍 トラブルシューティング

### よくある問題

1. **Webhook URLエラー**
   - LINE DevelopersのWebhook URLが正しいか確認
   - サーバーが起動しているか確認

2. **署名エラー**
   - チャネルシークレットが正しく設定されているか確認
   - 環境変数が正しく読み込まれているか確認

3. **メッセージ送信エラー**
   - アクセストークンが正しく設定されているか確認
   - Botが友だち追加されているか確認

### ログ確認

```bash
# 薬剤師Botのログ
docker-compose logs pharmacist-bot

# 店舗Botのログ
docker-compose logs store-bot
```

## 📞 サポート

問題が発生した場合は、以下を確認してください：

1. サーバーログの確認
2. LINE Developersの設定確認
3. 環境変数の設定確認
4. Webhook URLの動作確認

---

**注意:** この設定により、薬剤師Botと店舗Botは完全に分離され、それぞれ独立したLINE公式アカウントで動作します。 