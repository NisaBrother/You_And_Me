import os
import asyncio
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
from fastapi import FastAPI
import uvicorn

# ---- 環境変数 ----
LINE_TOKEN = os.getenv("LINE_TOKEN")        # LINEチャネルアクセストークン
TARGET_USER = os.getenv("TARGET_USER")      # TikTok配信者ID（@なし）
MY_USER_ID = os.getenv("MY_USER_ID")        # 自分のLINE userId
PORT = int(os.getenv("PORT", 10000))       # Render が割り当てるポート

if not LINE_TOKEN or not TARGET_USER or not MY_USER_ID:
    raise ValueError("LINE_TOKEN, TARGET_USER, MY_USER_ID の環境変数を設定してください")

# ---- LINE通知関数 ----
def send_line_message(user_id, msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {
        "to": user_id,
        "messages": [{"type": "text", "text": msg}]
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=5)
        if response.status_code != 200:
            print(f"LINE送信エラー: {response.status_code} {response.text}")
    except Exception as e:
        print(f"LINE送信例外: {e}")

# ---- TikTokライブ監視 ----
client = TikTokLiveClient(unique_id=TARGET_USER)

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    msg = f"🔴 {TARGET_USER} さんがTikTokライブを開始しました！"
    print(msg)
    send_line_message(MY_USER_ID, msg)

# ---- FastAPIサーバー（Render 用健康チェック用） ----
app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ---- Webサーバー起動タスク ----
async def start_web_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

# ---- メインループ（TikTok監視＋Webサーバー） ----
async def main():
    while True:
        try:
            tiktok_task = asyncio.create_task(client.start())
            web_task = asyncio.create_task(start_web_server())
            await asyncio.gather(tiktok_task, web_task)
        except Exception as e:
            print(f"例外発生: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
