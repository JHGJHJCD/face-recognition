"""דוחות נוכחות, הקשר לעוזר ה-AI וכתיבת אקסל — משותף לכל ממשק."""
import time

from .utils import fmt_time

VIEWS = ["סיכום יומי", "רשומות מפורטות", "סיכום לתקופה", "נעדרים"]


def day_range(d_from, d_to):
    """'YYYY-MM-DD' ×2 → (תחילת היום הראשון, סוף היום האחרון) בשניות."""
    t0 = time.mktime(time.strptime(d_from, "%Y-%m-%d"))
    t1 = time.mktime(time.strptime(d_to, "%Y-%m-%d")) + 86400
    return t0, max(t1, t0 + 86400)


def _day(day):
    return f"{day[8:10]}/{day[5:7]}/{day[:4]}"


def _hm(t):
    return time.strftime("%H:%M", time.localtime(t))


def attendance_view(db, settings, view, t0, t1):
    """(כותרות, שורות) לאחת מ-4 התצוגות ב-VIEWS."""
    if view == 1:
        rows = [(name, time.strftime("%d/%m/%Y", time.localtime(first)), time.strftime("%H:%M:%S", time.localtime(first)),
                 time.strftime("%H:%M:%S", time.localtime(last)), fmt_time(last - first)) for name, first, last in db.attendance(t0, t1)]
        return ["שם", "תאריך", "נראה לראשונה", "נראה לאחרונה", "משך"], rows
    if view == 3:
        return ["תאריך", "שם"], [(_day(d), n) for d, n in db.absent(t0, t1)]
    days = db.daily_summary(t0, t1, settings["work_start"])

    def late(d):
        return "" if d["late"] is None else ("בזמן" if d["late"] == 0 else f"{d['late']} דק׳")

    if view == 0:
        return (["שם", "תאריך", "הגעה", "עזיבה", "זמן נוכחות בפועל", "כניסות", "איחור"],
                [(d["name"], _day(d["day"]), _hm(d["first"]), _hm(d["last"]), fmt_time(d["total"]), str(d["visits"]), late(d)) for d in days])
    per = {}
    for d in days:
        p = per.setdefault(d["pid"], {"name": d["name"], "days": 0, "total": 0.0, "late": 0, "first": []})
        p["days"] += 1
        p["total"] += d["total"]
        p["late"] += 1 if d["late"] else 0
        lt = time.localtime(d["first"])
        p["first"].append(lt.tm_hour * 60 + lt.tm_min)
    rows = []
    for p in sorted(per.values(), key=lambda x: x["name"]):
        avg = int(sum(p["first"]) / len(p["first"]))
        rows.append((p["name"], str(p["days"]), fmt_time(p["total"]), f"{avg // 60:02d}:{avg % 60:02d}", str(p["late"])))
    return ["שם", "ימי נוכחות", "סך זמן נוכחות", "שעת הגעה ממוצעת", "מספר איחורים"], rows


def assistant_context(db, settings):
    now = time.time()

    def dt(t):
        return time.strftime("%d/%m %H:%M", time.localtime(t))

    L = [f"עכשיו: {time.strftime('%d/%m/%Y %H:%M')}",
         "אנשים רשומים: " + (", ".join(sorted(n + (f" (גיל {db.age(p)}, נולד {db.births[p]})" if p in db.births else "")
                                             for p, n in db.names.items())) or "אין"),
         f"שעת התחלה לחישוב איחורים: {settings['work_start'] or 'לא הוגדרה'}", "",
         "נוכחות ב-14 הימים האחרונים (יום | שם | הגעה | עזיבה | זמן בפועל | כניסות | דקות איחור):"]
    for d in db.daily_summary(now - 14 * 86400, now + 1, settings["work_start"])[:300]:
        L.append(f"{d['day']} | {d['name']} | {_hm(d['first'])} | {_hm(d['last'])} | {fmt_time(d['total'])} | {d['visits']} | "
                 f"{'' if d['late'] is None else d['late']}")
    L += ["", "אנשים לא מוכרים שנקלטו (זמן | תיאור):"]
    L += [f"{dt(ts)} | {note or 'אין תיאור'}" for _, ts, _, _, note in db.unknown_events(30)]
    L += ["", "הערות שה-AI רשם מהמצלמה ב-24 השעות האחרונות (זמן | מי זוהה | תיאור):"]
    L += [f"{dt(ts)} | {people} | {text}" for ts, kind, people, text in db.ai_notes(now - 86400, 50) if kind == "scene"]
    return "\n".join(L)


def write_xlsx(path, headers, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.sheet_view.rightToLeft = True
    ws.append(list(headers))
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(list(r))
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22
    wb.save(path)
