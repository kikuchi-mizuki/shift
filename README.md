# フリーランス薬剤師シフト調整自動化LINE Bot

## 概要
薬局からのシフト依頼を自動で薬剤師に配信し、応募管理・スケジュール調整を自動化するLINE Botシステムです。

## 機能
- 店舗からのシフト依頼受付（LINE Bot）
- 空き薬剤師の自動抽出
- 薬剤師への勤務照会送信
- 応募結果の自動記録
- Google Sheetsへの自動記入
- 確定通知の自動送信

## セットアップ

### 1. 環境構築
```bash
# 依存関係のインストール
pip install -r requirements.txt

# 環境変数の設定
cp env.example .env
# .envファイルを編集して必要な値を設定
```

### 2. LINE Bot設定
1. [LINE Developers Console](https://developers.line.biz/)でBotを作成
2. Channel Access TokenとChannel Secretを取得
3. .envファイルに設定

### 3. Google Sheets設定
1. Google Cloud Consoleでプロジェクトを作成
2. Google Sheets APIを有効化
3. サービスアカウントキーをダウンロード
4. credentials.jsonとして保存

### 4. 起動
```bash
uvicorn app.main:app --reload
```

## アーキテクチャ
- **FastAPI**: Web APIフレームワーク
- **LINE Messaging API**: Bot機能
- **Google Sheets API**: スケジュール管理
- **Redis**: セッション管理
- **SQLite**: データベース

## 開発者向け情報
詳細な開発ドキュメントは `docs/` ディレクトリを参照してください。 