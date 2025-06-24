from betfairlightweight import APIClient, filters
from datetime import datetime, timedelta

# ─── CONFIG ────────────────────────────────────────────────────────────────────
USERNAME      = "omchandel1703@gmail.com"
PASS          = "Hacker@0&7"
APP_KEY       = "mYG3sroDGCREEKrb"     # your 1.0-DELAY key
CERT_PATH     = "client-2048.crt"      # downloaded from Betfair dev portal
KEY_PATH      = "client-2048.key"      # downloaded from Betfair dev portal

DATE_RAW      = "6/13/2025 17:02"      # your sample row
VENUE         = "WARRAGUL"
RACE_NO       = 7
EVENT_TYPE_ID = ["7"]                 # 7 = Horse Racing
COUNTRY       = ["AU"]                # Australia

# ─── LOGIN ─────────────────────────────────────────────────────────────────────
client = APIClient(
    username=USERNAME,
    password=PASS,
    app_key=APP_KEY,
    certs=(CERT_PATH, KEY_PATH),
)
client.login()  # certificate‑based SSO login
print("✅ Logged in with cert‑based SSO")

# ─── BUILD DATE RANGE ──────────────────────────────────────────────────────────
dt = datetime.strptime(DATE_RAW, "%m/%d/%Y %H:%M")
start = dt.replace(hour=0, minute=0, second=0).isoformat() + "Z"
end   = dt.replace(hour=23, minute=59, second=59).isoformat() + "Z"

# ─── FIND THE CORRECT MARKET ───────────────────────────────────────────────────
mc = client.betting.list_market_catalogue(
    filter=filters.market_filter(
        event_type_ids=EVENT_TYPE_ID,
        market_countries=COUNTRY,
        market_start_time={"from": start, "to": end},
        text_query=VENUE,
        bsp_only=True
    ),
    market_projection=["MARKET_DEFINITION", "MARKET_START_TIME"],
    max_results="100"
)

# Narrow down to race #7
markets = [m for m in mc if m.market_name.upper().endswith(f" RACE {RACE_NO} WIN")]
if not markets:
    raise SystemExit(f"❌ No market found for {VENUE} Race {RACE_NO} on {start[:10]}")
market_id = markets[0].market_id
print(f"✅ Found market: {markets[0].market_name} (ID: {market_id})")

# ─── FETCH BSP DATA ────────────────────────────────────────────────────────────
book = client.betting.list_market_book(
    market_ids=[market_id],
    price_projection=filters.price_projection(price_data=["SP_AVAILABLE","SP_TRADED"])
)[0]

print(f"\nRunner BSP Prices for {markets[0].market_name}:")
for runner in book.runners:
    name       = runner.runner_name
    sp_traded  = getattr(runner.sp, "actualSP", None)
    sp_av_back = runner.sp.available_to_back[0].price if runner.sp.available_to_back else None
    bsp_price  = sp_traded or sp_av_back or "N/A"
    print(f" • {name:20s} → BSP = {bsp_price}")

# ─── LOGOUT (optional) ─────────────────────────────────────────────────────────
client.logout()
