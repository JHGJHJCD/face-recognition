"""FaceID.exe — קובץ ההפעלה הקטן (זה הקובץ שמפיצים).

למה: EXE יחיד של 250MB נפרס מחדש לתיקייה זמנית בכל הפעלה — נמדד 78 שניות עד שהתוכנה בכלל מתחילה (19/9/2026).
לכן התוכנה עצמה מותקנת פעם אחת ב-%LOCALAPPDATA%\\FaceID\\apps\\<גרסה>\\ (תיקייה פרוסה, עולה מיד), והקובץ הזה רק מפעיל אותה.
בהפעלה ראשונה (או אם ההתקנה נמחקה) הוא מוריד את app.zip מה-Release האחרון בגיטהאב ומציג התקדמות.
הנתונים (data\\) והמודלים (models\\) נשארים ליד הקובץ הזה — מועברים לתוכנה ב---home.
"""
import json
import os
import shutil
import ssl
import subprocess
import sys
import threading
import urllib.request
import zipfile

REPO = "JHGJHJCD/face-recognition"
APP_EXE = "FaceIDApp.exe"
HOME = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
APPS = os.path.join(os.environ.get("LOCALAPPDATA", HOME), "FaceID", "apps")
_PYI = ("_MEIPASS2", "_PYI_ARCHIVE_FILE", "_PYI_APPLICATION_HOME_DIR", "_PYI_PARENT_PID", "_PYI_ONEFILE_TEMPDIR", "_PYI_SPLASH_IPC", "_PYI_LINK_TARGET")


def installed():
    try:
        with open(os.path.join(APPS, "current.txt"), encoding="utf-8-sig") as f:
            exe = os.path.join(APPS, f.read().strip(), APP_EXE)
        return exe if os.path.exists(exe) else None
    except OSError:
        return None


def run(exe):
    env = {k: v for k, v in os.environ.items() if k not in _PYI}
    subprocess.Popen([exe, "--home", HOME] + sys.argv[1:], env=env, close_fds=True, cwd=os.path.dirname(exe))


def _ctx():
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:
        return ssl.create_default_context()


def install(progress):
    """מוריד ומתקין את הגרסה האחרונה. progress(אחוז או None, טקסט). מחזיר נתיב ל-EXE המותקן."""
    progress(None, "בודק מהי הגרסה האחרונה…")
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest", headers={"User-Agent": "FaceID-Launcher"})
    with urllib.request.urlopen(req, timeout=20, context=_ctx()) as r:
        rel = json.loads(r.read().decode())
    asset = next((a for a in rel.get("assets", []) if a.get("name") == "app.zip"), None)
    if not asset:
        raise RuntimeError("בגרסה האחרונה בגיטהאב אין קובץ התקנה (app.zip).")
    ver = rel["tag_name"].lstrip("vV")
    os.makedirs(APPS, exist_ok=True)
    tmp_zip, tmp_dir, final = os.path.join(APPS, "download.zip"), os.path.join(APPS, ver + ".tmp"), os.path.join(APPS, ver)
    req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "FaceID-Launcher"})
    with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r, open(tmp_zip, "wb") as f:
        total, done = int(r.headers.get("Content-Length") or 0), 0
        while True:
            chunk = r.read(1 << 18)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            progress(done * 100 // total if total else None, f"מוריד את התוכנה… {done >> 20} / {total >> 20} MB")
    if total and done != total:
        raise RuntimeError("ההורדה נקטעה — נסה שוב.")
    progress(None, "מתקין… (פעם אחת בלבד)")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    with zipfile.ZipFile(tmp_zip) as z:
        z.extractall(tmp_dir)
    shutil.rmtree(final, ignore_errors=True)
    os.replace(tmp_dir, final)
    os.remove(tmp_zip)
    with open(os.path.join(APPS, "current.txt"), "w", encoding="utf-8") as f:
        f.write(ver)
    return os.path.join(final, APP_EXE)


def install_with_window():
    import tkinter as tk
    from tkinter import ttk
    root = tk.Tk()
    root.title("זיהוי פנים")
    root.geometry("440x150")
    root.resizable(False, False)
    root.configure(bg="#10141c")
    tk.Label(root, text="זיהוי פנים — התקנה ראשונה", font=("Segoe UI", 14, "bold"), fg="#f2f4f8", bg="#10141c").pack(pady=(18, 4))
    msg = tk.StringVar(value="מתחיל…")
    tk.Label(root, textvariable=msg, font=("Segoe UI", 10), fg="#aab3c5", bg="#10141c").pack()
    bar = ttk.Progressbar(root, length=380, mode="indeterminate")
    bar.pack(pady=14)
    bar.start(12)
    state = {}

    def progress(pct, text):
        def ui():
            msg.set(text)
            if pct is None:
                if str(bar["mode"]) != "indeterminate":
                    bar.configure(mode="indeterminate")
                    bar.start(12)
            else:
                bar.stop()
                bar.configure(mode="determinate", value=pct)
        root.after(0, ui)

    def work():
        try:
            state["exe"] = install(progress)
        except Exception as e:
            state["err"] = str(e)
        root.after(0, root.destroy)

    threading.Thread(target=work, daemon=True).start()
    root.mainloop()
    if "err" in state:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, "ההתקנה נכשלה:\n" + state["err"] + "\n\nבדוק את החיבור לאינטרנט ונסה שוב.", "זיהוי פנים", 0x10 | 0x100000)
    return state.get("exe")


if __name__ == "__main__":
    exe = installed() or install_with_window()
    if exe:
        run(exe)
