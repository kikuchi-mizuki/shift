#!/usr/bin/env python3
"""
薬剤師Bot独立起動スクリプト
"""
import uvicorn
import os
from pharmacist_bot.main import app

if __name__ == "__main__":
    # Railwayの環境変数に対応
    port = int(os.getenv("PORT", 8002))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"🚀 薬剤師Botを起動中...")
    print(f"📍 ホスト: {host}")
    print(f"🔌 ポート: {port}")
    print(f"🌐 Webhook URL: https://<your-domain>/pharmacist/line/webhook")
    
    uvicorn.run(
        "pharmacist_bot.main:app",
        host=host,
        port=port,
        reload=True
    ) 