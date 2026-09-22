"""בדיקת נגן היוטיוב לבד (webui/ytplayer.py): פותח את הסרטון, מדפיס כל שנייה מה הנגן מדווח, וכמה פריימים הגיעו.
שימוש: probe_player.py [קישור] [שניות]"""
import json
import os
import queue
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from webui import ytplayer  # noqa: E402

url = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=jNQXAC9IVRw"
secs = int(sys.argv[2]) if len(sys.argv) > 2 else 40
app = QApplication(sys.argv)
q = queue.Queue()
pl = ytplayer.YouTubePlayer(url, q)
orig = pl._got
t0 = time.time()
n = [0]
last = [""]


def got(raw):
    try:
        d = json.loads(raw) if raw else {"state": "?", "raw": str(raw)[:80]}
    except ValueError:
        d = {"state": "bad", "raw": str(raw)[:80]}
    d.pop("img", None)
    if d.get("state") == "frame":
        n[0] += 1
    line = json.dumps(d, ensure_ascii=False)
    if line != last[0] or d.get("state") == "frame" and n[0] % 10 == 0:
        print(f"[{time.time() - t0:4.1f}s] {line}  frames={n[0]}  url={pl.view.url().toString()[:60]}")
        last[0] = line
    orig(raw)


pl._got = got


def stop():
    print("frames total:", n[0], "queue:", q.qsize(), "done:", pl.done)
    pl.close()
    app.quit()


DIAG = """(() => { const v = document.querySelector('video'); const ms = c => MediaSource.isTypeSupported(c);
  return JSON.stringify({h264: ms('video/mp4; codecs="avc1.42E01E"'), vp9: ms('video/webm; codecs="vp9"'), av1: ms('video/mp4; codecs="av01.0.05M.08"'),
    opus: ms('audio/webm; codecs="opus"'), aac: ms('audio/mp4; codecs="mp4a.40.2"'), verr: v && v.error && v.error.code, net: v && v.networkState,
    src: v && (v.currentSrc || '').slice(0, 40), play: (window.ytInitialPlayerResponse || {}).playabilityStatus,
    text: document.body.innerText.replace(/[ \n\t]+/g, ' ').slice(0, 300)}); })()"""
QTimer.singleShot(7000, lambda: pl.view.page().runJavaScript(DIAG, lambda r: print("DIAG", r)))
NET = """JSON.stringify(performance.getEntriesByType('resource').filter(e => /googlevideo|youtubei|videoplayback/.test(e.name))
  .map(e => [e.name.replace(/^https?:\/\/([^/]+)\/([^?]*).*$/, '$1/$2'), e.transferSize, Math.round(e.duration)]).slice(0, 12))"""
QTimer.singleShot(11000, lambda: pl.view.page().runJavaScript(NET, lambda r: print("NET", r)))
QTimer.singleShot(secs * 1000, stop)
app.exec()
