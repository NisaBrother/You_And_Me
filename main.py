import os
import asyncio
import httpx
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
from TikTokLive.client.errors import UserOfflineError, UserNotFoundError
from fastapi import FastAPI
import uvicorn

# ---- 環境変数 ----
LINE_TOKEN = os.getenv("LINE_TOKEN")        # LINEチャネルアクセストークン
TARGET_USER = os.getenv("TARGET_USER")      # TikTok配信者ID（@なし）
MY_USER_ID = os.getenv("MY_USER_ID")        # 自分のLINE userId
PORT = int(os.getenv("PORT", 8000))         # Render が割り当てるポート

if not LINE_TOKEN or not TARGET_USER or not MY_USER_ID:
    raise ValueError("LINE_TOKEN, TARGET_USER, MY_USER_ID の環境変数を設定してください")

# ---- LINE通知関数（非同期） ----
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

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    msg = f"🔴 {TARGET_USER} さんがTikTokライブを開始しました！"
    print(msg)
    await send_line_message(MY_USER_ID, msg)

# ---- 非同期でTikTokClientを起動（オフラインでもリトライ） ----
async def start_tiktok_client():
    while True:
        try:
            print("TikTokLiveClient を起動します...")
            await client.start()
        except UserOfflineError:
            # ユーザーがオフラインのときは5秒待って再試行
            print(f"{TARGET_USER} は現在オフラインです。5秒後に再接続します...")
            await asyncio.sleep(5)
        except UserNotFoundError:
            # ユーザー名が間違っている場合はログを出して終了
            print(f"{TARGET_USER} が見つかりません。ユーザー名を確認してください。")
            break
        except Exception as e:
            # その他の例外はログを出して少し待って再接続
            print(f"TikTokLiveClient 例外: {e}")
            await asyncio.sleep(5)

# ---- FastAPIサーバー（Render 用健康チェック） ----
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
        start_tiktok_client(),
        start_web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())
