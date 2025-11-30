"""
render_tiktok_supervisor.py

Supervisor style single-file app for Render that:
- Runs a worker subprocess that runs the TikTokLiveClient (isolated process)
- Runs a web server (uvicorn) as a subprocess serving /health for Render health checks
- Monitors the worker via a heartbeat file and restarts it when it dies or hangs
- Logs clearly to stdout so Render's log UI shows activity

Usage on Render: set the service start command to:
    python render_tiktok_supervisor.py

Environment variables required:
- LINE_TOKEN, TARGET_USER, MY_USER_ID
- (optional) PORT (default 8000)

Notes:
- This file intentionally launches subprocesses using the same Python interpreter
  so that dependency environment is shared.
- The worker writes a heartbeat file every HEARTBEAT_INTERVAL seconds. The
  supervisor treats the worker as stuck if that file is not updated within
  HEARTBEAT_TIMEOUT seconds and will restart it.

"""

import os
import sys
import time
import json
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

# Constants
HEARTBEAT_FILENAME = "/tmp/tiktok_worker_heartbeat"
HEARTBEAT_INTERVAL = 20          # worker updates heartbeat every N seconds
HEARTBEAT_TIMEOUT = 90           # supervisor treats worker as dead if no update within this
WORKER_RESTART_BACKOFF = 5       # seconds to wait before restarting a failed worker
UVICORN_RESTART_BACKOFF = 5
CHECK_INTERVAL = 10

# Environment variables
LINE_TOKEN = os.getenv("LINE_TOKEN")
TARGET_USER = os.getenv("TARGET_USER")
MY_USER_ID = os.getenv("MY_USER_ID")
PORT = int(os.getenv("PORT", "8000"))

if not LINE_TOKEN or not TARGET_USER or not MY_USER_ID:
    # If we're running as the worker subprocess, allow the worker to check this itself.
    # But for the supervisor we require them to be set so mistakes are visible early.
    if __name__ == "__main__":
        raise ValueError("LINE_TOKEN, TARGET_USER, MY_USER_ID の環境変数を設定してください")


def now_str():
    return datetime.utcnow().isoformat() + "Z"


def log(msg: str):
    print(f"[{now_str()}] {msg}", flush=True)


# ------------------------- Supervisor -------------------------
async def supervisor_loop():
    """Launch and monitor two subprocesses:
      - web server: uvicorn serving this module's `app`
      - worker: the worker mode of this same script (python main.py worker)
    """
    python = sys.executable
    script = Path(__file__).resolve()

    # Build commands
    uvicorn_cmd = [python, "-m", "uvicorn", f"{script.stem}:app", "--host", "0.0.0.0", "--port", str(PORT), "--log-level", "info"]
    worker_cmd = [python, str(script), "worker"]

    web_proc = None
    worker_proc = None

    try:
        while True:
            # ensure web server
            if web_proc is None or web_proc.poll() is not None:
                if web_proc is not None:
                    log(f"web server exited with code {web_proc.returncode}. Restarting in {UVICORN_RESTART_BACKOFF}s")
                    await asyncio.sleep(UVICORN_RESTART_BACKOFF)
                log("Starting uvicorn web server subprocess...")
                web_proc = subprocess.Popen(uvicorn_cmd)
                log(f"uvicorn pid={web_proc.pid}")

            # ensure worker
            if worker_proc is None or worker_proc.poll() is not None:
                if worker_proc is not None:
                    log(f"worker exited with code {worker_proc.returncode}. Restarting in {WORKER_RESTART_BACKOFF}s")
                    await asyncio.sleep(WORKER_RESTART_BACKOFF)
                log("Starting worker subprocess...")
                # ensure heartbeat file is cleared
                try:
                    Path(HEARTBEAT_FILENAME).unlink(missing_ok=True)
                except Exception:
                    pass
                worker_proc = subprocess.Popen(worker_cmd)
                log(f"worker pid={worker_proc.pid}")

            # monitor heartbeat
            await asyncio.sleep(CHECK_INTERVAL)
            hb_path = Path(HEARTBEAT_FILENAME)
            if not hb_path.exists():
                log("No heartbeat file found yet from worker.")
                continue
            try:
                mtime = datetime.utcfromtimestamp(hb_path.stat().st_mtime)
            except Exception as e:
                log(f"failed to stat heartbeat file: {e}")
                continue

            age = (datetime.utcnow() - mtime).total_seconds()
            if age > HEARTBEAT_TIMEOUT:
                log(f"Heartbeat stale (age={age:.1f}s). Killing worker pid={worker_proc.pid} and restarting.")
                try:
                    worker_proc.kill()
                except Exception as e:
                    log(f"failed to kill worker: {e}")
                # next loop will restart
                worker_proc = None

    except asyncio.CancelledError:
        log("supervisor_loop cancelled")
    finally:
        log("Supervisor shutting down, terminating child processes...")
        if worker_proc and worker_proc.poll() is None:
            worker_proc.terminate()
        if web_proc and web_proc.poll() is None:
            web_proc.terminate()


