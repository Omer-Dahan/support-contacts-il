# 📇 Support Contacts IL

A database of customer service & support contacts for **645 Israeli companies**, plus a Telegram bot for free-text search and VCF export.

> 🇮🇱 Phone numbers, emails, WhatsApp channels, opening hours, branches and service metrics, all in one place.

---

## ✨ Features

| | |
|---|---|
| 🔍 | **Free-text search**: by company name, category, city, phone, or email |
| 📂 | Browse **21 categories** (banks, cellular, electricity, insurance, health...) |
| 📇 | **VCF export**: personal, by category or by search query, importable straight to your phone |
| 📊 | **Service metrics**: response times, answer rates, sentiment analysis from user complaints |
| 🤖 | Full company profile: phones, emails, WhatsApp, hours, branches, AI summary |
| 🛠️ | **Admin Panel**: live statistics (active users, top searches, top viewed companies, VCF exports) |
| 📢 | **Channel Link**: quick link to our Telegram bots channel across key screens |

## 🗄️ The Database

| Metric | Value |
|---|---|
| Companies | 645 |
| Phone numbers | 2,118 |
| Emails | 2,379 |
| WhatsApp channels | 408 |
| Branches | 5,556 |
| FAQs | 7,704 |

**FTS5** (SQLite) search engine with BM25 relevance scoring and full Hebrew support.

## 🤖 Telegram Bot

Built with **Telethon (MTProto) only**, no aiogram / python-telegram-bot / pyrogram.

### Bot Features
- `/start`: main menu with inline navigation (transparent buttons, in-place editing)
- Free-text search -> ranked results, 5 per page, prev/next navigation
- Full company profile + single-company VCF export
- VCF export: entire database / by category / by search query
- Channel button: direct link to the Telegram bot channel on main menu, about screen, successful export, and admin panel
- `/admin`: protected admin dashboard with real-time usage statistics (only accessible to `ADMIN_CHAT_ID`)
- User activity tracking: separate SQLite database (`data/users.db`) for user events (created automatically on first run; never modifies `sherutplus.db`)
- Per-user in-memory state (no FSM framework needed)

### Run

```bash
# 1. Environment
uv venv ~/venvs/support-bot
~/venvs/support-bot/bin/pip install -r requirements.txt

# 2. Configuration (copy from .env.example)
#    TELEGRAM_API_ID / TELEGRAM_API_HASH from my.telegram.org
#    BOT_TOKEN from @BotFather
#    ADMIN_CHAT_ID: your Telegram numeric ID (e.g. from @userinfobot)
cp .env.example .env

# 3. Smoke test
bash scripts/smoke_test.sh

# 4. Run
~/venvs/support-bot/bin/python -m bot.main
```

### Admin Configuration
To enable the `/admin` control panel:
1. Obtain your Telegram numeric user ID (e.g. by messaging `@userinfobot` or `@raw_data_bot`).
2. Add `ADMIN_CHAT_ID=your_numeric_id` to your `.env` file.
3. In Telegram, send `/admin` or `/stats` to view real-time statistics (total users, active users in 7 days, top viewed companies, search queries, VCF export breakdown).
4. Unauthorized users attempting to send `/admin` are silently ignored without exposing system details.

> **Note:** The `data/users.db` database is created automatically on first run to store user sessions and event metrics. It is excluded from version control via `.gitignore`.

## 🛠️ Tools

| Script | Purpose |
|---|---|
| `search.py` | Terminal free-text search (`python3 search.py "electricity"`) |
| `export_vcf.py` | VCF export (`--category "Banks"`, `--query`, `--slugs`, `--all`) |
| `scraper/scrape_sherutplus.py` | Scrape & refresh the database from sherutplus.com |
| `scraper/fix_ai_summary.py` | Repair/populate AI summaries and sentiment breakdowns |

## 🗂️ Project Structure

```
bot/                 Telegram bot (Telethon)
  handlers/          start, search, details, export, callbacks, admin
  users_db.py        User activity and analytics tracking (users.db)
scraper/             scraping, extraction & data repair
data/                sherutplus.db + raw data (JSONL)
research/            full market research (sources, competitors, schema)
```

## 📚 Research

The `research/` folder contains the complete market research: reliable sources, competitor comparison, recommended data schema (JSON source of truth -> VCF + bot) and refresh strategy.

---

## ⚠️ Notes

- Contact details are collected from public sources (company websites + directories). Verify against the official site before critical use.
- Every company record includes a `source_url` and verification date in the data schema.
