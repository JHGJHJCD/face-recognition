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
EXE_ASSET = "FaceID.exe"      # קובץ ההפעלה הקטן (launcher.py) — מה שמפיצים, ומה שגרסאות 1.0–1.2 מורידות כעדכון
APP_ASSET = "app.zip"         # התוכנה עצמה כתיקייה פרוסה; מותקנת ב-%LOCALAPPDATA%\\FaceID\\apps\\<גרסה>
APP_EXE = "FaceIDApp.exe"
APPS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "FaceID", "apps")
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
    asset = next((a for a in assets if a.get("name") == APP_ASSET), None)
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


# ---------- התקנת גרסה חדשה ----------
def current_exe():
    return sys.executable if getattr(sys, "frozen", False) else None


def cleanup_old(keep_version):
    """מוחק גרסאות קודמות ושאריות הורדה (הגרסה הרצה נעולה ממילא עד שתיסגר)."""
    if not current_exe() or not os.path.isdir(APPS):
        return
    import shutil
    for name in os.listdir(APPS):
        if name not in (keep_version, "current.txt"):
            full = os.path.join(APPS, name)
            shutil.rmtree(full, ignore_errors=True) if os.path.isdir(full) else _rm(full)


def install_update(info, progress_cb=None):
    """מוריד את app.zip, פורס ל-apps\\<גרסה>, מעדכן current.txt. מחזיר נתיב ל-EXE החדש. progress_cb(אחוז)."""
    import shutil
    os.makedirs(APPS, exist_ok=True)
    ver = info["version"]
    tmp_zip, tmp_dir, final = os.path.join(APPS, "download.zip"), os.path.join(APPS, ver + ".tmp"), os.path.join(APPS, ver)
    download(info["url"], tmp_zip, lambda p, d, t: progress_cb and progress_cb(min(p, 95)), timeout=60)
    shutil.rmtree(tmp_dir, ignore_errors=True)
    with zipfile.ZipFile(tmp_zip) as z:
        z.extractall(tmp_dir)
    shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp_dir, final)
    _rm(tmp_zip)
    exe = os.path.join(final, APP_EXE)
    if not os.path.exists(exe):
        raise IOError("קובץ ההתקנה פגום (חסר " + APP_EXE + ")")
    with open(os.path.join(APPS, "current.txt"), "w", encoding="utf-8") as f:
        f.write(ver)
    return exe


def relaunch(exe, home):
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI") and k not in ("_MEIPASS2", "FACEID_FAKE_VERSION")}
    subprocess.Popen([exe, "--home", home], close_fds=True, env=env, cwd=os.path.dirname(exe))


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
