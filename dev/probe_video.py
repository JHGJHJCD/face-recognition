"""בדיקת מסלול "בדיקת סרטון" דרך ה-API בלי חלון: מעלה Backend + שרת, שולח קישור יוטיוב (או קובץ), ממתין לסיום ומדפיס את התוצאה.
שימוש: probe_video.py <קישור-יוטיוב | נתיב-קובץ>"""
import json
import os
import sys
import threading
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PyQt6.QtWidgets import QApplication  # noqa: E402

from webui import ytplayer  # noqa: E402,F401  (חייב לפני QApplication — QtWebEngine)
from webui.backend import Backend, start_server  # noqa: E402

app = QApplication(sys.argv)
be = Backend()
srv, url = start_server(be)
target = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def get(name):
    with urllib.request.urlopen(url + "api/" + name, timeout=30) as r:
        return json.loads(r.read().decode())


def post(name, body):
    req = urllib.request.Request(url + "api/" + name, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"http": e.code, "body": e.read().decode("utf-8", "ignore")[:400]}


def work():
    while be.engine is None and not be.load_error:
        time.sleep(0.5)
    print("engine ready; error:", be.load_error)
    if os.path.exists(target):
        be.in_main(lambda: be._video_start(target))
    else:
        print("post video/url →", post("video/url", {"url": target}))
    last = ""
    t0 = time.time()
    stop_after = float(os.environ.get("STOP_AFTER", 0))     # בדיקת עצירה: אחרי N שניות שולחים video/stop ומודדים כמה זמן עד שנעצר
    while True:
        v = get("poll")["video"]
        if stop_after and time.time() - t0 > stop_after:
            print(f"  [{time.time() - t0:5.0f}s] → video/stop", post("video/stop", {}))
            stop_after = 0
        line = f"{v['pct']}% {v['phase']}"
        if line != last:
            print(f"  [{time.time() - t0:5.0f}s] {line}")
            last = line
        if not v["running"]:
            break
        time.sleep(1)
    r = get("video")
    print("status:", r["state"]["status"])
    print("notes:", r["state"]["notes"])
    print("summary:", r["summary"])
    print("people:", [(p["name"], p["ranges"]) for p in r["people"]])
    for f in r["females"]:
        print(f"  {f['start']}–{f['end']}  {f['kind']:<5} ~{f['age']}  small={f['small']}  {f['source']}  {f['ai']}  thumb={f['thumb']}")
    app.quit()


threading.Thread(target=work, daemon=True).start()
app.exec()
