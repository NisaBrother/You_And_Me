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

is_live = False

@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    global is_live

    # すでにライブ中として認識している場合は通知しない
    if is_live:
        print("すでにライブ中として認識しています。通知しません。")
        return

    # 初回のみ通知
    is_live = True

    url = f"https://www.tiktok.com/@{TARGET_USER}/live"
    msg = f"🔴 {TARGET_USER} さんがTikTokライブを開始しました！\n{url}"

    print(msg)
    await send_line_message(MY_USER_ID, msg)


# ---- TikTokClient起動（オフライン・未検出でもリトライ） ----
async def start_tiktok_client():
    global is_live

    while True:
        try:
            print(f"TikTokLiveClient を {TARGET_USER} のために起動します...")
            await client.start()

        except UserOfflineError:
            print(f"{TARGET_USER} がオフラインになりました。")
            # ライブ終了 → 次の配信で通知できるようにリセット
            is_live = False

            await asyncio.sleep(5)

        except UserNotFoundError:
            print(f"{TARGET_USER} が見つかりません。30秒後に再試行します...")
            await asyncio.sleep(30)

        except Exception as e:
            print(f"TikTokLiveClient 例外: {e} 10秒後に再接続します...")
            # 念のためリセット（異常再接続時でも次回通知できるように）
            is_live = False

            await asyncio.sleep(10)


# ---- FastAPIサーバー（健康チェック用） ----
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
