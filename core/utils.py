"""כלי עזר: קריאת קבצים בנתיבים עבריים, המרות תמונה, נתיבי הפרויקט."""
import ctypes
import os
import sys

import cv2
import numpy as np

if "--home" in sys.argv[:-1]:     # הופעל דרך FaceID.exe הקטן: הנתונים והמודלים ליד קובץ ההפעלה, לא בתיקיית ההתקנה
    BASE_DIR = sys.argv[sys.argv.index("--home") + 1]
elif getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
DATA_DIR = os.path.join(BASE_DIR, "data")
UNKNOWN_DIR = os.path.join(DATA_DIR, "unknown")
os.makedirs(UNKNOWN_DIR, exist_ok=True)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff", ".jfif"}
VIDEO_EXT = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".m4v", ".webm", ".3gp", ".mpg", ".mpeg"}


def _jpeg_max_side(data):
    """הצלע הארוכה של JPEG מתוך הכותרת בלבד (סימון SOF), בלי לפענח. 0 = לא JPEG / לא נמצא."""
    n = len(data)
    if n < 4 or data[0] != 0xFF or data[1] != 0xD8:
        return 0
    i = 2
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        m = int(data[i + 1])
        if m in (0xC0, 0xC1, 0xC2):
            return max(int(data[i + 5]) << 8 | int(data[i + 6]), int(data[i + 7]) << 8 | int(data[i + 8]))
        if m == 0xD8 or 0xD0 <= m <= 0xD7 or m == 0x01 or m == 0xFF:
            i += 2 if m != 0xFF else 1
            continue
        i += 2 + (int(data[i + 2]) << 8 | int(data[i + 3]))
    return 0


def imread(path, max_side=None):
    """cv2.imread לא קורא נתיבים בעברית ב-Windows — קוראים דרך bytes."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        flag = cv2.IMREAD_COLOR
        if max_side:   # JPEG ענק: פענוח ישר בחצי/רבע גודל — נמדד 254ms → 122ms לתמונת 5000 פיקסל
            side = _jpeg_max_side(data)
            if side >= max_side * 4:
                flag = cv2.IMREAD_REDUCED_COLOR_4
            elif side >= max_side * 2:
                flag = cv2.IMREAD_REDUCED_COLOR_2
        img = cv2.imdecode(data, flag)
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


_T0 = None


def mark(name):
    """יומן זמני עלייה (data/startup.log) — למדידת מהירות ההפעלה; נכתב מחדש בכל הפעלה."""
    global _T0
    import time
    try:
        first = _T0 is None
        if first:
            _T0 = time.time()
        with open(os.path.join(DATA_DIR, "startup.log"), "w" if first else "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} +{time.time() - _T0:5.1f}s {name}\n")
    except OSError:
        pass
