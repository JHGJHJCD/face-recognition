"""נגן יוטיוב בתוך חלון של התוכנה — "בדיקה בתוך יוטיוב" בלי הורדה (22/9/2026).

למה כך: נטפרי חוסם את ה-API שכלי הורדה משתמשים בו (HTTP 418). דף הצפייה המלא של יוטיוב ב-QtWebEngine לא מתחיל לנגן
(readyState 0, ואחרי דקה מפנה להתחברות) — אבל **הנגן המוטמע** (iframe API) בדף מקומי משלנו מנגן מצוין (נבדק: dev/probe_embed.py).
הפריים נלקח ב-view.grab() (צילום החלון, הנגן ממלא אותו בלי פקדים), והזמן בסרטון מ-player.getCurrentTime().
הפריימים נכנסים לתור ש-YouTubeWorker (core/jobs.py) מנתח בחוט נפרד. ניגון מושתק במהירות 2. חייב לרוץ בחוט Qt הראשי.
"""
import json
import queue

import cv2
import numpy as np
from PyQt6.QtCore import QBuffer, QIODevice, QObject, Qt, QTimer, QUrl
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView

RATE = 2            # מהירות ניגון
GRAB_MS = 500       # כל כמה מילישניות (זמן אמת) לוקחים פריים ⇒ עם RATE=2 זה כל שנייה בסרטון
START_TIMEOUT = 30  # שניות עד שמוותרים אם הווידאו לא התחיל

ERRORS = {2: "קישור לא תקין", 5: "הנגן לא הצליח להריץ את הסרטון", 100: "הסרטון לא נמצא או פרטי",
          101: "בעל הסרטון לא מאפשר להריץ אותו מחוץ ליוטיוב", 150: "בעל הסרטון לא מאפשר להריץ אותו מחוץ ליוטיוב"}

HTML = """<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#000;overflow:hidden}#p{position:fixed;inset:0}</style></head>
<body><div id="p"></div><script>
window.S = {state: 'init', t: 0, d: 0, err: null};
var tag = document.createElement('script'); tag.src = 'https://www.youtube.com/iframe_api'; tag.onerror = () => { S.state = 'error'; S.err = 'api'; };
document.head.appendChild(tag);
var player;
function onYouTubeIframeAPIReady() {
  player = new YT.Player('p', {videoId: '%VID%', playerVars: {autoplay: 1, mute: 1, controls: 0, rel: 0, playsinline: 1, iv_load_policy: 3, disablekb: 1, fs: 0},
    events: {onReady: e => { S.state = 'ready'; e.target.mute(); e.target.setPlaybackRate(%RATE%); e.target.playVideo(); },
             onStateChange: e => { S.state = e.data === 0 ? 'ended' : 'st' + e.data; if (e.data === 1) try { player.setPlaybackRate(%RATE%); } catch (x) {} },
             onError: e => { S.state = 'error'; S.err = e.data; }}});
}
setInterval(() => { if (player && player.getCurrentTime) { try { S.t = player.getCurrentTime(); S.d = player.getDuration(); } catch (e) {} } }, 200);
</script></body></html>"""


class YouTubePlayer(QObject):
    """פותח את הסרטון בחלון, ומזרים (זמן, אורך, frame BGR) ל-frames. בסיום: (None, אורך, "ended") או (None, 0, "error:…")."""

    def __init__(self, url, frames: queue.Queue, parent=None):
        super().__init__(parent)
        self.frames = frames
        self.done = False
        vid = url.split("v=")[-1][:11]
        self.view = QWebEngineView()
        self.view.setWindowTitle("התוכנה צופה בסרטון — אפשר למזער, לא לסגור")
        self.view.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.view.resize(640, 360)
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        self.view.page().setAudioMuted(True)
        # baseUrl חובה: בלי מקור (origin) יוטיוב מחזיר "שגיאה 153" למוטמע
        self.view.setHtml(HTML.replace("%VID%", vid).replace("%RATE%", str(RATE)), QUrl("http://127.0.0.1/"))
        self.view.show()
        self.waited = 0.0
        self.last_t = -1.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(GRAB_MS)

    def _tick(self):
        if not self.done:
            self.view.page().runJavaScript("JSON.stringify(window.S)", self._got)

    def _got(self, raw):
        if self.done:
            return
        try:
            d = json.loads(raw) if raw else {}
        except ValueError:
            d = {}
        state, t = d.get("state", ""), float(d.get("t") or 0)
        if state == "ended":
            self._finish((None, float(d.get("d") or t), "ended"))
        elif state == "error":
            self._finish((None, 0.0, "error:" + ERRORS.get(d.get("err"), "שגיאה " + str(d.get("err")))))
        elif state == "st1" and t > self.last_t:       # מנגן והזמן מתקדם
            self.waited, self.last_t = 0.0, t
            img = self._grab()
            if img is not None:
                try:
                    self.frames.put_nowait((t, float(d.get("d") or 0), img))
                except queue.Full:      # המנתח מפגר — מוותרים על הפריים הזה
                    pass
        else:
            self.waited += GRAB_MS / 1000
            if state == "init" and self.waited > 12 and (img := self._grab()) is not None and img.mean() > 200:
                self._finish((None, 0.0, "error:נטפרי חוסם את הסרטון הזה"))       # דף לבן במקום נגן = דף החסימה
            elif self.waited > START_TIMEOUT:
                self._finish((None, 0.0, "error:הסרטון לא מתנגן — ייתכן שהקישור חסום בנטפרי"))

    def _grab(self):
        img = self.view.grab().toImage()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "JPG", 90)
        arr = cv2.imdecode(np.frombuffer(bytes(buf.data()), np.uint8), cv2.IMREAD_COLOR)
        return arr if arr is not None and arr.mean() > 6 else None      # מסך שחור = עוד לא צויר

    def _finish(self, item):
        print("ytplayer:", item[2], flush=True)
        self.done = True
        self.timer.stop()
        self.frames.put(item)
        self.close()

    def close(self):
        self.done = True
        self.timer.stop()
        try:
            self.view.page().setAudioMuted(True)
            self.view.setHtml("")
            self.view.close()
            self.view.deleteLater()
        except RuntimeError:
            pass
