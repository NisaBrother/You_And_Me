import os
import asyncio
import httpx
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
from TikTokLive.client.errors import UserOfflineError, UserNotFoundError
from fastapi import FastAPI
import uvicorn
from datetime import datetime, timedelta

# ---- 環境変数 ----
LINE_TOKEN = os.getenv("LINE_TOKEN")
TARGET_USER = os.getenv("TARGET_USER")
MY_USER_ID = os.getenv("MY_USER_ID")
PORT = int(os.getenv("PORT", 8000))

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


# ==================================================
#   TikTokLiveClient（再起動可能版）
# ==================================================

client = None
is_live = False
last_reset = datetime.utcnow()

def create_client():
    """TikTokLiveClient を完全に新しく作成"""
    global client
    client = TikTokLiveClient(unique_id=TARGET_USER)

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

    return client


# ---- TikTokClient起動（自動リセット付き） ----
async def start_tiktok_client():
    global client, is_live, last_reset

    create_client()

    error_count = 0

    while True:
        try:
            # ★ 30分経過したらクライアントをリセット
            if datetime.utcnow() - last_reset > timedelta(minutes=30):
                print("🟡 30分経過したため TikTokLiveClient を再起動します")
                client = create_client()
                last_reset = datetime.utcnow()
                is_live = False

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
            print(f"TikTokLiveClient 例外: {e}")
            error_count += 1

            # ★ エラーが5回続いたらリセット
            if error_count >= 5:
                print("🔴 エラー多発のため TikTokLiveClient を強制再起動します")
                client = create_client()
                last_reset = datetime.utcnow()
                is_live = False
                error_count = 0

            await asyncio.sleep(10)


# ==================================================
# FastAPIサーバー（健康チェック）
# ==================================================
app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}


async def start_web_server():
    config = uvicorn.Config(app, host="0.0.0.0", port=PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


# ---- メインタスク ----
async def main():
    await asyncio.gather(
        start_tiktok_client(),
        start_web_server()
    )


if __name__ == "__main__":
    asyncio.run(main())
