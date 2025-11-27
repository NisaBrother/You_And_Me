from TikTokLive import TikTokLiveClient
from TikTokLive.types.events import ConnectEvent
import requests
import os

TARGET_USER = os.getenv("TARGET_USER")
LINE_TOKEN = os.getenv("LINE_NOTIFY_TOKEN")

client = TikTokLiveClient(unique_id=TARGET_USER)

def send_line_message(message):
    url = "https://notify-api.line.me/api/notify"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}"
    }
    data = {
        "message": message
    }
    requests.post(url, headers=headers, data=data)

@client.on(ConnectEvent)
async def on_connect(event):
    msg = f"{TARGET_USER} がライブ配信を開始しました！"
    print(msg)
    send_line_message(msg)

if __name__ == "__main__":
    client.run()
