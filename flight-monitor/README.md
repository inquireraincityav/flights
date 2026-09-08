# Flight Price Monitor — YVR → BOM

Automated flight price monitoring system for round-trip flights from Vancouver (YVR) to Mumbai (BOM). Continuously searches multiple airlines and OTAs, evaluates baggage-inclusive pricing, tracks historical trends, and sends real-time Telegram alerts when good deals appear.

## What It Does

- Monitors **6 flight sources**: Google Flights, Skyscanner, CheapOair, Air Canada, Air India, Cathay Pacific
- Searches **15 date combinations** (Dec 11–15, 2026 → Jan 3–5, 2027)
- Evaluates **baggage-inclusive pricing** (at least 1 checked bag required)
- Compares **airline-direct vs. third-party** prices
- Sends **Telegram alerts** for deals in your target range (CAD $1,800–$2,600)
- Tracks **price history** and detects drops, trends, and historical lows
- Provides a **web dashboard** with date matrix, filters, and provider health
- Runs **continuously** with configurable check intervals

## Requirements

- Python 3.12+
- Chromium browser (installed via Playwright)
- Telegram Bot (for notifications)
- Internet connection

## Quick Start

### 1. Clone and Set Up Python Environment

```bash
cd flight-monitor
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

### 2. Install Playwright Browser

```bash
playwright install chromium
```

### 3. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings. The most important ones are the Telegram credentials.

### 4. Set Up Telegram Bot

#### Create the Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., "YVR BOM Flight Monitor")
4. Choose a username (e.g., `yvr_bom_flight_bot`)
5. BotFather will give you a **bot token** — copy it

#### Get Your Chat ID

1. Send any message to your new bot in Telegram
2. Open this URL in your browser (replace `YOUR_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. Find `"chat":{"id":XXXXXXXX}` in the response — that number is your **Chat ID**

#### Add to `.env`

```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=123456789
```

### 5. Initialize Database

```bash
python main.py --init-db
```

### 6. Test Telegram

```bash
python main.py --test-alert
```

You should receive a test message in Telegram.

### 7. Test a Provider

```bash
python main.py --test-provider google_flights
python main.py --test-provider air_canada
python main.py --test-provider air_india
python main.py --test-provider cathay_pacific
python main.py --test-provider skyscanner
python main.py --test-provider cheapoair
```

### 8. Run First Scan

```bash
python main.py --check-now
```

This runs one complete scan across all providers and date combinations.

### 9. Run Continuously

```bash
python main.py
```

The monitor will scan every 4 hours (configurable) and send alerts automatically.

### 10. Start Dashboard

```bash
python main.py --dashboard
```

Open http://localhost:8080 in your browser.

## Commands

| Command | Description |
|---------|-------------|
| `python main.py` | Start continuous monitoring |
| `python main.py --check-now` | Run one immediate scan |
| `python main.py --daily-summary` | Send daily summary to Telegram |
| `python main.py --test-alert` | Send test Telegram notification |
| `python main.py --test-provider NAME` | Test a single provider |
| `python main.py --dashboard` | Start web dashboard |
| `python main.py --init-db` | Initialize/reset database |

## Docker

### Build and Run

```bash
docker-compose up -d
```

This starts the monitor with automatic restarts. The SQLite database is persisted via a Docker volume.

### View Logs

```bash
docker-compose logs -f flight-monitor
```

### Dashboard Only

```bash
docker-compose --profile dashboard-only up -d dashboard
```

## VPS Deployment

1. SSH into your VPS
2. Install Docker and Docker Compose
3. Clone the repo and create `.env`
4. Run `docker-compose up -d`
5. The monitor runs 24/7 with automatic restarts

## Configuration

All settings are in `.env`. Key ones:

| Setting | Default | Description |
|---------|---------|-------------|
| `ORIGIN` | YVR | Departure airport |
| `DESTINATION` | BOM | Arrival airport |
| `DEPARTURE_START` | 2026-12-11 | First departure date |
| `DEPARTURE_END` | 2026-12-15 | Last departure date |
| `RETURN_START` | 2027-01-03 | First return date |
| `RETURN_END` | 2027-01-05 | Last return date |
| `PASSENGERS` | 1 | Number of passengers |
| `CABIN_CLASS` | economy | Cabin class |
| `MIN_TARGET_PRICE_CAD` | 1800 | Lower target price |
| `MAX_TARGET_PRICE_CAD` | 2600 | Upper target price |
| `CHECK_INTERVAL_HOURS` | 4 | Hours between scans |
| `ALERT_COOLDOWN_HOURS` | 24 | Min hours between same alert |
| `MAX_STOPS` | 2 | Maximum stops per direction |
| `DIRECT_BOOKING_PREMIUM_CAD` | 100 | Premium threshold for preferring airline-direct |

