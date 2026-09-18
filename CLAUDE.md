# זיהוי פנים — CLAUDE.md

תוכנת Windows מקומית (עברית, RTL) לזיהוי פנים. נבנתה 17/9/2026 בהשראת סרטון face-api.js
(https://youtu.be/CVClHLwv-4I) אבל עם מנועים חזקים בהרבה. **הזיהוי עצמו רץ מקומית.** רכיב ה-AI בענן (Gemini) — הכרעת יהודה: "אוטומטי ברקע";
הוא **היחיד** ששולח תמונות החוצה, ונכבה בהגדרות (`ai_enabled`). מ-18/9/2026: ממשק HTML בתוך חלון (QtWebEngine), EXE יחיד, עדכון אוטומטי מגיטהאב.

> תחזוקה עצמית: בשינוי מבני משמעותי (מסך/פיצ'ר גדול/שינוי בבנייה-שחרור) — עדכן קובץ זה באותה הזדמנות.

## עקרונות עבודה (הועברו מ-`מנהל_חלוקה` 18/9/2026 לבקשת יהודה — אותה צורת עבודה בשני הפרויקטים)
- **המשתמש לא מתכנת** — לעבוד ולשחרר, לא להסביר צעדים טכניים. הערת-שחרור קצרה בעברית פשוטה בסוף.
- אל תשבור תאימות לאחור; אל תשנה שמות עמודות/שדות ב-DB בלי מיגרציה (`ALTER TABLE … ADD COLUMN` ב-`Database.__init__`, כמו `birth`/`note`).
- שמור RTL מלא ופשטות למשתמש בכל שינוי UI.
- לפני מחיקת קוד — ודא שאינו בשימוש.
- **אימות = העיקרון החשוב ביותר:** כשאפשר לאמת — אמת בעצמך (בדיקות/צילום מסך אמיתי), אל תבקש מהמשתמש. סגור לולאת-משוב לבד עד שהתוצאה נכונה.
- **משימה מורכבת → תכנן קודם.** אם משהו משתבש באמצע — חזור לתכנון, אל תתקן תוך כדי ריצה. במקרה גבולי או UX — שאל שאלה ממוקדת אחת (בעברית מדוברת, "(מומלץ)").
- **אל תסתפק בפתרון הראשון:** אחרי מימוש — שקול מימוש אלגנטי יותר; עבור על הקוד לאיתור שכפול/סיבוך (`/simplify`).
- **הנדסה מצטברת:** כל טעות שלי או תיקון של המשתמש → כלל ב-CLAUDE.md (מלכודות) או בזיכרון, כדי לא לחזור עליה.
- **הקשר נקי:** במשימות רחבות/סריקה — האצל לסוכני-משנה במקום לגרור הכל לשיחה הראשית.
- **ניהול ידע — דפוס LLM Wiki:** קובץ זה = ה-wiki (אני כותב, יהודה קורא); מקורות קפואים → `docs/raw/`; ניתוח/הכרעה מהשיחה נכתבים חזרה לכאן. Lint: `/בדוק-ידע`.

## סדר עדיפויות בהתנגשות
**שלמות נתונים → דיוק הזיהוי → יציבות → חוויית משתמש → איכות קוד.** כששניים מתנגשים, המוקדם מנצח.

## לפני סיום משימה · Definition of Done
- הרץ את הבדיקות הרלוונטיות (`tests\test_pipeline.py`, `tests\test_upgrade.py`) ואמת ויזואלית (`main.py --shot <תיקייה>` — צילום כל מסך).
- שינוי קוד אפליקציה שאומת → **בנה EXE ושחרר Release בגיטהאב בלי לחכות שיבקשו** (הכרעת יהודה במנהל חלוקה 24/08/2026, חלה גם כאן). לא לשחרר קוד שלא אומת.
- בשינוי מבני — עדכן `CLAUDE.md`. הושלם = עובד ואומת בפועל, הבדיקות עוברות, לא נשברה תאימות/שלמות נתונים, התיעוד עודכן.

## ⚠️ מלכודות ידועות
- **Python:** בנה/בדוק רק עם `C:\Users\יהודה\AppData\Local\Programs\Python\Python312\python.exe`. ה-`python` שב-PATH הוא 3.14 וחסר תלויות.
- **גופן:** Segoe UI בלבד (גם ב-CSS: `"Segoe UI Variable Text", "Segoe UI"`).
- **צילומי מסך עברית:** בלי offscreen. הממשק החדש: `main.py --shot <תיקייה>` (‏`win.grab()` על QWebEngineView עובד).
- **נטפרי חוסם צ'אטים של Claude על תמונות:** `Read` של PNG מסוים יכול להקפיץ 418 ולהרוג את הצ'אט לצמיתות. אם צ'אט נחסם אחרי קריאת צילום — לא לקרוא אותו שוב; לאמת דרך `gemini_task.py -f <png>`.
- **כלי Bash + heredoc מוחקים לוכסנים-אחוריים** (`\n` הפך לשורה אמיתית ב-`main.py`, ו-`\U` שבר סקריפט — 18/9) — סקריפטי-עזר דרך Write, עריכות דרך Edit.
- **PyInstaller onefile:** `QtWebEngineWidgets` מייבא `QtPrintSupport` — **אסור** ל-exclude אותו (קרס בהפעלה 18/9). `collect_all("openvino")` מושך torch/transformers/tensorflow (‏+450MB) — הם ב-excludes. `hiddenimports` של openvino = לא (רק מה ש-`import openvino` מושך). devtools של Chromium מסוננים מ-`a.datas`. תוצאה ~249MB. `--classic` ו-`ui/` מוחרגים מה-EXE.
- **EXE בלי קונסולה:** שגיאות הפעלה נכתבות ל-`crash_log.txt` ליד ה-EXE (`main._crash`). בדיקה: להעתיק ל-`%TEMP%\faceid_test` עם junction ל-`models` ולהריץ `--shot`.
- **הודעת "_MEI / Failed to remove temporary directory"** בסגירה — תהליך-האב של PyInstaller + נטפרי, לא ניתן לחסום מהקוד. לא שובר נתונים. לא להשקיע בזה.
- **`QDateEdit` ב-RTL** הופך יום/חודש/שנה — `setLayoutDirection(LTR)` **לפני** `setDisplayFormat` (רלוונטי רק ל-`--classic`).
- **גלילה בממשק ה-HTML:** `#app`/`main` חייבים `height:100vh; overflow:hidden` — בלי זה `#page` גדל מעבר למסך ושום דבר לא נגלל (הבאג של 18/9). אלמנטים עם `.btn` + `hidden` צריכים `[hidden]{display:none!important}`.

## הרצה
- קיצור: `זיהוי פנים.lnk` (בתיקייה וב-`Desktop\קיצורים\`) → `pythonw.exe main.py` בלי טרמינל. `main.py --classic` = הממשק הישן (PyQt), גיבוי בלבד.
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
- `core/reports.py` — דוחות נוכחות (4 תצוגות), הקשר לעוזר, כתיבת אקסל — משותף לשני הממשקים.
- `core/updater.py` — עדכון אוטומטי (repo `JHGJHJCD/face-recognition`, asset `FaceID.exe`) + הורדת `models.zip` מ-Release `models-v1` בהפעלה ראשונה.
- `webui/backend.py` — **הממשק הנוכחי.** `Backend(QObject)` + שרת HTTP מקומי (127.0.0.1, פורט אקראי, אסימון בכתובת). `/frame` = JPEG + תוויות ב-`X-Meta`;
  `/api/*` JSON; `/img/*` תמונות ממוזערות. `in_main()` מריץ בחוט Qt (חלונות קבצים, יצירת workers). `version.py` = מספר גרסה.
- `webui/static/` — `index.html`/`app.css`/`app.js` (ללא ספריות): 8 מסכים — זיהוי חי (canvas), אנשים, מיון תמונות, סריקת וידאו, יומן נוכחות
  (סיכום יומי/מפורט-עם-עריכה/תקופה/נעדרים), עוזר AI, **נתונים ועדכונים** (סטטיסטיקה, גיבוי ZIP/שחזור, ניקוי, אזור מסוכן, עדכון תוכנה), הגדרות. מצב בהיר/כהה.
- `main.py` — חלון `QWebEngineView` + `--shot`/`--camera`/`--classic`/`--debug`. `ui/` + `main_classic.py` = הממשק הישן (לא נארז ב-EXE).

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
- **ממשק "בעיצוב דפדפן" (יהודה ביקש 17/9, נבנה 18/9):** `core/` נשאר, `ui/` הוחלף ב-`webui/` — ראה "מבנה".

## בנייה ושחרור (מ-18/9/2026)
- `version.py` `APP_VERSION` → `python -m PyInstaller --noconfirm --clean זיהוי_פנים.spec` (‏~5 דק') → `cp dist/זיהוי_פנים.exe dist/FaceID.exe` →
  בדיקה מתיקייה נקייה (ראה מלכודות) → `git add/commit/push` → `gh release create vX.Y dist/FaceID.exe -R JHGJHJCD/face-recognition --latest --notes "…"`.
- **הערות שחרור** בעברית פשוטה: שורה ראשונה כותרת עם `:`, ואז פריטים בשורות `-` (מוצג בכרטיס העדכון בתוכנה, עד 600 תווים).
- **מודלים:** Release קבוע `models-v1` עם `models.zip` (‏329MB, נבנה מ-`models/*.onnx`). מודל חדש = תג חדש + `updater.MODELS_TAG`.
- `gh` לא ב-PATH: `C:\Users\יהודה\AppData\Local\gh_cli\bin\gh.exe`. **אין קרדיט Claude ב-commits** (הכרעת המשתמש 27/08/2026).
- `.gitignore`: `data/` (DB, מפתחות Gemini, לא-מוכרים), `models/`, `dist/`, `build/`, PNG. **לעולם לא לדחוף נתוני אנשים או מפתחות.**
- מנגנון העדכון בתוכנה: בדיקה 20 שנ' אחרי הפעלה וכל 30 דק' (`Backend._update_loop`, ETag → 304 לא נספר במכסה); כפתור בנתונים-ועדכונים; ההתקנה
  מורידה `update_download.exe`, `apply_update` משנה שם ל-`.old`, מחליף, מפעיל מחדש (מנקה משתני `_PYI_*` — אחרת ה-EXE החדש מת). מהקוד (לא frozen) — רק הודעה.
- ⚠️ יצירת repo ציבורי דרך `gh repo create` נחסמה ע"י מסווג ההרשאות של Claude Code (18/9) — יהודה מאשר/יוצר; אחרי שה-repo קיים, push ו-release עובדים.
