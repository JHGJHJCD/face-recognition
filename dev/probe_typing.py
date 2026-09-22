r"""בדיקת עיכובים בהקלדה בחלון "אדם חדש": פותח את החלון, מקליד בו הקשות אמיתיות (QTest) ומודד
כמה זמן עובר עד שהאות מופיעה בשדה, וכמה החוט הראשי של Qt "נתקע" — עם מצלמה ובלי.

  python dev\probe_typing.py            בלי מצלמה
  python dev\probe_typing.py --camera   עם מצלמה (המצב שבו יהודה הקליד)
"""
import os
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import main  # noqa: E402
from webui.backend import Backend, start_server  # noqa: E402

CAMERA = "--camera" in sys.argv
PAGE = sys.argv[sys.argv.index("--page") + 1] if "--page" in sys.argv else ("video" if "--yt" in sys.argv else "live")
NOBLUR = "--noblur" in sys.argv
YT = sys.argv[sys.argv.index("--yt") + 1] if "--yt" in sys.argv else ""
TEXT = "אברהם יצחק יעקב משה"
lag = {"max": 0.0, "sum": 0.0, "n": 0}
cpu = {}
_last = [time.perf_counter()]


def tick():
    """טיימר של 10ms — אם הוא מגיע מאוחר, החוט הראשי היה תפוס."""
    now = time.perf_counter()
    d = (now - _last[0]) * 1000 - 10
    _last[0] = now
    if d > 0:
        lag["max"] = max(lag["max"], d); lag["sum"] += d; lag["n"] += 1


LOG=open(os.path.join(ROOT,"data","probe_typing.log"),"a",encoding="utf-8")
def log(*a):
    print(*a, file=LOG, flush=True); print(*a, flush=True)


def run():
    app = QApplication(sys.argv)
    if "--prio" in sys.argv:        # ניסוי: עדיפות גבוהה לחוט הממשק, כדי שחוטי הזיהוי לא ידחקו אותו
        import ctypes
        k = ctypes.windll.kernel32
        log("SetThreadPriority ->", k.SetThreadPriority(k.GetCurrentThread(), 1))
    backend = Backend()
    server, url = start_server(backend)
    win = main.Window(backend, url)
    backend.window = win
    win.show()
    js = win.view.page().runJavaScript
    t = QTimer(); t.timeout.connect(tick); t.start(10)
    results = []

    def wait_ready():
        if backend.engine is None:
            return QTimer.singleShot(300, wait_ready)
        if CAMERA:
            backend._camera_on()
        if YT:
            js("location.hash='video'")
            backend.video_scan_url(YT)
            log("yt started")
            return QTimer.singleShot(3000, wait_video)
        QTimer.singleShot(6000 if CAMERA else 1500, open_modal)

    def wait_video():
        if backend.video["running"]:
            log("waiting:", backend.video["pct"], backend.video["phase"])
            return QTimer.singleShot(3000, wait_video)
        log("yt done:", backend.video["status"], "| people:", len((backend.video_result or {}).get("people", [])))
        js("S.videoSel=0; loadVideo()")
        QTimer.singleShot(2500, open_modal)

    def open_modal():
        log("open_modal")
        js(f"location.hash='{PAGE}'")
        if NOBLUR:
            js("document.head.insertAdjacentHTML('beforeend','<style>.overlay{backdrop-filter:none!important}</style>')")
        js("""window.__lat=[]; askPerson('בדיקה');
              setTimeout(()=>{const i=document.querySelector('#m-first');
                i.addEventListener('input',()=>window.__lat.push(performance.now()));},50);
              window.__fr=[]; let p=performance.now(); (function f(){const n=performance.now(); window.__fr.push(n-p); p=n; requestAnimationFrame(f);})();""")
        lag.update(max=0.0, sum=0.0, n=0)
        cpu["t0"], cpu["p0"] = time.perf_counter(), time.process_time()
        QTimer.singleShot(600, lambda: type_next(0))

    def type_next(i):
        log("type", i)
        if i in (3, 9, 15) and "--spy" in sys.argv:
            import subprocess
            spy = os.path.join(os.path.dirname(sys.executable), "Scripts", "py-spy.exe")
            subprocess.Popen([spy, "dump", "--pid", str(os.getpid()), "--native"],
                             stdout=open(os.path.join(ROOT, "data", f"spy_{i}.txt"), "w"), stderr=subprocess.STDOUT)
        if i >= len(TEXT):
            return QTimer.singleShot(800, report) or QTimer.singleShot(3500, lambda: None)
        w = win.view.focusProxy() or win.view
        results.append(time.perf_counter())
        w = app.focusWidget() or w
        for tp in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            app.postEvent(w, QKeyEvent(tp, Qt.Key.Key_unknown, Qt.KeyboardModifier.NoModifier, TEXT[i]))
        QTimer.singleShot(150, lambda: type_next(i + 1))

    def report():
        log("report")
        import collections, threading
        names = {t.ident: t.name for t in threading.enumerate()}
        cnt = collections.Counter()
        me = threading.get_ident()
        def sample():
            for _ in range(100):
                for tid, fr in sys._current_frames().items():
                    if tid in (me, threading.main_thread().ident):
                        continue
                    cnt[(names.get(tid, tid), f"{fr.f_code.co_filename.split(chr(92))[-1]}:{fr.f_lineno} {fr.f_code.co_name}")] += 1
                time.sleep(0.02)
            for k, v in cnt.most_common(8):
                log("  hot:", v, k)
        threading.Thread(target=sample, daemon=True).start()
        def got(v):
            lat, fr = v or [[], []]
            long_frames = sorted(x for x in fr if x > 40)[-5:]
            print(f"camera={CAMERA} page={PAGE} noblur={NOBLUR} prio={'--prio' in sys.argv}  typed={len(TEXT)} got={len(lat)}")
            wall, pt = time.perf_counter() - cpu["t0"], time.process_time() - cpu["p0"]
            print(f"cpu: {pt / wall:.2f} cores busy in this process during typing ({wall:.1f}s)  threads={threading.active_count()}")
            print(f"Qt main-thread lag: max={lag['max']:.0f}ms  total={lag['sum']:.0f}ms over {lag['n']} late ticks")
            print(f"page frames: n={len(fr)}  long(>40ms)={sum(1 for x in fr if x > 40)}  worst={[round(x) for x in long_frames]}")
            js("document.querySelector('#m-first').value", lambda s: (print("value:", s), after_typing()))
        js("[window.__lat, window.__fr]", got)

    def after_typing():
        """סוגרים את החלון (Escape) ובודקים שהמצלמה חוזרת לעבוד אחרי ההשהיה."""
        if CAMERA:
            log("paused while modal:", getattr(backend.live, "paused", None))
        js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")
        fid0 = backend.frame_id
        def check():
            log("after close: paused=", getattr(backend.live, "paused", None), " live=", backend.live is not None, " frames advanced=", backend.frame_id - fid0)
            win.close(); app.quit()
        QTimer.singleShot(4000 if CAMERA else 500, check)

    wait_ready()
    app.exec()
    server.shutdown()


if __name__ == "__main__":
    run()
