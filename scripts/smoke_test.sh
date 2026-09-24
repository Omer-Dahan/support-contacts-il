#!/usr/bin/env bash
# בדיקת עשן מלאה לבוט Support Contacts IL - להרצה אחרי שמוזן BOT_TOKEN אמיתי ב-.env
set -euo pipefail

PROJECT_DIR="/home/vm/projects/support-contacts-il"
VENV_PY="$HOME/venvs/support-bot/bin/python"
cd "$PROJECT_DIR"

echo "1/5 - בדיקת קומפילציה של כל קבצי הבוט"
"$VENV_PY" -m py_compile bot/*.py bot/handlers/*.py
echo "   OK"

echo "2/5 - טעינת קונפיגורציה (.env)"
"$VENV_PY" -c "
from bot.config import settings
assert settings.bot_token and settings.bot_token != 'PASTE_BOT_TOKEN_HERE', 'BOT_TOKEN לא הוגדר ב-.env'
print('   OK - bot_token מוגדר, db_path =', settings.db_path, ', users_db_path =', settings.users_db_path)
"

echo "3/5 - בדיקת שכבת חברות (חיפוש, קטגוריות, פרטי חברה)"
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
    print(f'   OK - {len(results)} תוצאות ל\"חשמל\", {len(cats)} קטגוריות, פרטי {details[\"name\"]} נטענו')

asyncio.run(main())
"

echo "4/5 - בדיקת שכבת משתמשים וניהול (users.db + הרשאות admin)"
"$VENV_PY" -c "
import asyncio
import os
import tempfile
from bot.config import is_admin, settings
from bot.users_db import init_users_db, ensure_user, record_event, get_admin_stats
from bot.handlers.admin import build_admin_report

async def test_admin():
    test_db = os.path.join(tempfile.gettempdir(), 'test_smoke_users.db')
    if os.path.exists(test_db):
        os.remove(test_db)
    await init_users_db(test_db)
    await ensure_user(12345, 'Israel', 'israeli', test_db)
    await record_event(12345, 'start', db_path=test_db)
    await record_event(12345, 'search', query='בנק', db_path=test_db)
    await record_event(12345, 'company_view', detail='בנק הפועלים', db_path=test_db)
    await record_event(12345, 'export', detail='all', db_path=test_db)

    stats = await get_admin_stats(test_db)
    assert stats['total_users'] == 1, 'שגיאה במשתמשים'
    assert stats['total_searches'] == 1, 'שגיאה בחיפושים'
    assert stats['total_exports'] == 1, 'שגיאה בייצוא'
    assert len(stats['top_companies']) == 1, 'שגיאה בחברות מובילות'

    # בדיקת הרשאות
    assert not is_admin(999999999), 'משתמש לא מורשה זוהה כאדמין'
    if settings.admin_chat_id:
        assert is_admin(settings.admin_chat_id), 'אדמין מורשה לא זוהה'

    if os.path.exists(test_db):
        os.remove(test_db)
    print('   OK - שכבת users.db ובדיקות הרשאת admin עברו בהצלחה')

asyncio.run(test_admin())
"

echo "5/5 - הרצת הבוט בפועל (Ctrl+C לעצירה)"
echo "   מתחבר לטלגרם עם הטוקן שהוגדר ב-.env..."
exec "$VENV_PY" -m bot.main
