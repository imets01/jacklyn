# Jacklyn

Self-hosted, multi-broker wealth & portfolio tracker. Named after the *Alocasia Jacklyn*: a portfolio
starts as a small corm and, with care and structure, compounds into organic growth.

Jacklyn pulls statements from any broker into one exact-decimal ledger, values it live in CHF, EUR, HUF
or USD, and tracks TBSZ vintages alongside regular and Swiss accounts.

## Quick start

### Docker (one command, also for Proxmox)

```bash
cp .env.example .env              # optional, defaults work
docker compose up -d --build
```

Open <http://localhost:8080>. Data lives in the `jacklyn-data` volume (SQLite). For PostgreSQL, set
`DATABASE_URL=postgresql+psycopg://jacklyn:<password>@postgres:5432/jacklyn` and `POSTGRES_PASSWORD`
in `.env`, then `docker compose --profile postgres up -d --build`.

### Local development (hot reload)

Requires Python 3.12 and Node 22+.

```powershell
.\scripts\setup.ps1     # venv + pip + npm ci  (macOS/Linux: ./scripts/setup.sh)
.\scripts\dev.ps1       # API :8000 (reload) + UI :5173 (HMR)  (./scripts/dev.sh)
.\scripts\check.ps1     # ruff, mypy --strict, pytest, oxlint, tsc + vite build  (./scripts/check.sh)
```

Containerized hot reload instead: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`.

API docs: <http://localhost:8000/docs>. On first start the app migrates the database, creates the admin
account waiting to be claimed (see Security) and seeds a demo portfolio (IBKR Swiss, IBKR TBSZ 2025, Lightyear, Erste NetBroker) so the dashboard
is alive immediately. Set `JACKLYN_SEED_DEMO_DATA=false` for a clean install.

## Security & sharing

Jacklyn is built to be shared with a few trusted people without exposing your server:

- **Invite-only accounts.** On first start the server logs a one-time *setup token*; whoever enters it creates
  the admin account. Everyone else joins through single-use invite links from **Settings → People**.
  There is no public sign-up.
- **Strong sign-in.** Passwords are hashed with Argon2id. Sessions are random tokens in `HttpOnly`/`SameSite`
  cookies, stored only as hashes. Accounts lock after repeated failures, addresses are throttled, two-step codes
  (TOTP) are optional, and you can sign out other devices.
- **Isolation.** Every query is scoped to the signed-in user, and tests prove one user can't read or change
  another's data. Admins manage accounts, not portfolios.
- **Defence in depth.** CSRF header + origin checks, a strict Content-Security-Policy, `no-store` on all API
  responses, and 2FA secrets and broker tokens encrypted at rest. Containers run non-root with read-only
  filesystems and no capabilities, and the UI is published on `127.0.0.1` only by default.
- **Sharing with friends:** see [docs/cloudflare-tunnel.md](docs/cloudflare-tunnel.md). It covers a shareable
  link with no open ports, behind Cloudflare Access plus Jacklyn's own login.
- **Locked out?** Run `docker compose exec backend python -m app.cli reset-link you@example.com`.

## How it works

```
 file upload ─┐                               ┌─ IBKR Flex Web Service (sync client)
 (CSV/XLSX/   │   Tier 1 presets              │
  XLS/XML)    ├─► IBKR · Lightyear · Erste ──┐│
              │   Tier 2 Universal Column     ├┴─► StandardTransaction ─► ingest_transactions()
              └─► Mapper (saved presets) ────┘     (Pydantic, Decimal)    · SHA-256 + broker-ID dedup
                                                                         · asset resolution
                                                                         · ImportLog
                                       PortfolioEngine ◄─ transactions + asset_prices + fx_rates
                                       (avg cost, P&L, history)          ▲ yfinance (cached, background)
```

- **Parsers** (`backend/app/parsers/`) implement `BaseBrokerParser.detect() / parse() / normalize()`.
  `GenericCSVParser` takes a JSON `ColumnMappingConfig` (columns, date format, decimal separator,
  type-value map, defaults), so any tabular statement imports without new code. The Lightyear and Erste
  presets are themselves alias-based mapping configs on top of it.
- **File handling**: encoding detection (UTF-8/16, cp1250 with a Hungarian ő/ű fix), delimiter sniffing,
  `1,234.56` vs `1.234,56` vs `1'234.50` detection, title/preamble rows skipped, `.xlsx`, `.xls`, and the
  HTML tables some banks ship as `.xls`.
- **Dedup**: every row gets a deterministic SHA-256 of its normalized content (with an occurrence index so
  two identical trades in one file both survive). Rows carrying a broker ID are also matched on it.
  Re-importing a file or an overlapping date range is always safe.
