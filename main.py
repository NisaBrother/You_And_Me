from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
import requests
import os
import asyncio

LINE_TOKEN = os.getenv("LINE_TOKEN")
TARGET_USER = os.getenv("yuumi_takaki05")  # 監視するTikTokユーザーID

def send_line(msg: str):
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {LINE_TOKEN}"}
    data = {"message": msg}
    requests.post(url, headers=headers, data=data)

# ---- TikTokLive クライアント ----
client = TikTokLiveClient(unique_id=TARGET_USER)

# ---- 接続イベント ----
@client.on(ConnectEvent)
async def on_connect(event: ConnectEvent):
    user_name = TARGET_USER  # 今回は固定ユーザーIDを表示
    msg = f"{user_name} さんが TikTokライブを開始しました！"
    print(msg)
    send_line(msg)

# ---- TikTok に常時接続 ----
async def main():
    while True:
        try:
            await client.start()
        except Exception as e:
            print("Error:", e)
            send_line(f"⚠ エラー発生: {e}")
            await asyncio.sleep(5)  # 5秒後リトライ

if __name__ == "__main__":
    asyncio.run(main())

