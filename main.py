import os
import asyncio
import json
from fastapi import FastAPI, Request
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
import uvicorn

# ---- 環境変数 ----
LINE_TOKEN = os.getenv("2008577971")  # チャネルアクセストークン
TARGET_USER = os.getenv("yuumi_takaki05")  # TikTokユーザーID（@なし）

if not LINE_TOKEN or not TARGET_USER:
    raise ValueError("LINE_TOKEN または TARGET_USER が設定されていません")

# ---- 送信先ユーザーIDリスト ----
USER_IDS = set()  # Webhookで登録されたuserIdを保持

# ---- LINE送信関数 ----
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

# ---- TikTokLive クライアント ----
client = TikTokLiveClient(unique_id=TARGET_USER)

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    msg = f"{TARGET_USER} さんが TikTokライブを開始しました！"
    print(msg)
    send_line_message(USER_IDS, msg)

# ---- FastAPI Webhookサーバ ----
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

# ---- TikTokライブ監視 + Webhookサーバ 並列実行 ----
async def main():
    tiktok_task = asyncio.create_task(client.start())
    uvicorn_task = asyncio.create_task(uvicorn.run(app, host="0.0.0.0", port=10000))
    await asyncio.gather(tiktok_task, uvicorn_task)

if __name__ == "__main__":
    asyncio.run(main())
