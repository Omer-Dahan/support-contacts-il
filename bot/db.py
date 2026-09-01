"""שכבת גישה למסד הנתונים sherutplus.db — חיפוש FTS5, קטגוריות, פרטי חברה ותיקים לייצוא VCF.

עצמאית לחלוטין (aiosqlite ישיר) ואינה תלויה בסקריפטים scraper/search.py או export_vcf.py,
אך משתמשת באותה שיטת בניית שאילתת FTS5 (הרחבת ה' הידיעה, ריבוי/הטיות) ובאותם משקלי BM25.
"""

import re
from typing import Any, Optional

import aiosqlite

PAGE_SIZE = 5
SEARCH_FETCH_LIMIT = 60

# משקלי BM25 לפי סדר העמודות המאונדקסות ב-companies_fts:
# name, legal_name, category, description, ai_summary, cities, phone_labels
_BM25_WEIGHTS = "10.0, 5.0, 5.0, 2.0, 2.0, 6.0, 3.0"

_COMPANY_LIST_SELECT = """
    SELECT
        c.id, c.slug,
        COALESCE(NULLIF(TRIM(c.name), ''), NULLIF(TRIM(c.legal_name), ''), c.slug) AS name,
        c.category,
        (SELECT COALESCE(NULLIF(clean_number, ''), number) FROM phones
            WHERE company_id = c.id ORDER BY is_primary DESC, kind = 'phone' DESC, id ASC LIMIT 1) AS primary_phone,
        (SELECT GROUP_CONCAT(DISTINCT city) FROM branches
            WHERE company_id = c.id AND city IS NOT NULL AND city != '') AS cities
    FROM companies c
"""

_DETAIL_SUBTABLES = ("phones", "emails", "whatsapp", "branches", "hours")


def _clean_hebrew(text: str) -> str:
    """מסיר ניקוד, טעמי מקרא ותווי רוחב-אפס מטקסט עברי לפני טוקניזציה."""
    if not text:
        return ""
    return re.sub(r"[\u0591-\u05C7\u200B-\u200F\uFEFF]", "", text).strip()


def _fts_variants(token: str) -> list[str]:
    variants = [token]
    if token.startswith("ה") and len(token) > 2:
        variants.append(token[1:])
    elif len(token) >= 2:
        variants.append("ה" + token)
    variants.append(f"{token}*")
    return list(dict.fromkeys(variants))


def build_fts_query(user_query: str) -> str:
    """בונה ביטוי MATCH עמיד עבור FTS5: ה' הידיעה, wildcard לריבוי/הטיות, וביטוי מדויק לרב-מילים."""
    sanitized = re.sub(r"[\"'*^:()\[\]{}+~-]", " ", _clean_hebrew(user_query))
    tokens = [t.strip() for t in sanitized.split() if t.strip()]
    if not tokens:
        return ""

    if len(tokens) == 1:
        return " OR ".join(_fts_variants(tokens[0]))

    exact_phrase = '"' + " ".join(tokens) + '"'
    parts = [exact_phrase] + ["(" + " OR ".join(_fts_variants(t)) + ")" for t in tokens]
    return " OR ".join(parts)


async def search_companies(db_path: str, query: str) -> list[dict[str, Any]]:
    """חיפוש חופשי מדורג לפי רלוונטיות (BM25). עד SEARCH_FETCH_LIMIT תוצאות."""
    fts_expr = build_fts_query(query)
    if not fts_expr:
        return []

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        sql = f"""
            {_COMPANY_LIST_SELECT}
            JOIN companies_fts fts ON fts.company_id = c.id
            WHERE fts.companies_fts MATCH ?
            ORDER BY bm25(companies_fts, {_BM25_WEIGHTS}) ASC
            LIMIT ?
        """
        try:
            cursor = await db.execute(sql, (fts_expr, SEARCH_FETCH_LIMIT))
            rows = await cursor.fetchall()
        except aiosqlite.OperationalError:
            like = f"%{query.strip()}%"
            cursor = await db.execute(
                f"{_COMPANY_LIST_SELECT} WHERE c.name LIKE ? LIMIT ?",
                (like, SEARCH_FETCH_LIMIT),
            )
            rows = await cursor.fetchall()

        return [dict(r) for r in rows]


async def get_categories(db_path: str) -> list[tuple[str, int]]:
    """רשימת קטגוריות קיימות עם מספר חברות בכל אחת, ממוין מהגדולה לקטנה."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            """
            SELECT category, COUNT(*) AS cnt FROM companies
            WHERE category IS NOT NULL AND category != ''
            GROUP BY category ORDER BY cnt DESC
            """
        )
        return [(row[0], row[1]) for row in await cursor.fetchall()]


async def get_companies_by_category(db_path: str, category: str) -> list[dict[str, Any]]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"{_COMPANY_LIST_SELECT} WHERE c.category = ? ORDER BY c.name ASC",
            (category,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def get_company_details(db_path: str, slug: str) -> Optional[dict[str, Any]]:
    """תיק חברה מלא: פרטי בסיס + כל הטלפונים/מיילים/וואטסאפ/סניפים/שעות/שאלות נפוצות."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM companies WHERE slug = ?", (slug,))
        row = await cursor.fetchone()
        if not row:
            return None

        company = dict(row)
        cid = company["id"]

        cursor = await db.execute(
            "SELECT * FROM phones WHERE company_id = ? ORDER BY is_primary DESC, id ASC", (cid,)
        )
        company["phones"] = [dict(r) for r in await cursor.fetchall()]

        for table in ("emails", "whatsapp", "branches", "hours"):
            cursor = await db.execute(f"SELECT * FROM {table} WHERE company_id = ?", (cid,))
            company[table] = [dict(r) for r in await cursor.fetchall()]

        return company


async def get_companies_for_export(
    db_path: str,
    *,
    category: Optional[str] = None,
    query: Optional[str] = None,
    all_companies: bool = False,
) -> list[dict[str, Any]]:
    """שולף תיקים מלאים (חברה + כל טבלאות הבת) התואמים לסינון, עבור בניית VCF."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row

        if category:
            cursor = await db.execute(
                "SELECT * FROM companies WHERE category = ? ORDER BY name", (category,)
            )
        elif query:
            fts_expr = build_fts_query(query)
            if not fts_expr:
                return []
            cursor = await db.execute(
                f"""
                SELECT c.* FROM companies c
                JOIN companies_fts fts ON fts.company_id = c.id
                WHERE fts.companies_fts MATCH ?
                ORDER BY bm25(companies_fts, {_BM25_WEIGHTS}) ASC
                """,
                (fts_expr,),
            )
        elif all_companies:
            cursor = await db.execute("SELECT * FROM companies ORDER BY name")
        else:
            return []

        companies = [dict(r) for r in await cursor.fetchall()]

        for comp in companies:
            cid = comp["id"]
            for table in _DETAIL_SUBTABLES:
                sub_cursor = await db.execute(f"SELECT * FROM {table} WHERE company_id = ?", (cid,))
                comp[table] = [dict(r) for r in await sub_cursor.fetchall()]

        return companies
