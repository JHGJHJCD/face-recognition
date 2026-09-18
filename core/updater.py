"""עדכון אוטומטי מגיטהאב + הורדת המודלים בהפעלה ראשונה (ספרייה סטנדרטית בלבד).

  Release רגיל:   תג vX.Y  + FaceID.exe        → העדכון מוריד, מחליף את ה-EXE הרץ ומפעיל מחדש (כמו במנהל חלוקה).
  Release מודלים: תג models-v1 + models.zip    → נפרד מה-EXE (‏~380MB, לא משתנה) — יורד פעם אחת לתיקיית models/ ליד ה-EXE.
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile

REPO = "JHGJHJCD/face-recognition"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
EXE_ASSET = "FaceID.exe"
MODELS_TAG = "models-v1"
MODELS_URL = f"https://github.com/{REPO}/releases/download/{MODELS_TAG}/models.zip"
MODEL_FILES = ["det_10g.onnx", "glintr100.onnx", "fairface.onnx", "emotion.onnx", "MiniFASNetV2.onnx", "MiniFASNetV1SE.onnx"]
_UA = "FaceID-Updater"
_DOWNLOAD_NAME = "update_download.exe"
_ETAGS = {}


def parse_version(s):
    parts = []
    for p in (s or "").strip().lstrip("vV").split("."):
        d = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(d) if d else 0)
    return tuple(parts) or (0,)


def is_newer(remote, local):
    r, l = parse_version(remote), parse_version(local)
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


def _ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return ssl.create_default_context()


def _get_json(url, timeout=10):
    """GET עם If-None-Match — תשובת 304 לא נספרת במכסת 60 בקשות/שעה של גיטהאב."""
    headers = {"User-Agent": _UA, "Accept": "application/vnd.github+json"}
    cached = _ETAGS.get(url)
    if cached:
        headers["If-None-Match"] = cached[0]
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            etag = resp.headers.get("ETag") or ""
    except urllib.error.HTTPError as e:
        if e.code == 304 and cached:
            return cached[1]
        raise
    if etag:
        _ETAGS[url] = (etag, data)
    return data


def check_latest(timeout=10):
    """{version, tag, url, size, notes} של ה-Release האחרון, או None אם אין בו EXE. זורק בשגיאת רשת."""
    data = _get_json(API_LATEST, timeout)
    tag = data.get("tag_name") or ""
    assets = data.get("assets") or []
    asset = next((a for a in assets if a.get("name") == EXE_ASSET), None) or \
        next((a for a in assets if str(a.get("name", "")).lower().endswith(".exe")), None)
    if asset is None:
        return None
    return {"version": tag.lstrip("vV"), "tag": tag, "url": asset.get("browser_download_url"),
            "size": int(asset.get("size") or 0), "notes": data.get("body") or ""}


def download(url, dest, progress_cb=None, cancel_cb=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout, context=_ctx()) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest, "wb") as f:
            while True:
                if cancel_cb and cancel_cb():
                    f.close()
                    _rm(dest)
                    raise InterruptedError("בוטל")
                chunk = resp.read(1 << 18)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(min(100, int(done * 100 / total)), done, total)
    if total and os.path.getsize(dest) != total:
        _rm(dest)
        raise IOError("ההורדה לא הושלמה במלואה — נסה שוב")
    return dest


def _rm(p):
    try:
        os.remove(p)
    except OSError:
        pass


# ---------- EXE ----------
def current_exe():
    return sys.executable if getattr(sys, "frozen", False) else None


def download_target():
    exe = current_exe()
    return os.path.join(os.path.dirname(exe) if exe else os.getcwd(), _DOWNLOAD_NAME)


def cleanup_old():
    exe = current_exe()
    if exe:
        for stale in (exe + ".old", download_target()):
            if os.path.exists(stale):
                _rm(stale)


_PYI_ENV_VARS = ("_MEIPASS2", "_PYI_ARCHIVE_FILE", "_PYI_APPLICATION_HOME_DIR", "_PYI_PARENT_PID", "_PYI_ONEFILE_TEMPDIR",
                 "_PYI_SPLASH_IPC", "_PYI_LINK_TARGET")


def apply_update(downloaded_path):
    """מחליף את ה-EXE הרץ בקובץ שהורד ומפעיל מחדש. None = הצלחה (על הקורא לצאת), אחרת מחרוזת שגיאה."""
    exe = current_exe()
    if not exe:
        return "עדכון אוטומטי זמין רק בגרסת התוכנה (EXE)."
    if not (downloaded_path and os.path.exists(downloaded_path)):
        return "קובץ העדכון לא נמצא."
    old = exe + ".old"
    try:
        _rm(old)
        os.replace(exe, old)
        os.replace(downloaded_path, exe)
    except OSError as e:
        if not os.path.exists(exe) and os.path.exists(old):
            os.replace(old, exe)
        return f"לא ניתן להחליף את קובץ התוכנה: {e}"
    env = {k: v for k, v in os.environ.items() if k not in _PYI_ENV_VARS and k != "FACEID_FAKE_VERSION"}   # אחרת ה-EXE החדש משתמש ב-_MEI של הישן ומת
    try:
        subprocess.Popen([exe], close_fds=True, env=env)
    except OSError as e:
        return f"העדכון הותקן, אך ההפעלה מחדש נכשלה. הפעל את התוכנה ידנית.\n({e})"
    return None


# ---------- מודלים ----------
def models_missing(models_dir):
    return [f for f in MODEL_FILES if not os.path.exists(os.path.join(models_dir, f))]


def fetch_models(models_dir, progress_cb=None):
    """מוריד models.zip ופורס לתיקיית המודלים. progress_cb(אחוז, הודעה)."""
    os.makedirs(models_dir, exist_ok=True)
    tmp = os.path.join(models_dir, "models.zip.part")
    download(MODELS_URL, tmp, lambda p, d, t: progress_cb and progress_cb(p, f"מוריד מודלים… {d // 1048576} / {t // 1048576} MB"), timeout=60)
    if progress_cb:
        progress_cb(100, "פורס קבצים…")
    with zipfile.ZipFile(tmp) as z:
        for name in z.namelist():
            base = os.path.basename(name)
            if base in MODEL_FILES:
                with z.open(name) as src, open(os.path.join(models_dir, base), "wb") as dst:
                    while True:
                        chunk = src.read(1 << 20)
                        if not chunk:
                            break
                        dst.write(chunk)
    _rm(tmp)
    missing = models_missing(models_dir)
    if missing:
        raise IOError("חסרים מודלים גם אחרי ההורדה: " + ", ".join(missing))
