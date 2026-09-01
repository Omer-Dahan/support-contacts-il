# 📇 Support Contacts IL — בוט טלגרם

בוט טלגרם לחיפוש חופשי במאגר פרטי שירות הלקוחות של 645 חברות ישראליות, וייצוא אנשי קשר לקובץ VCF.

בנוי עם **Telethon (MTProto)** בלבד — ללא aiogram / python-telegram-bot / pyrogram.

## מבנה הפרויקט

```
bot/
  config.py            הגדרות מ-.env (pydantic-settings)
  main.py              נקודת הכניסה — אתחול הלקוח ורישום ה-handlers
  states.py            מצב חיפוש/דפדוף per-user, בזיכרון בלבד
  db.py                שכבת גישה למסד הנתונים (aiosqlite, חיפוש FTS5, קטגוריות, VCF)
  handlers/
    start.py           /start ותפריט ראשי
    search.py          חיפוש חופשי + רינדור עמודי תוצאות
    details.py          מסך פרטי חברה מלא
    export.py           תפריט ותהליך ייצוא VCF
    callbacks.py         ניווט (menu:/cat:/co:/nav:)
scripts/
  smoke_test.sh        בדיקת עשן מלאה + הרצת הבוט
```

## התקנה

```bash
uv venv ~/venvs/support-bot --python 3.11
uv pip install --python ~/venvs/support-bot/bin/python -r requirements.txt
```

## הגדרה

1. העתיקו `.env.example` ל-`.env` (כבר קיים בפרויקט).
2. פנו ל-[@BotFather](https://t.me/BotFather), צרו בוט חדש, והדביקו את הטוקן בשדה `BOT_TOKEN` ב-`.env`.
3. ערכי `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` הם ערכים ציבוריים אוניברסליים של Telegram Desktop — לא צריך לשנות.

## הרצה

```bash
~/venvs/support-bot/bin/python -m bot.main
```

או דרך סקריפט בדיקת העשן, שגם מוודא שהקונפיגורציה ושכבת ה-DB תקינות לפני ההרצה:

```bash
bash scripts/smoke_test.sh
```

## שימוש בבוט

- **/start** — תפריט ראשי: חיפוש חופשי, עיון לפי קטגוריה, ייצוא VCF, מידע על המאגר.
- **חיפוש חופשי** — הקלידו כל טקסט (שם חברה, קטגוריה, עיר) לקבלת תוצאות מדורגות לפי רלוונטיות (FTS5 + BM25), 5 בעמוד.
- **לפי קטגוריה** — רשימת ~28 קטגוריות → חברות בקטגוריה → פרטים מלאים.
- **ייצוא VCF** — כל המאגר / קטגוריה שלמה / לפי חיפוש חופשי, נשלח כקובץ מוכן לייבוא לטלפון.

## תלות במסד הנתונים

הבוט קורא ישירות מ-`data/sherutplus.db` דרך `aiosqlite`, ואינו תלוי בסקריפטים `scraper/search.py` או `export_vcf.py` — הלוגיקה (בניית שאילתת FTS5, פורמט VCF) שוכפלה ועודכנה עבור גישה אסינכרונית.
