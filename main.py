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
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")  # Render が自動提供してくれる

if not LINE_TOKEN or not TARGET_USER or not MY_USER_ID:
    raise ValueError("LINE_TOKEN, TARGET_USER, MY_USER_ID の環境変数を設定してください")


# ---- LINE通知 ----
async def send_line_message(user_id, msg):
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {"to": user_id, "messages": [{"type": "text", "text": msg}]}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(url, headers=headers, json=data)
            if resp.status_code != 200:
                print(f"LINE送信エラー: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"LINE送信例外: {e}")


# ---- TikTokライブ監視 ----
client = TikTokLiveClient(unique_id=TARGET_USER)
is_live = False

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    global is_live
    if is_live:
        print("すでにライブ中として認識しています。通知しません。")
        return

    is_live = True
    msg = f"🔴 {TARGET_USER} さんがTikTokライブを開始しました！"
    print(msg)
    await send_line_message(MY_USER_ID, msg)


async def start_tiktok_client():
    global is_live
    while True:
        try:
            print(f"TikTokLiveClient を {TARGET_USER} のために起動します...")
            await client.start()

        except UserOfflineError:
            print(f"{TARGET_USER} がオフラインになりました。")
            is_live = False
            await asyncio.sleep(5)

        except UserNotFoundError:
            print(f"{TARGET_USER} が見つかりません。30秒後に再試行します...")
            await asyncio.sleep(30)

        except Exception as e:
            print(f"TikTokLiveClient 例外: {e} 10秒後に再接続します...")
            is_live = False
            await asyncio.sleep(10)


# ---- FastAPIサーバー ----
app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}


async def start_web_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


# ---- スリープ防止：自分自身の /health を叩く ----
async def keep_alive():
    if not RENDER_EXTERNAL_URL:
        print("⚠ RENDER_EXTERNAL_URL が設定されていません。Keep-Alive は無効です。")
        return

    url = f"{RENDER_EXTERNAL_URL}/health"
    print(f"[KeepAlive] URL: {url}")

    while True:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.get(url)
                print("[KeepAlive] ping sent")
        except Exception as e:
            print(f"[KeepAlive] error: {e}")

        await asyncio.sleep(600)  # 10分


# ---- メイン ----
async def main():
    await asyncio.gather(
        start_tiktok_client(),
        start_web_server(),
        keep_alive(),        # ← スリープ防止の追加
    )

if __name__ == "__main__":
    asyncio.run(main())
