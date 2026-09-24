# הודעה לסוכן: התקנת Support Contacts IL בשרת רשמי (production)

## ההקשר שצריך למסור לסוכן

**הפרויקט:** Support Contacts IL, בוט טלגרם לפרטי שירות לקוחות של 645 חברות ישראליות.
**ריפו:** https://github.com/Omer-Dahan/support-contacts-il (ציבורי)
**מה יש בריפו:** `bot/` (קוד הבוט), `data/sherutplus.db` (מסד הנתונים, 10MB), `scraper/`, `research/`, `scripts/smoke_test.sh`, `requirements.txt`, `.env.example`
**טכנולוגיה:** Python 3.11, Telethon (MTProto), SQLite עם FTS5, aiosqlite, pydantic-settings
**אין צורך להעביר את ה-DB בנפרד** — הוא נמצא בריפו.

---

## הנוסח להעביר לסוכן

> אני צריך שתכין ותתקין את הבוט **Support Contacts IL** על שרת לינוקס רשמי (production).
>
> **הריפו:** https://github.com/Omer-Dahan/support-contacts-il
> **השרת:** [מלא כאן: כתובת השרת, משתמש ההתחברות, ואיך מתחברים]
> **נתיב התקנה מבוקש:** `/opt/bots/support-contacts-il` (או `/home/<user>/projects/support-contacts-il` אם אין הרשאות ל-opt)
>
> ### מה הבוט צריך
> - Python 3.11 ומעלה
> - venv נפרד (אסור להתקין גלובלית, PEP 668)
> - חבילות מ-`requirements.txt`: telethon, aiosqlite, pydantic-settings, python-dotenv
> - קובץ `.env` עם: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `BOT_TOKEN`, `DB_PATH`, `ADMIN_CHAT_ID` (הטוקנים יימסרו בנפרד, לא לכתוב אותם בלוגים או בפלט)
> - מסד הנתונים `data/sherutplus.db` שמגיע עם הריפו
> - גישה יוצאת לרשת (Telegram MTProto על פורט 443)
>
> ### מה אני רוצה שתעשה
> 1. **הכן סקריפט התקנה** `deploy/install.sh` שאפשר להריץ שוב ושוב בלי לשבור כלום (idempotent):
>    - מתקין תלויות מערכת אם חסרות (python3.11, python3-venv, git, curl)
>    - משכפל את הריפו (או מושך עדכונים אם כבר קיים)
>    - יוצר venv ב-`/opt/bots/support-contacts-il/venv` ומתקין את `requirements.txt`
>    - בודק שה-`.env` מלא ותקין, ומציג שגיאה ברורה אם חסר משהו
>    - מתקין את שירות ה-systemd ומפעיל אותו
>    - מריץ בדיקת עשן בסוף ומדווח אם עבר
> 2. **הכן קובץ שירות systemd** `deploy/support-contacts-il.service`:
>    - `Type=simple`, `Restart=always`, `RestartSec=10`
>    - `EnvironmentFile` שמצביע ל-`.env` של הפרויקט
>    - לוגים ל-journald (`StandardOutput=journal`, `SyslogIdentifier=support-contacts-il`)
>    - הגבלת משאבים סבירה: `MemoryMax=512M`, `CPUQuota=50%`
>    - אתחול אוטומטי עם עליית השרת (`WantedBy=multi-user.target`)
>    - אל תשתמש ב-`User=root` אם אין סיבה, עדיף משתמש ייעודי או `vm`
> 3. **כתוב תיעוד התקנה** `deploy/INSTALL.md` בעברית: כל שלב, פקודה מדויקת, ומה עושים אם משהו נכשל
> 4. **אבטח את הסודות:** `.env` בהרשאות `600`, ולוודא ש-`.env` נמצא ב-`.gitignore` (הוא כבר שם)
> 5. **הגדר פקודת עדכון:** `deploy/update.sh` שמושך מהגיט, מתקין תלויות חדשות ומפעיל מחדש את השירות
> 6. **תן לי את כל הפקודות בדיוק כפי שהרצת**, לפי הסדר, כדי שאוכל להריץ אותן ידנית בשרת אחר. כולל התקנת תלויות מערכת, יצירת venv, הגדרת ה-service והפעלה. לא תיאור כללי, פקודות מוכנות להעתקה.
> 7. **בדוק שהכול עובד בפועל** והראה לי פלט אמיתי:
>    - `systemctl status support-contacts-il` מציג active (running)
>    - הלוג ב-`journalctl -u support-contacts-il` מציג "Support Contacts IL bot started"
>    - הבוט מגיב להודעה בטלגרם (אם אפשר לבדוק)
>    - הפעלה מחדש של השירות מחזירה אותו לאוויר תוך כמה שניות
>
> ### הערות חשובות
> - הבוט צריך לשרוד restart של השרת בלי התערבות ידנית
> - אל תדפיס טוקנים או סודות בשום פלט, לוג או קומיט
> - אם משהו לא עובד, תגיד לי מה בדיוק ואל תמציא פתרון שנראה עובד
> - אני מעדיף פקודות שמראות פלט אמיתי על פני הסברים

---

## מה למלא לפני העברה לסוכן

| שדה | מה למלא |
|---|---|
| כתובת השרת | IP או דומיין |
| משתמש התחברות | root / vm / אחר |
| נתיב התקנה | `/opt/bots/support-contacts-il`? |
| האם יש Python 3.11 | לבדוק עם `python3 --version` |
| האם יש systemd | כמעט תמיד כן בלינוקס מודרני |
| מפתחות | `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `BOT_TOKEN` |

## המפתחות (להעביר לסוכן בערוץ מאובטח, לא בצ'אט ציבורי)
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — מ-my.telegram.org
- `BOT_TOKEN` — מ-@BotFather
- `DB_PATH` — `/opt/bots/support-contacts-il/data/sherutplus.db`
- `ADMIN_CHAT_ID` — אופציונלי, להתראות שגיאה
