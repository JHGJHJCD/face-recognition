"""כלי עזר: קריאת קבצים בנתיבים עבריים, המרות תמונה, נתיבי הפרויקט."""
import ctypes
import os
import sys

import cv2
import numpy as np

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DATA_DIR = os.path.join(BASE_DIR, "data")
UNKNOWN_DIR = os.path.join(DATA_DIR, "unknown")
os.makedirs(UNKNOWN_DIR, exist_ok=True)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".jfif"}
VIDEO_EXT = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".m4v", ".webm", ".3gp", ".mpg", ".mpeg"}


def imread(path, max_side=None):
    """cv2.imread לא קורא נתיבים בעברית ב-Windows — קוראים דרך bytes."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None
    if img is None:
        return None
    if max_side and max(img.shape[:2]) > max_side:
        s = max_side / max(img.shape[:2])
        img = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    return img


def imwrite(path, img, quality=90):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if ok:
        buf.tofile(path)
    return ok


def jpg_bytes(img, quality=88):
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""


def short_path(path):
    """נתיב 8.3 (ASCII) — VideoCapture של OpenCV נכשל על נתיב עברי."""
    try:
        path.encode("ascii")
        return path
    except UnicodeEncodeError:
        pass
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024)
    return buf.value if n else path


def crop_square(img, bbox, margin=0.35, size=160):
    """חיתוך ריבועי סביב פנים לתמונה ממוזערת."""
    h, w = img.shape[:2]
    x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    half = max(x2 - x1, y2 - y1) * (1 + margin) / 2
    xa, ya = int(max(0, cx - half)), int(max(0, cy - half))
    xb, yb = int(min(w, cx + half)), int(min(h, cy + half))
    crop = img[ya:yb, xa:xb]
    if crop.size == 0:
        return np.zeros((size, size, 3), np.uint8)
    return cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA)


def fmt_time(sec):
    sec = int(sec)
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