# ------------------------- Worker -------------------------
# The worker code is intentionally separated and executed only when the script
# is invoked with the 'worker' argument. This isolates crashes/memory growth.

WORKER_SCRIPT = r"""
# This code runs inside the worker subprocess.
# It provides similar logic to your original implementation but adds a heartbeat file
# and robust exception handling / automatic reconnect.

import os
import asyncio
import httpx
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent
from TikTokLive.client.errors import UserOfflineError, UserNotFoundError
import sys
from pathlib import Path
from datetime import datetime

LINE_TOKEN = os.getenv('LINE_TOKEN')
TARGET_USER = os.getenv('TARGET_USER')
MY_USER_ID = os.getenv('MY_USER_ID')
PORT = int(os.getenv('PORT', '8000'))

HEARTBEAT_FILENAME = '{}' 
HEARTBEAT_INTERVAL = {}

if not LINE_TOKEN or not TARGET_USER or not MY_USER_ID:
    raise ValueError('LINE_TOKEN, TARGET_USER, MY_USER_ID の環境変数を設定してください')

is_live = False

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


async def start_tiktok_client():
    global is_live
    while True:
        try:
            print(f"[worker] TikTokLiveClient を {TARGET_USER} のために起動します...")
            await client.start()
        except UserOfflineError:
            print(f"[worker] {TARGET_USER} がオフラインになりました。")
            is_live = False
            await asyncio.sleep(5)
        except UserNotFoundError:
            print(f"[worker] {TARGET_USER} が見つかりません。30秒後に再試行します...")
            await asyncio.sleep(30)
        except Exception as e:
            print(f"[worker] TikTokLiveClient 例外: {e} 10秒後に再接続します...")
            is_live = False
            await asyncio.sleep(10)


async def heartbeat_loop():
    hb_path = Path(HEARTBEAT_FILENAME)
    while True:
        try:
            hb_path.write_text(datetime.utcnow().isoformat())
        except Exception as e:
            print(f"[worker] heartbeat write error: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def main_worker():
    await asyncio.gather(start_tiktok_client(), heartbeat_loop())

if __name__ == '__main__':
    try:
        asyncio.run(main_worker())
    except KeyboardInterrupt:
        print('[worker] KeyboardInterrupt; exiting')
    except Exception as e:
        print(f'[worker] fatal exception: {e}')
""".format(HEARTBEAT_FILENAME, HEARTBEAT_INTERVAL)


# ------------------------- Web server (FastAPI) -------------------------
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}


# ------------------------- Entrypoint -------------------------
def is_worker_mode():
    return len(sys.argv) > 1 and sys.argv[1] == "worker"


def run_worker_mode():
    # Execute worker script as a separate interpreter. This keeps the worker
    # isolated and allows the supervisor to restart it cleanly.
    python = sys.executable
    # Write the worker script to a temp file and execute it. Using a temp file
    # ensures the worker has the correct content even if the main file is on a
    # read-only FS.
    worker_path = Path('/tmp') / f"{Path(__file__).stem}_worker.py"
    worker_path.write_text(WORKER_SCRIPT)
    os.execv(python, [python, str(worker_path)])


async def main():
    if is_worker_mode():
        run_worker_mode()
        return

    log("Supervisor starting")
    try:
        await supervisor_loop()
    except KeyboardInterrupt:
        log("Supervisor received KeyboardInterrupt")


if __name__ == '__main__':
    if is_worker_mode():
        run_worker_mode()
    else:
        try:
            asyncio.run(main())
        except Exception as e:
            log(f"fatal supervisor error: {e}")
            raise
