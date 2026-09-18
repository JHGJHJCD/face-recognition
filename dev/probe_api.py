"""בדיקת API בלי חלון: מעלה את ה-Backend והשרת, ממתין למנועים, וקורא לנתיבי GET. שימוש: probe_api.py people stats ..."""
import os
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PyQt6.QtWidgets import QApplication  # noqa: E402

from webui.backend import Backend, start_server  # noqa: E402

app = QApplication(sys.argv)
be = Backend()
srv, url = start_server(be)


def work():
    while be.engine is None and not be.load_error:
        time.sleep(0.5)
    for name in sys.argv[1:] or ["people"]:
        try:
            t0 = time.time()
            with urllib.request.urlopen(url + "api/" + name, timeout=30) as r:
                body = r.read().decode()
            print(name, "%.2fs" % (time.time() - t0), "->", r.status, len(body), "bytes", body[:200].encode("ascii", "replace").decode())
        except urllib.error.HTTPError as e:
            print(name, "-> HTTP", e.code, e.read().decode()[:400].encode("ascii", "backslashreplace").decode())
        except Exception as e:
            print(name, "-> ERR", repr(e))
    sys.stdout.flush()
    os._exit(0)


threading.Thread(target=work, daemon=True).start()
app.exec()
srv.shutdown()
