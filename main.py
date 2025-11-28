import os
import asyncio
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
from fastapi import FastAPI
import uvicorn
import httpx

LINE_TOKEN = os.getenv("LINE_TOKEN")
TARGET_USER = os.getenv("TARGET_USER")
MY_USER_ID = os.getenv("MY_USER_ID")
PORT = int(os.getenv("PORT", 8000))

if not LINE_TOKEN or not TARGET_USER or not MY_USER_ID:
    raise ValueError("環境変数未設定")

async def send_line_message_async(user_id, msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {LINE_TOKEN}"}
    data = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(url, headers=headers, json=data)
        if resp.status_code != 200:
            print(f"LINE送信エラー: {resp.status_code} {resp.text}")

client = TikTokLiveClient(unique_id=TARGET_USER)

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    msg = f"🔴 {TARGET_USER} さんがTikTokライブを開始しました！"
    print(msg)
    await send_line_message_async(MY_USER_ID, msg)

app = FastAPI()
@app.get("/health")
async def health_check():
    return {"status": "ok"}

async def start_web_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    await asyncio.gather(client.start(), start_web_server())

if __name__ == "__main__":
    asyncio.run(main())