- **Ingestion is decoupled from uploads**: `ingest_transactions()` takes `StandardTransaction`s from any
  producer — the seeder, file imports and the IBKR Flex sync (`services/sync/`) all use it.
- **IBKR sync**: connect a read-only Flex token + query ID on the Import page. "Sync now" and a daily
  auto-sync fetch one Flex statement and route each IBKR account (U-number) to the Jacklyn account with that
  broker account ID; unknown accounts are listed for linking. The token is encrypted at rest and never
  returned by the API.
- **Money is never a float**: `Decimal` everywhere in Python; `NUMERIC(28,10)` on PostgreSQL and exact
  text storage on SQLite (whose NUMERIC silently degrades to REAL). Floats are rejected at the column level.
- **Multi-user**: every user-owned table has `user_id`, and every API query is scoped to the signed-in user
  (`app/api/deps.py`). Assets, prices and FX rates are shared reference data.
- **Valuation**: average-cost basis converted to the base currency at each transaction's own date, so P&L
  includes currency effects. Live quotes and FX come from yfinance in a background thread (15 min TTL) and
  are cached in `asset_prices` / `fx_rates`; the app keeps working offline from the cache.
- **Asset profiles & logos**: the same refresh fills `asset_profiles` (fund issuer, TER, sector, description)
  and downloads one logo per company or fund issuer into `asset_logos`. Browsers only ever load logos from
  `/api/assets/{id}/logo` and `/api/logos/{key}` (flags, currency badges), so the CSP stays `img-src 'self'`
  and no third party learns what anyone holds.
  Sources, best first: [Elbstream](https://elbstream.com) by ISIN (plus its commodity, crypto and currency
  tiles; credited in the UI), then the company or fund issuer's website icon via Google. SVGs are stored only if they are plain drawings (no script,
  event handlers or external references). Without any image the UI draws flags, a metal bar or initials.
- **Portfolio Health**: a deterministic rules engine (`backend/app/health/`). Rules, thresholds and their
  cited sources live in `backend/app/health/data/rules.toml`; the MSCI ACWI benchmark weights and the
  fund-index → country mapping in `benchmarks.toml` (update both from the cited factsheets). With
  `JACKLYN_EULERPOOL_TOKEN` set, funds use their real country mix and full holdings from
  [Eulerpool](https://eulerpool.com) instead; the index mapping is then only a fallback. The rebalancing
  assistant spends new money only (no sells) and is covered by unit tests in `tests/test_health.py`.
- **TBSZ**: account type `tbsz` with a vintage `tbsz_year`; the UI shows the lock-up (10% rate after three
  years, tax-free after five, counted from 1 January after the collection year).

## API

| Method | Path | |
|---|---|---|
| GET | `/api/portfolio/summary?base=CHF` | Net worth, day & all-time P&L, allocations, accounts, market status |
| GET | `/api/portfolio/history?range=1Y&base=CHF[&account_id=]` | Value vs. net invested series |
| GET | `/api/portfolio/holdings?base=CHF[&account_id=]` | Positions and cash balances |
| GET | `/api/portfolio/holdings/{asset_id}?base=CHF` | One asset across accounts: position, fund/company info, activity |
| GET | `/api/assets/{asset_id}/chart?range=1D…MAX` · `/api/assets/{asset_id}/logo` · `/api/logos/{key}` | Price chart (Yahoo, cached in memory), cached asset logo, country flag or currency badge |
| GET/POST | `/api/accounts` · GET/PATCH/DELETE `/api/accounts/{id}` | Accounts with valuation; TBSZ rules enforced |
| GET | `/api/transactions?account_id=&type=&asset_id=&q=&date_from=&date_to=` | Ledger across accounts with filters (search matches symbol, name, ISIN, note) |
| PUT/GET | `/api/health/profile` · `/api/health/report?base=&amount=&include_cash=` | Investor profile; Portfolio Health report (breakdowns, rule findings with citations, score, rebalancing plan) |
| POST | `/api/import/preview` (multipart) | Detect → parse → normalized rows with duplicate flags, or a table preview for the column mapper |
| POST | `/api/import/commit` | Idempotently store selected `StandardTransaction`s |
| GET | `/api/import/logs` | Import history |
| GET/POST/DELETE | `/api/mappings` | Saved column-mapper presets (auto-applied by header signature) |
| POST | `/api/market/refresh` | Force a quote/FX refresh |
| GET/PUT/DELETE | `/api/sync/ibkr` · POST `/api/sync/ibkr/run` | IBKR Flex connection (token write-only); start a background sync |
| GET/PATCH | `/api/me` | Signed-in user & base currency |

## Repository layout

```
backend/   FastAPI app (app/), Alembic migrations, tests + statement fixtures
frontend/  React 19 + TypeScript + Vite + Tailwind v4 + Recharts + TanStack Query
scripts/   setup / dev / check for PowerShell and bash
```
