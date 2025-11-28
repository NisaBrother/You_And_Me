import os
import asyncio
import requests
from TikTokLive import TikTokLiveClient
from TikTokLive.types.events import LiveStartEvent

# ---- 環境変数 ----
TARGET_USER = os.getenv("TARGET_USER")       # TikTok ユーザーID
LINE_TOKEN   = os.getenv("LINE_TOKEN")       # LINE Bot のチャネルアクセストークン
MY_USER_ID   = os.getenv("MY_USER_ID")       # 自分の LINE userId

if not (TARGET_USER and LINE_TOKEN and MY_USER_ID):
    raise ValueError("TARGET_USER, LINE_TOKEN, MY_USER_ID の環境変数を設定してください")

# ---- LINE 通知関数 ----
def send_line_message(message: str):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "to": MY_USER_ID,
        "messages": [{"type": "text", "text": message}]
    }
    r = requests.post("https://api.line.me/v2/bot/message/push", headers=headers, json=data)
    if r.status_code != 200:
        print(f"LINE通知エラー: {r.status_code}, {r.text}")

# ---- TikTok 監視 ----
async def main():
    client = TikTokLiveClient(unique_id=TARGET_USER)

    @client.on("live_start")
    async def on_live_start(event: LiveStartEvent):
        print(f"{TARGET_USER} の配信開始を検知！")
        send_line_message(f"{TARGET_USER} がライブ配信を開始しました！")

    print("TikTokLiveClient started")
    await client.start()

# ---- 実行 ----
if __name__ == "__main__":
    asyncio.run(main())