## Deal Tiers

| Tier | Price Range | Alert Level |
|------|-------------|-------------|
| 🔥 INSANE | Under $1,800 | Highest priority — immediate alert |
| 🟣 EXCELLENT | $1,800–$2,099 | High priority |
| 🟢 GREAT | $2,100–$2,299 | Standard alert |
| 🔵 GOOD | $2,300–$2,600 | Standard alert |

## Provider Limitations

| Provider | Method | Status | Notes |
|----------|--------|--------|-------|
| Google Flights | Playwright | Working | Best aggregator; page structure may change |
| Skyscanner | Playwright | May be blocked | Anti-bot protections may prevent access |
| CheapOair | Playwright | May be blocked | Anti-bot protections may prevent access |
| Air Canada | Playwright | Working | Direct booking; no checked bag in basic economy |
| Air India | Playwright | Working | Direct booking; 2×23kg bags included |
| Cathay Pacific | Playwright | Working | Direct booking; 1×23kg bag included |

All providers use Playwright browser automation. Airline websites may change their structure or block automated access. The system handles failures gracefully — a single provider failure never crashes the overall scan.

## Adding a New Provider

1. Create `providers/your_provider.py`
2. Extend `BaseProvider`
3. Implement `search_flights()` returning `List[FlightOffer]`
4. Register in `main.py`'s `create_monitor()` function

```python
from providers.base import BaseProvider, FlightOffer, FlightLeg

class YourProvider(BaseProvider):
    name = "your_provider"
    website = "https://example.com"
    is_airline_direct = False

    async def search_flights(self, origin, destination, departure_date, return_date, passengers=1, cabin="economy"):
        # Your implementation
        return [FlightOffer(...)]
```

## Updating for Another Trip

Edit `.env`:

```
ORIGIN=YYZ
DESTINATION=LHR
DEPARTURE_START=2027-03-01
DEPARTURE_END=2027-03-05
RETURN_START=2027-03-15
RETURN_END=2027-03-18
```

Then restart the monitor. The date combinations are generated automatically.

## Adjusting Price Targets

Edit `.env`:

```
MIN_TARGET_PRICE_CAD=1500
MAX_TARGET_PRICE_CAD=2200
INSANE_DEAL_MAX_CAD=1499
EXCELLENT_DEAL_MAX_CAD=1799
GREAT_DEAL_MAX_CAD=1999
GOOD_DEAL_MAX_CAD=2200
```

## Troubleshooting

**"Telegram not configured"**
→ Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

**"Provider X: access blocked"**
→ The website is blocking automated access. This is expected for some providers. Other providers will continue working.

**"No results from any provider"**
→ Check your internet connection. Run `python main.py --test-provider google_flights` to debug.

**"playwright install" fails**
→ Run `playwright install-deps chromium` first to install system dependencies.

**Dashboard shows no data**
→ Run `python main.py --check-now` first to populate the database.

## Running Tests

```bash
cd flight-monitor
pytest tests/ -v
```

## Project Structure

```
flight-monitor/
├── main.py                 # Entry point
├── config.py               # Configuration from .env
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container build
├── docker-compose.yml      # Container orchestration
├── providers/              # Flight search providers
│   ├── base.py             # Base provider interface
│   ├── google_flights.py   # Google Flights (Playwright)
│   ├── skyscanner.py       # Skyscanner (Playwright)
│   ├── cheapoair.py        # CheapOair (Playwright)
│   ├── air_canada.py       # Air Canada direct
│   ├── air_india.py        # Air India direct
│   └── cathay_pacific.py   # Cathay Pacific direct
├── database/               # SQLite persistence
│   ├── models.py           # SQLAlchemy models
│   └── database.py         # Session management & queries
├── notifications/          # Alert delivery
│   └── telegram.py         # Telegram Bot API
├── services/               # Business logic
│   ├── monitor.py          # Main orchestrator
│   ├── price_analysis.py   # Trend detection
│   ├── baggage.py          # Baggage evaluation
│   ├── ranking.py          # Deal scoring
│   ├── currency.py         # FX conversion
│   ├── deduplication.py    # Alert cooldowns
│   └── verification.py     # Booking verification
├── dashboard/              # FastAPI web UI
│   ├── app.py              # API endpoints
│   └── templates/          # HTML templates
├── utils/                  # Shared utilities
│   ├── dates.py            # Date generation
│   ├── fingerprints.py     # Itinerary hashing
│   ├── logging.py          # Log configuration
│   └── time.py             # Timezone helpers
├── tests/                  # Test suite
│   └── test_core.py        # Core functionality tests
└── data/                   # SQLite database (gitignored)
    └── flights.db
```
