import os
import asyncio
import httpx
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
from TikTokLive.client.errors import UserOfflineError, UserNotFoundError
from fastapi import FastAPI
import uvicorn

# ---- 環境変数 ----
LINE_TOKEN = os.getenv("LINE_TOKEN")
TARGET_USER = os.getenv("TARGET_USER")
MY_USER_ID = os.getenv("MY_USER_ID")
PORT = int(os.getenv("PORT", 8000))

if not LINE_TOKEN or not TARGET_USER or not MY_USER_ID:
    raise ValueError("LINE_TOKEN, TARGET_USER, MY_USER_ID を設定してください")

# ---- LINE通知関数 ----
async def send_line_message(user_id, msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, headers=headers, json=data)
            if resp.status_code != 200:
                print(f"LINE送信エラー: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"LINE送信例外: {e}")

# ---- TikTok クライアント ----
client = TikTokLiveClient(unique_id=TARGET_USER)
is_live = False

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    global is_live
    if not is_live:
        is_live = True
        msg = f"🔴 {TARGET_USER} さんがTikTokライブを開始しました！（ConnectEvent）"
        print(msg)
        await send_line_message(MY_USER_ID, msg)

# ---- TikTok ライブ状態をポーリング ----
async def poll_tiktok_live():
    global is_live
    async with httpx.AsyncClient(timeout=10) as client_http:
        while True:
            try:
                url = f"https://www.tiktok.com/api/live/detail/?unique_id={TARGET_USER}"
                resp = await client_http.get(url)
                data = resp.json()
                live_status = data.get("live_room", {}).get("room_status", 0)
                # room_status=2 がライブ中
                if live_status == 2:
                    if not is_live:
                        is_live = True
                        msg = f"🔴 {TARGET_USER} さんがTikTokライブを開始しました！（ポーリング）"
                        print(msg)
                        await send_line_message(MY_USER_ID, msg)
                else:
                    if is_live:
                        print(f"{TARGET_USER} がライブ終了を検知")
                    is_live = False
            except Exception as e:
                print(f"ポーリング例外: {e}")
            await asyncio.sleep(20)  # 20秒ごとに確認

# ---- Render スリープ回避 ----
async def keep_awake():
    async with httpx.AsyncClient() as client_http:
        while True:
            try:
                await client_http.get(f"http://localhost:{PORT}/health")
            except:
                pass
            await asyncio.sleep(600)  # 10分ごと

# ---- FastAPI サーバー（健康チェック用） ----
app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

async def start_web_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

# ---- メインループ ----
async def main():
    await asyncio.gather(
        client.start(),       # ConnectEvent 用
        poll_tiktok_live(),   # 確実通知用ポーリング
        start_web_server(),   # /health
        keep_awake()          # Render スリープ防止
    )

if __name__ == "__main__":
    asyncio.run(main())
