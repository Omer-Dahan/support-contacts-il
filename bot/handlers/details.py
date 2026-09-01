import html
import re

from telethon.tl.custom import Button

MAX_PHONES_SHOWN = 8
MAX_CITIES_SHOWN = 6
MAX_SUMMARY_CHARS = 350


def _normalize_whitespace(text: str) -> str:
    """מחליף רווחים/ירידות שורה מרובות ברווח בודד ומנקה קצוות."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _is_broken_ai_summary(text: str | None) -> bool:
    """בודק אם סיכום ה-AI שבור או חלקי (ללא נתוני אחוזים/גרף)."""
    if not text:
        return True
    cleaned = _normalize_whitespace(text)
    # אם השבר מכיל כותרת פילוח רגשות ללא נתוני אחוזים
    if "פילוח רגשות" in cleaned and "%" not in cleaned:
        return True
    if "מבוסס על" in cleaned and "פילוח" in cleaned and "%" not in cleaned:
        return True
    if cleaned.startswith("📊") and "%" not in cleaned and len(cleaned) < 300:
        return True
    if cleaned.endswith("פילוח רגשות של לקוחות על פי סוג פנייה:"):
        return True
    return False


def _format_phone(p: dict) -> str:
    number = _normalize_whitespace(p.get("clean_number") or p.get("number") or "")
    label = _normalize_whitespace(p.get("label") or p.get("purpose") or "")
    icon = "📠" if p.get("kind") == "fax" else "📞"
    suffix = f" ({html.escape(label)})" if label else ""
    return f"{icon} {number}{suffix}"


def render_company_details(company: dict) -> tuple[str, list]:
    """מרנדר מסך פרטי חברה מלא: טלפונים, מיילים, וואטסאפ, שעות, סניפים, אתר וסיכום AI / description."""
    raw_name = company.get("name") or company.get("legal_name") or company.get("slug") or "ללא שם"
    name = html.escape(_normalize_whitespace(raw_name))
    lines = [f"🏢 <b>{name}</b>"]

    if company.get("category"):
        cat_clean = html.escape(_normalize_whitespace(company["category"]))
        lines.append(f"📁 {cat_clean}")

    phones = company.get("phones") or []
    if phones:
        lines.append("")
        for p in phones[:MAX_PHONES_SHOWN]:
            num = _normalize_whitespace(p.get("clean_number") or p.get("number") or "")
            if num:
                lines.append(_format_phone(p))
        if len(phones) > MAX_PHONES_SHOWN:
            lines.append(f"   ועוד {len(phones) - MAX_PHONES_SHOWN} מספרים")

    emails = company.get("emails") or []
    if emails:
        lines.append("")
        for e in emails[:5]:
            em = _normalize_whitespace(e.get("email") or "")
            if em:
                lines.append(f"✉️ {html.escape(em)}")

    whatsapp = company.get("whatsapp") or []
    if whatsapp:
        lines.append("")
        for w in whatsapp[:3]:
            contact = _normalize_whitespace(w.get("phone") or w.get("url") or "")
            if contact:
                lines.append(f"💬 {html.escape(contact)}")

    hours = company.get("hours") or []
    if hours:
        lines.append("")
        for h in hours[:3]:
            text = h.get("raw_text") or f"{h.get('days', '')}: {h.get('opens', '')}-{h.get('closes', '')}"
            text_clean = _normalize_whitespace(text)
            if text_clean:
                lines.append(f"🕐 {html.escape(text_clean)}")

    branches = company.get("branches") or []
    cities = sorted({_normalize_whitespace(b["city"]) for b in branches if b.get("city") and _normalize_whitespace(b["city"])})
    if cities:
        shown = ", ".join(cities[:MAX_CITIES_SHOWN])
        more = f" ועוד ({len(branches)} סניפים ב-{len(cities)} ערים)" if len(cities) > MAX_CITIES_SHOWN else f" ({len(branches)} סניפים)"
        lines.append(f"\n📍 {html.escape(shown)}{more}")

    if company.get("website_url"):
        web_url = company["website_url"].strip()
        lines.append(f"\n🌐 {web_url}")

    # בדיקת תקינות ai_summary ונפילה ל-description במידת הצורך
    ai_sum = company.get("ai_summary")
    if ai_sum and not _is_broken_ai_summary(ai_sum):
        summary = _normalize_whitespace(ai_sum)
    else:
        summary = _normalize_whitespace(company.get("description") or "")

    if summary:
        if len(summary) > MAX_SUMMARY_CHARS:
            summary = summary[:MAX_SUMMARY_CHARS] + "..."
        lines.append(f"\n🤖 {html.escape(summary)}")

    buttons = [
        [Button.inline("⬇️ הורד VCF לחברה זו", data=f"exp:one:{company['slug']}".encode("utf-8"))],
        [Button.inline("↩️ חזרה לתוצאות", data=b"nav:back_to_list")],
        [Button.inline("🏠 תפריט ראשי", data=b"menu:main")],
    ]

    return "\n".join(lines), buttons
