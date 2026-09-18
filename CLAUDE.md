# זיהוי פנים — CLAUDE.md

תוכנת PyQt6 מקומית (עברית, RTL) לזיהוי פנים. נבנתה 17/9/2026 בהשראת סרטון face-api.js
(https://youtu.be/CVClHLwv-4I) אבל עם מנועים חזקים בהרבה. **הזיהוי עצמו רץ מקומית.** מאז 17/9/2026 יש רכיב AI בענן (Gemini) — הכרעת יהודה: "אוטומטי ברקע"; הוא **היחיד** ששולח תמונות החוצה, ונכבה בהגדרות (`ai_enabled`).

## הרצה
- קיצור: `זיהוי פנים.lnk` (בתיקייה וב-`Desktop\קיצורים\`) → `pythonw.exe main.py` בלי טרמינל.
- Python **3.12** (`...\Python312\python.exe`). תלויות: `PyQt6 openvino onnxruntime opencv-python-headless numpy openpyxl pillow`.
- בדיקות: `tests\test_pipeline.py [תיקייה] [כמות]` (מקצה לקצה, DB זמני) · `main.py --camera --shot <תיקייה>` (מצלם כל לשונית ל-PNG ויוצא).
- `tests\test_upgrade.py [תיקייה] [כמות]` — בודק את שדרוג 17/9: תמונת-ראי, תאורה חלשה, כלל המרווח, סיכומי נוכחות.
- `tests\make_shortcut.py` — יוצר מחדש סמל + desktop.ini + קיצורים.

## מבנה
- `core/engine.py` — המודלים (מחלקת `Net`: OpenVINO על **Intel GPU**, גיבוי ONNX Runtime CPU). `FaceEngine.detect/embed/gender_age/emotion/liveness`.
- `core/db.py` — SQLite (`data/faces.db`), הגדרות (`data/settings.json`), גלריה בזיכרון, `match()`, קיבוץ Chinese-Whispers.
- `core/live.py` — `LiveWorker`: מצלמה, מעקב IoU, הצבעת זהות על 6 מדידות, נוכחות, התרעת לא-מוכר, רישום מהמצלמה.
- `core/jobs.py` — סריקת תיקיות תמונות (ניתנת להמשך) וסריקת וידאו.
- `core/ai.py` — `GeminiClient` (REST דרך urllib, בלי SDK): רוטציה על `data/gemini_keys.txt` (24 מפתחות, הועתקו מ-`ארכיון\צאט קידושין ישן`), שרשרת מודלי flash חינמיים, חסימת מפתח זמנית ב-429. ניסוחי הבקשות (`SYSTEM`, `scene_prompt`, `UNKNOWN_PROMPT`) שם.
- `ui/tabs.py`, `ui/widgets.py`, `main.py` — 7 לשוניות: זיהוי חי, אנשים, מיון תמונות, סריקת וידאו, יומן נוכחות, עוזר AI, הגדרות.

## מודלים (`models/`, ‏~380MB)
| תפקיד | מודל | מקור |
|---|---|---|
| איתור | SCRFD-10G `det_10g.onnx` | insightface releases v0.7 `buffalo_l.zip` |
| זהות | ArcFace R100 Glint360K `glintr100.onnx` | insightface v0.7 `antelopev2.zip` |
| גיל/מין | FairFace ResNet34 `fairface.onnx` | github yakhyo/fairface-onnx releases |
| הבעות | HSEmotion `emotion.onnx` (enet_b0_8_best_vgaf) | **jsdelivr** `cdn.jsdelivr.net/gh/av-savchenko/face-emotion-recognition@main/...` |
| זיוף | MiniFASNetV2 (2.7) + V1SE (4.0) | github yakhyo/face-anti-spoofing releases |

## דברים לא-מובנים-מאליהם (נלמדו בבנייה)
- **מהירות:** על המעבד (Core 5 120U) זהות = ~200–350ms לפנים; על ה-iGPU דרך OpenVINO = ~13–30ms. לכן OpenVINO GPU חובה.
  קומפילציה ראשונה ל-GPU ~1–2 דק'; אח"כ מטמון ב-`%LOCALAPPDATA%\FaceID_ov_cache` (טעינה ~10 שנ'). מודל חדש = קומפילציה מחדש.
- צורות קלט **סטטיות** (GPU): איתור תמיד 640×640, שאר המודלים batch=1.
- וקטורים של מודלי זהות שונים לא ברי-השוואה → כל שורה ב-DB מתויגת `model`; החלפת מודל = רישום מחדש.
- מודל `genderage` של InsightFace נתן גיל 65–74 לבן 26 במצלמה הזו → הוחלף ב-FairFace (נותן ~30). גיל מוצג מעוגל ל-5.
- **NetFree:** מטשטש תמונות אנשים מהרשת (אי אפשר להוריד תמונות בדיקה — בודקים על `Pictures` המקומי/מצלמה); חוסם `github.com/...?raw=true` ו-raw.githubusercontent לקובצי onnx מסוימים — jsdelivr עבר.
- נתיבים עבריים: `imread/imwrite` דרך bytes, וידאו דרך נתיב 8.3 (`short_path`), מודלים נטענים כ-bytes.
- חבילת `insightface` לא מותקנת בכוונה (דורשת קומפיילר) — הפענוח של SCRFD והיישור (Umeyama) ממומשים ב-engine.py.
- סף זיהוי ברירת מחדל 0.40 (קוסינוס). נמדד: אותו אדם 0.66–0.95, אנשים שונים כמעט תמיד <0.3.

## שדרוג 17/9/2026 (דיוק · נוכחות · AI · פרטי אדם)
- **דיוק:** `embed(tta=True)` = וקטור מתמונה + תמונת ראי (אותו מרחב וקטורי — לא צריך רישום מחדש). עולה פי 2 זמן, לכן בזיהוי חי רץ
  רק במקרה גבולי (דמיון בין סף−0.12 לסף+0.15); ברישום ובסריקות תמיד. `db.match` — כלל מרווח: שני אנשים בהפרש <0.04 וציון <0.55 → "לא מוכר".
  פריים גרוע (מטושטש/פרופיל) שלא זוהה **לא נספר** כהצבעת "לא מוכר". `enhance_low_light` (גמא+CLAHE) רק כשהתמונה חשוכה.
  **למידה אוטומטית** (`auto_learn`): 6/6 הצבעות לאותו אדם, דמיון ≥0.58, פנים חדות, והמראה שונה מהדגימות (מקס׳ <0.75) → דגימה חדשה
  במקור "למידה אוטומטית", עד 20 לאדם, אחת ל-30 שנ׳.
- **נמדד ונפסל:** אורך הווקטור הגולמי (`Face.norm`) כמדד איכות — ב-glintr100 חד≈22.5, מטושטש≈19, חופף מדי. לא משמש לסינון.
- **נוכחות:** `db.daily_summary` (הגעה/עזיבה/זמן בפועל/כניסות/איחור מול `work_start`), `db.absent`; בלשונית 4 תצוגות + ייצוא התצוגה הנוכחית.
- **AI:** ב-`LiveWorker` חוט נפרד (`_ai_loop`) — תיאור סצנה כשהרכב האנשים משתנה או כל `ai_interval` שנ׳ (נסוג בכישלונות), ותיאור כל לא-מוכר
  (נשמר ב-`unknown_events.note`). הכול נרשם ב-`ai_notes` (60 יום). לשונית העוזר שולחת כהקשר: אנשים+גילים, 14 ימי נוכחות, לא-מוכרים, הערות 24 שעות, ותמונת מצלמה חיה.
  ה-SYSTEM אוסר על Gemini לנחש זהות — זהות קובעת רק התוכנה.
- **פרטי אדם:** `ask_person` (שם פרטי + משפחה חובה, תאריך לידה רשות) החליף את `ask_name` בכל 5 המקומות; `persons.first_name/last_name/birth`;
  `name` = "פרטי משפחה". גיל מתאריך לידה גובר על הערכת FairFace בתווית החיה; 🎂 ביום ההולדת.
- ⚠️ `QDateEdit` ב-RTL הופך את סדר יום/חודש/שנה — חובה `setLayoutDirection(LTR)` **לפני** `setDisplayFormat`.
- **רעיון פתוח (יהודה ביקש 17/9):** ממשק "בעיצוב דפדפן". הדרך בלי לפגוע בביצועים: להשאיר את `core/` כמו שהוא ולהחליף רק את `ui/` בדף HTML
  בתוך חלון (QtWebEngine/pywebview) או שרת מקומי + דפדפן; הווידאו כ-MJPEG/‏canvas. טרם בוצע — ממתין להחלטה.
