# Parivahan eChallan Telegram Bot

Cloud-deployable Telegram automation bot built with **Python 3.11+**, **`python-telegram-bot` (v22+ async)**, and **Playwright (async)**. Keeps an active Playwright `BrowserContext` and `Page` in `context.user_data` across conversation states so Parivahan session cookies persist from vehicle lookup through sequential PDF receipt downloads.

## Project Structure

| File | Responsibility |
| :--- | :--- |
| `bot.py` | Async Telegram `ConversationHandler` (`WAITING_FOR_VEHICLE` -> `WAITING_FOR_CAPTCHA_LIST` -> `WAITING_FOR_CAPTCHA_PRINT`), inline buttons, 180s inactivity timeout cleanup, and `aiohttp` port `8080` health server. |
| `browser_manager.py` | Async Playwright Chromium controller with stealth masking (`navigator.webdriver`), `1366x768` viewport, Windows Chrome UA, optional `PROXY_URL`, dynamic HTML table parser, and multi-strategy PDF capture (`/tmp/<CHALLAN_NO>.pdf`). |
| `dom_selectors.py` | Centralized primary and fallback CSS/text selectors for `/index/accused-challan` and `/index/challan-print`. |
| `Dockerfile` | Container definition based on `mcr.microsoft.com/playwright/python:v1.58.0-noble` with pre-installed Chromium and Linux dependencies. |
| `requirements.txt` | Python dependencies (`python-telegram-bot>=22.8`, `playwright==1.58.0`, `aiohttp`, `python-dotenv`). |
| `.env.example` | Environment variable template. |

---

## Prerequisites

1. **Create a Telegram Bot**
   - Open Telegram and message `@BotFather`.
   - Send `/newbot`, choose a name and username, and copy the resulting **HTTP API Token** (`TELEGRAM_BOT_TOKEN`).
2. **Find Your Numeric Telegram User ID**
   - Message `@userinfobot` on Telegram and copy your numeric `Id` for `ALLOWED_USER_IDS`.

---

## Step-by-Step Deployment: AI Studio -> GitHub -> Railway

### Step 1: Sync This Project from AI Studio to GitHub

1. In Google AI Studio, click **Save to GitHub** (or export the project archive and initialize a local Git repo).
2. Create a new **Private** GitHub repository (e.g. `parivahan-echallan-bot`) and push the files (`bot.py`, `browser_manager.py`, `dom_selectors.py`, `Dockerfile`, `requirements.txt`, `.env.example`, `README.md`).
3. Verify `.env` is listed in `.gitignore` and never committed to GitHub.

### Step 2: Deploy Automatically to Railway via Docker

1. Sign in to [Railway](https://railway.app/) with your GitHub account.
2. Click **New Project** -> **Deploy from GitHub repo** and select your `parivahan-echallan-bot` repository.
3. Railway automatically detects the root `Dockerfile` and builds the container using `mcr.microsoft.com/playwright/python:v1.58.0-noble` (no manual `playwright install` step required).
4. Open the service **Variables** tab and configure:

| Variable | Value | Notes |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | `123456:ABC...` | Bot token from `@BotFather` |
| `ALLOWED_USER_IDS` | `123456789` | Comma-separated authorized Telegram numeric user IDs |
| `HEADLESS_MODE` | `true` | Must remain `true` in headless cloud containers |
| `PROXY_URL` | *(optional)* | Indian residential/HTTP proxy if Parivahan blocks non-IN cloud IPs |
| `PORT` | `8080` | Matches the `aiohttp` health server and `EXPOSE 8080` |

5. Open **Settings -> Networking / Healthcheck**:
   - Set **Healthcheck Path** to `/health`.
   - Railway polls `GET /health` on port `8080` and keeps the container alive continuously.
6. Click **Deploy** (or push any commit to `main` for automatic redeploys).

### Alternative Cloud Hosts (Render & Koyeb)

- **Render**: Create a **New Web Service**, connect your GitHub repo, select **Runtime: Docker**, set **Health Check Path** to `/health`, and add the same environment variables (`PORT=8080`).
- **Koyeb**: Create a **New Web Service**, choose **GitHub**, select **Builder: Dockerfile**, expose port `8080`, set HTTP health check path to `/health`, and configure the environment variables.

---

## Local Docker Testing

```bash
cp .env.example .env
# Edit .env with your TELEGRAM_BOT_TOKEN and ALLOWED_USER_IDS

docker build -t parivahan-echallan-bot .
docker run --rm --env-file .env -p 8080:8080 parivahan-echallan-bot
```

Verify the health endpoint in another terminal:

```bash
curl http://localhost:8080/health
# {"status": "ok", "service": "parivahan-echallan-bot"}
```

---

## Bot Usage

1. Send `/start` (or `/check OD02AB1234`) to your bot in Telegram.
2. Enter a vehicle registration number (e.g. `OD02AB1234`).
3. Reply with the CAPTCHA image text (or tap **Refresh CAPTCHA** / **Cancel**).
4. Receive a full-page screenshot of the pending challans table.
5. For each pending challan `Challan [1/N]: <CHALLAN_NO>`, reply with the print-page CAPTCHA to receive `<CHALLAN_NO>.pdf` directly in your chat.
6. Temporary files in `/tmp` are deleted immediately after upload, and Chromium is closed automatically upon completion, `/cancel`, or after 180 seconds of inactivity.

---

## Troubleshooting `net::ERR_CONNECTION_RESET`

`echallan.parivahan.gov.in` is hosted on NIC India infrastructure and frequently drops TCP connections (`net::ERR_CONNECTION_RESET`) from non-Indian or cloud datacenter IP ranges (including Railway US/EU/Singapore regions).

- `browser_manager.py` automatically disables HTTP/2 & QUIC (`--disable-http2`, `--disable-quic`), launches full Chromium (`--headless=new`), and retries transient resets with root-origin cookie warm-up.
- If resets persist from your cloud region, configure an **Indian residential/ISP HTTP or SOCKS5 proxy** in your Railway/Render/Koyeb Variables:
  - `PROXY_URL=http://username:password@indian-proxy-host:port`

