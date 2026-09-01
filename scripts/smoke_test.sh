#!/usr/bin/env bash
# בדיקת עשן מלאה לבוט Support Contacts IL — להרצה אחרי שמוזן BOT_TOKEN אמיתי ב-.env
set -euo pipefail

PROJECT_DIR="/home/vm/projects/support-contacts-il"
VENV_PY="$HOME/venvs/support-bot/bin/python"
cd "$PROJECT_DIR"

echo "1/4 — בדיקת קומפילציה של כל קבצי הבוט"
"$VENV_PY" -m py_compile bot/*.py bot/handlers/*.py
echo "   OK"

echo "2/4 — טעינת קונפיגורציה (.env)"
"$VENV_PY" -c "
from bot.config import settings
assert settings.bot_token and settings.bot_token != 'PASTE_BOT_TOKEN_HERE', 'BOT_TOKEN לא הוגדר ב-.env'
print('   OK — bot_token מוגדר, db_path =', settings.db_path)
"

echo "3/4 — בדיקת שכבת ה-DB (חיפוש, קטגוריות, פרטי חברה)"
"$VENV_PY" -c "
import asyncio
from bot.config import settings
from bot.db import search_companies, get_categories, get_company_details

async def main():
    results = await search_companies(settings.db_path, 'חשמל')
    assert results, 'חיפוש חשמל לא החזיר תוצאות'
    cats = [c for c, _ in await get_categories(settings.db_path)]
    assert 'בנקים' in cats, 'קטגוריית בנקים לא נמצאה'
    details = await get_company_details(settings.db_path, results[0]['slug'])
    assert details, 'פרטי חברה לא נטענו'
    print(f'   OK — {len(results)} תוצאות ל\"חשמל\", {len(cats)} קטגוריות, פרטי {details[\"name\"]} נטענו')

asyncio.run(main())
"

echo "4/4 — הרצת הבוט בפועל (Ctrl+C לעצירה)"
echo "   מתחבר לטלגרם עם הטוקן שהוגדר ב-.env..."
exec "$VENV_PY" -m bot.main
