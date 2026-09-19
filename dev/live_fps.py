"""מודד את קצב הזיהוי החי בפועל (בלי חלון): 8 שניות מצלמה, מדפיס תמונות-לשנייה וכמה ניתוחי-זהות רצו."""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PyQt6.QtCore import QCoreApplication, Qt, QTimer  # noqa: E402

from core.db import Database, Settings  # noqa: E402
from core.engine import FaceEngine  # noqa: E402
from core.live import LiveWorker  # noqa: E402

app = QCoreApplication(sys.argv)
eng = FaceEngine()
st = Settings()
st["ai_enabled"] = False
w = LiveWorker(eng, Database(eng.rec_name), st, None)
frames, faces, titles = [], [], set()


def on_frame(frame, labels, fps):
    frames.append(time.time())
    faces.append(len(labels))
    titles.update(lb["state"] for lb in labels)


w.frame_ready.connect(on_frame, Qt.ConnectionType.DirectConnection)
w.failed.connect(lambda m: (print("camera failed:", m.encode("ascii", "replace")), app.quit()))
w.start()


def done():
    w.stop()
    if len(frames) > 10:
        span = frames[-1] - frames[5]
        print("fps %.1f over %.1fs, avg faces %.1f, states %s" % ((len(frames) - 6) / span, span, sum(faces) / len(faces), sorted(titles)))
    app.quit()


QTimer.singleShot(10000, done)
app.exec()
