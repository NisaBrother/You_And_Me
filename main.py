import os
import asyncio
import requests
from fastapi import FastAPI, Request
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
import uvicorn

# ---- 環境変数 ----
LINE_TOKEN = os.getenv("2008577971")
TARGET_USER = os.getenv("yuumi_takaki05")
PORT = int(os.getenv("PORT", 10000))  # Render が割り当てるポート

if not LINE_TOKEN or not TARGET_USER:
    raise ValueError("LINE_TOKEN または TARGET_USER が設定されていません")

# ---- LINE送信先ユーザーIDリスト（Webhook経由で登録） ----
USER_IDS = set()

def send_line_message(user_ids, msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    for user_id in user_ids:
        data = {
            "to": user_id,
            "messages": [{"type": "text", "text": msg}]
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 200:
            print(f"LINE送信エラー {user_id}: {response.status_code} {response.text}")

# ---- TikTokLiveClient ----
client = TikTokLiveClient(unique_id=TARGET_USER)

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    msg = f"🔴 {TARGET_USER} さんが TikTokライブを開始しました！"
    print(msg)
    send_line_message(USER_IDS, msg)

# ---- FastAPI Webhook ----
app = FastAPI()

@app.post("/webhook")
async def webhook(req: Request):
    payload = await req.json()
    events = payload.get("events", [])
    for e in events:
        if e.get("source") and e["source"].get("userId"):
            user_id = e["source"]["userId"]
            if user_id not in USER_IDS:
                USER_IDS.add(user_id)
                print(f"新規ユーザー登録: {user_id}")
    return {"status": "ok"}

# ---- Uvicornを非同期で実行する関数 ----
async def start_webhook_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

# ---- メイン関数 ----
async def main():
    # TikTokLive と Webhook を並列で起動
    tiktok_task = asyncio.create_task(client.start())
    webhook_task = asyncio.create_task(start_webhook_server())
    await asyncio.gather(tiktok_task, webhook_task)

if __name__ == "__main__":
    asyncio.run(main())
