#!/usr/bin/env python3
"""
店舗Bot独立起動スクリプト
"""
import uvicorn
import os
from store_bot.main import app

if __name__ == "__main__":
    # Railwayの環境変数に対応
    port = int(os.getenv("PORT", 8001))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"🏪 店舗Botを起動中...")
    print(f"📍 ホスト: {host}")
    print(f"🔌 ポート: {port}")
    print(f"🌐 Webhook URL: https://<your-domain>/store/webhook")
    
    uvicorn.run(
        "store_bot.main:app",
        host=host,
        port=port,
        reload=True
    ) 