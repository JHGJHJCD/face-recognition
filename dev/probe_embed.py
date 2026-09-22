"""בדיקת נגן יוטיוב מוטמע (iframe embed) בתוך QWebEngineView: האם מנגן, האם grab() של החלון מחזיר פריימים אמיתיים, ומה הזמן בסרטון.
שימוש: probe_embed.py [מזהה-סרטון] [שניות]"""
import json
import os
import sys
import time

import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
from PyQt6.QtCore import QBuffer, QIODevice, QTimer, QUrl  # noqa: E402
from PyQt6.QtWebEngineCore import QWebEngineSettings  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

vid = sys.argv[1] if len(sys.argv) > 1 else "jNQXAC9IVRw"
secs = int(sys.argv[2]) if len(sys.argv) > 2 else 30
HTML = """<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#000;overflow:hidden}
#p{position:fixed;inset:0}</style></head><body><div id="p"></div>
<script>
window.S = {state: 'init', t: 0, d: 0, err: null, rate: 0};
var tag = document.createElement('script'); tag.src = 'https://www.youtube.com/iframe_api'; document.head.appendChild(tag);
var player;
function onYouTubeIframeAPIReady() {
  player = new YT.Player('p', {videoId: '%VID%', playerVars: {autoplay: 1, mute: 1, controls: 0, rel: 0, modestbranding: 1, playsinline: 1, iv_load_policy: 3, disablekb: 1},
    events: {onReady: e => { S.state = 'ready'; e.target.mute(); e.target.setPlaybackRate(2); e.target.playVideo(); },
             onStateChange: e => { S.state = 'st' + e.data; if (e.data === 0) S.state = 'ended'; },
             onError: e => { S.state = 'error'; S.err = e.data; }}});
}
setInterval(() => { if (player && player.getCurrentTime) { try { S.t = player.getCurrentTime(); S.d = player.getDuration(); S.rate = player.getPlaybackRate(); } catch (e) {} } }, 250);
</script></body></html>""".replace("%VID%", vid)

app = QApplication(sys.argv)
view = QWebEngineView()
view.resize(640, 360)
view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
view.page().setAudioMuted(True)
view.setHtml(HTML, QUrl("http://127.0.0.1/"))
view.show()
t0 = time.time()
n = [0]


def tick():
    def got(raw):
        d = json.loads(raw) if raw else {}
        img = view.grab().toImage()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "JPG", 85)
        arr = cv2.imdecode(np.frombuffer(bytes(buf.data()), np.uint8), cv2.IMREAD_COLOR)
        mean = float(arr.mean()) if arr is not None else -1
        if mean > 8:
            n[0] += 1
        print(f"[{time.time() - t0:4.1f}s] {d}  grab mean={mean:.1f} size={arr.shape[1] if arr is not None else 0}x{arr.shape[0] if arr is not None else 0}")
    view.page().runJavaScript("JSON.stringify(window.S)", got)


tm = QTimer()
tm.timeout.connect(tick)
tm.start(1000)


def stop():
    print("non-black grabs:", n[0])
    app.quit()


QTimer.singleShot(secs * 1000, stop)
app.exec()
