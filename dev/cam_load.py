r"""לולאת מצלמה חשופה (בלי Qt, בלי זיהוי) — כדי לבדוק אם עצם הלכידה מכבידה על הקלדה בתוכנה.
  python dev\cam_load.py [שניות] [dshow|msmf] [grab]   grab = רק grab() בלי פענוח JPEG
"""
import sys
import time

import cv2

secs = float(sys.argv[1]) if len(sys.argv) > 1 else 60
api = cv2.CAP_MSMF if "msmf" in sys.argv else cv2.CAP_DSHOW
grab_only = "grab" in sys.argv
cap = cv2.VideoCapture(0, api)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
W = next((int(a[2:]) for a in sys.argv if a.startswith("w=")), 1280)
FPS = next((int(a[4:]) for a in sys.argv if a.startswith("fps=")), 0)
YUY = "yuy2" in sys.argv
if YUY:
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"YUY2"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, W)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720 if W == 1280 else 480)
if FPS:
    cap.set(cv2.CAP_PROP_FPS, FPS)
print("opened:", cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT), cap.get(cv2.CAP_PROP_FPS), flush=True)
t0, n = time.time(), 0
while time.time() - t0 < secs:
    ok = cap.grab() if grab_only else cap.read()[0]
    n += ok
print(f"frames={n} in {secs}s  ({n / secs:.1f}/s)  api={'msmf' if api == cv2.CAP_MSMF else 'dshow'} grab_only={grab_only}")
