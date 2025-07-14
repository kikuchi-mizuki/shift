FROM python:3.11-slim

WORKDIR /app

# システム依存関係のインストール
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python依存関係のコピーとインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー
COPY . .

# データディレクトリの作成
RUN mkdir -p data

# ポートの公開
EXPOSE 8000

# アプリケーションの起動
CMD sh -c "uvicorn integrated_main:app --host 0.0.0.0 --port $PORT" 