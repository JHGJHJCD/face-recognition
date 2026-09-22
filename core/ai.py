"""בינה מלאכותית בענן (Gemini): תיאור הסצנה, תיאור אנשים לא מוכרים, ועוזר שאלות בעברית.

שים לב: זה החלק היחיד בתוכנה ששולח מידע (תמונות מהמצלמה + נתוני יומן) לאינטרנט. כיבוי בהגדרות = הכול מקומי.
המפתחות ב-data/gemini_keys.txt (מפתח בכל שורה) — רוטציה אוטומטית כשמפתח מגיע למכסה.
"""
import base64
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

import cv2

from .utils import DATA_DIR

KEYS_PATH = os.path.join(DATA_DIR, "gemini_keys.txt")
# חינמיים בלבד (pro = מכסה 0). 18/9/2026: "flash-latest" היה מושבת שעות (503/פסקי זמן) בזמן ש-lite ענה ב-2 שנ' ו-3.5 ב-10 שנ'
# ⇒ המהיר ראשון, הכינוי "latest" אחרון, ומודל שנפל מדולג ל-5 דקות. gemini-2.0/2.5-flash הוסרו (404 למפתחות חדשים).
MODELS = ["gemini-flash-lite-latest", "gemini-3.5-flash", "gemini-flash-latest"]
# צפייה בסרטון יוטיוב מקישור (file_data) — רק מודלים שרואים וידאו; flash-lite מתעלם מהמדיה בשקט
VIDEO_MODELS = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-flash-latest"]
MODEL_DOWN_SEC = 300
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"

try:  # NetFree מחליף תעודות — סומכים על מאגר התעודות של Windows
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass


class AIError(Exception):
    pass


def load_keys():
    try:
        with open(KEYS_PATH, encoding="utf-8") as f:
            return [k.strip() for k in f if k.strip() and not k.startswith("#")]
    except OSError:
        return []


def save_keys(text):
    with open(KEYS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(k.strip() for k in text.splitlines() if k.strip()) + "\n")


