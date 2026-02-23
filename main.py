import os
import asyncio
import httpx
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
from TikTokLive.client.errors import UserOfflineError, UserNotFoundError
from fastapi import FastAPI, Request
import uvicorn

# ---- 環境変数 ----
LINE_TOKEN = os.getenv("LINE_TOKEN")
TARGET_USER = os.getenv("TARGET_USER")
MY_USER_ID = os.getenv("MY_USER_ID")
PORT = int(os.getenv("PORT", 8000))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render が自動提供してくれる

if not LINE_TOKEN or not TARGET_USER or not MY_USER_ID:
    raise ValueError("LINE_TOKEN, TARGET_USER, MY_USER_ID の環境変数を設定してください")


# ---- LINE通知（broadcast版）----
async def send_line_message(msg):
    url = "https://api.line.me/v2/bot/message/broadcast"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {
        "messages": [
            {"type": "text", "text": msg}
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(url, headers=headers, json=data)
            if resp.status_code == 200:
                print(f"[LINE] 全員通知成功: {msg}")
            else:
                print(f"[LINE] 送信エラー {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[LINE] 送信例外: {e}")


# ---- TikTokライブ監視 ----
client = TikTokLiveClient(unique_id=TARGET_USER)
is_live = False

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    global is_live
    print("[TikTok] ConnectEvent 発火")
    if is_live:
        print("[TikTok] すでにライブ中として認識しています。通知はスキップ")
        return

    is_live = True
    msg = f"🔴 {TARGET_USER} さんがTikTokライブを開始しました！"
    print(f"[TikTok] ライブ開始検知: {msg}")
    await send_line_message(msg)


async def start_tiktok_client():
    global is_live
    while True:
        try:
            print(f"[TikTok] TikTokLiveClient を {TARGET_USER} のために起動します...")
            await client.start()

        except UserOfflineError:
            print(f"[TikTok] {TARGET_USER} がオフラインになりました")
            if is_live:
                msg = f"⚪ {TARGET_USER} さんのTikTokライブが終了しました。"
                await send_line_message(msg)
            is_live = False
            await asyncio.sleep(5)

        except UserNotFoundError:
            print(f"[TikTok] {TARGET_USER} が見つかりません。30秒後に再試行します...")
            await asyncio.sleep(30)

        except Exception as e:
            print(f"[TikTok] 例外: {e}。10秒後に再接続します...")
            is_live = False
            await asyncio.sleep(10)


# ---- FastAPIサーバー ----
app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}


# ---- Webhook（友だち追加 → userId取得 → あなたへ通知） ----
@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    events = body.get("events", [])

    for event in events:
        # 友だち追加イベント
        if event["type"] == "follow":
            new_user_id = event["source"]["userId"]
            print(f"[LINE] 新規友だち追加: {new_user_id}")

            # あなたのLINEへ通知
            await send_line_message(
                f"👤 新規友だち追加\nUserID: {new_user_id}"
            )

    return {"status": "ok"}


async def start_web_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


# ---- メイン ----
async def main():
    await asyncio.gather(
        start_tiktok_client(),
        start_web_server(),
    )

if __name__ == "__main__":
    asyncio.run(main())