class GeminiClient:
    def __init__(self):
        self.lock = threading.Lock()
        self.keys = load_keys()
        self.idx = 0
        self.blocked = {}       # (מפתח, מודל) -> עד מתי לדלג
        self.model_down = {}    # מודל -> עד מתי לדלג (503 / פסק זמן = תקלה אצל גוגל, לא במפתח)
        self.calls = 0
        self.last_error = ""

    def reload(self):
        with self.lock:
            self.keys = load_keys()
            self.blocked.clear()

    @property
    def available(self):
        return bool(self.keys)

    def ask(self, prompt, images=(), system=None, temperature=0.4, max_tokens=1024, timeout=25, video_url=None, stop=None):
        """images: רשימת תמונות BGR (numpy) או bytes של JPEG. video_url: קישור יוטיוב — גוגל מושך את הסרטון בצד שלו
        (נטפרי לא מפריע), לוקח דקות לסרטון ארוך. מחזיר טקסט."""
        if not self.keys:
            raise AIError("לא הוגדר מפתח Gemini (לשונית הגדרות).")
        parts = []
        if video_url:
            parts.append({"file_data": {"file_uri": video_url}})
        for im in images:
            if not isinstance(im, (bytes, bytearray)):
                if max(im.shape[:2]) > 960:
                    s = 960 / max(im.shape[:2])
                    im = cv2.resize(im, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
                im = cv2.imencode(".jpg", im, [cv2.IMWRITE_JPEG_QUALITY, 82])[1].tobytes()
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(im).decode()}})
        parts.append({"text": prompt})
        body = {"contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                     "thinkingConfig": {"thinkingBudget": 0}}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        last = "אין תשובה"
        pool = VIDEO_MODELS if video_url else MODELS
        models = [m for m in pool if self.model_down.get(m, 0) <= time.time()] or pool
        for model in models:
            busy = 0
            if "lite" in model:
                body["generationConfig"].pop("thinkingConfig", None)
            else:
                body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
            for _ in range(len(self.keys)):
                if stop is not None and stop():
                    raise AIError("הופסק")
                with self.lock:
                    key = self.keys[self.idx % len(self.keys)]
                    self.idx += 1
                if self.blocked.get((key, model), 0) > time.time():
                    continue
                try:
                    return self._call(key, model, body, timeout)
                except urllib.error.HTTPError as e:
                    detail = e.read().decode("utf-8", "ignore")[:300]
                    last = f"HTTP {e.code}: {detail}"
                    if "NetFree" in detail:
                        raise AIError("נטפרי חסם את הגישה ל-Gemini.")
                    if e.code == 400 and "thinkingConfig" in body["generationConfig"]:
                        # flash-lite דוחה thinkingBudget=0 בהודעה כללית ("invalid argument") — מנסים שוב בלי
                        body["generationConfig"].pop("thinkingConfig", None)
                        continue
                    if e.code in (429, 403, 401):
                        self.blocked[(key, model)] = time.time() + (90 if e.code == 429 else 3600)
                        continue
                    if e.code in (500, 503) and video_url and busy < 4:
                        busy += 1       # וידאו: "high demand" לפעמים חולף תוך שניות — מנסים מפתח אחר לפני שמוותרים על המודל
                        time.sleep(3)
                        continue
                    if e.code in (404, 400, 500, 503):
                        self.model_down[model] = time.time() + MODEL_DOWN_SEC
                        break           # המודל לא זמין / עמוס — עוברים לבא
                except AIError as e:
                    last = str(e)
                    break
                except Exception as e:      # פסק זמן / רשת — מנסים את המודל הבא לפני שמוותרים
                    last = f"אין תשובה מ-{model}: {e}"
                    self.model_down[model] = time.time() + MODEL_DOWN_SEC
                    break
        self.last_error = last
        raise AIError(f"כל המפתחות/המודלים נכשלו. {last}")

    def _call(self, key, model, body, timeout):
        req = urllib.request.Request(URL.format(model), json.dumps(body).encode(),
                                     {"Content-Type": "application/json", "x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        self.calls += 1
        try:
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"]).strip()
        except (KeyError, IndexError):
            text = ""
        if not text:
            raise AIError("Gemini החזיר תשובה ריקה (ייתכן שהתוכן סונן).")
        return text


# ---------- ניסוחי הבקשות ----------
SYSTEM = ("אתה העוזר החכם של תוכנת זיהוי פנים ונוכחות. ענה תמיד בעברית פשוטה, קצר וענייני, בלי Markdown ובלי כוכביות. "
          "את זהות האנשים קובעת התוכנה בלבד (השמות שנמסרים לך) — לעולם אל תנחש מי האדם לפי המראה שלו.")


def scene_prompt(people):
    who = "; ".join(people) if people else "אין פנים מזוהות כרגע"
    return ("זו תמונה ממצלמת התוכנה. מה שהתוכנה זיהתה (מימין לשמאל בתמונה): " + who + ".\n"
            "תאר ב-2–3 משפטים קצרים מה קורה: מה האנשים עושים, שפת הגוף שלהם (תנוחה, ידיים, כיוון מבט, מתח או רוגע), מצב הרוח הכללי, כמה אנשים רואים (גם כאלה שהפנים שלהם לא נקלטו), "
            "וכל דבר חריג או ראוי לתשומת לב. אם אין שום דבר מעניין — משפט אחד.")


UNKNOWN_PROMPT = ("זו תמונה של אדם שהתוכנה לא מכירה. תאר אותו במשפט אחד או שניים כדי שיהיה קל להיזכר מי זה: "
                  "גיל משוער, זקן/משקפיים/כיסוי ראש, לבוש בולט, הבעה. בלי לנחש שם או זהות.")


# ---------- בדיקת סרטון: נשים וילדות (לרעיון "בודק סרטונים לציבור החרדי") ----------
_YT_RE = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/|live/|v/))([A-Za-z0-9_-]{11})")


def youtube_url(text):
    """מזהה קישור/מזהה יוטיוב בטקסט ומחזיר כתובת קנונית, או None."""
    text = (text or "").strip()
    m = _YT_RE.search(text)
    if not m and re.fullmatch(r"[A-Za-z0-9_-]{11}", text):
        return "https://www.youtube.com/watch?v=" + text
    return "https://www.youtube.com/watch?v=" + m.group(1) if m else None


def parse_json(text):
    """Gemini לפעמים עוטף ב-```json … ``` או מוסיף משפט לפני — מחלצים את ה-JSON הראשון."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[4:] if text.lower().startswith("json") else text
    for opener, closer in (("{", "}"), ("[", "]")):
        a, b = text.find(opener), text.rfind(closer)
        if a != -1 and b > a:
            try:
                return json.loads(text[a:b + 1])
            except ValueError:
                continue
    raise AIError("תשובת Gemini לא בפורמט הצפוי: " + text[:120])


def video_check_prompt(girl_age):
    return ("צפה בכל הסרטון מתחילתו ועד סופו ומצא כל קטע שבו מופיעה אישה, נערה או ילדה (כולל ברקע, מהצד, מרחוק, בציור/אנימציה "
            "ובתמונות שמוצגות על המסך). לכל קטע רצוף רשום את זמן ההתחלה והסיום המדויקים ככל האפשר (mm:ss). אל תפספס קטעים קצרים. "
            f"לכל דמות נשית הערך גיל במספר. ילדה נחשבת 'קטנה' עד גיל {girl_age} (לא כולל {girl_age}). "
            "החזר JSON בלבד, בלי הסבר, במבנה: "
            '{"segments":[{"start":"mm:ss","end":"mm:ss","who":"אישה|נערה|ילדה","age":מספר,"small":true/false,"note":"תיאור קצר בעברית"}],'
            '"summary":"משפט אחד בעברית: כמה קטעים, ומה סוג הדמויות"}. '
            'אם אין אף דמות נשית: {"segments":[],"summary":"לא נמצאו נשים או ילדות בסרטון"}.')


def frames_check_prompt(n, girl_age):
    return (f"מצורפות {n} תמונות (פריימים מסרטון), ממוספרות לפי הסדר 0..{n - 1}. עבור כל תמונה קבע האם מופיעה בה אישה, נערה או ילדה, "
            f"והערך את גילה במספר. ילדה 'קטנה' = מתחת לגיל {girl_age}. אם בתמונה יש כמה דמויות נשיות — התייחס לצעירה ביותר. "
            "החזר JSON בלבד: "
            '[{"i":מספר התמונה,"female":true/false,"who":"אישה|נערה|ילדה|","age":מספר או null,"small":true/false,"note":"מילה-שתיים"}]')
