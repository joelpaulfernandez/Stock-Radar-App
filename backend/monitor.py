"""
Canada Government Contract News Monitor
========================================
Monitors Canadian news RSS feeds for government contract announcements
that could move publicly-traded stock prices.

Reads credentials from environment variables (set as GitHub Secrets).
Tracks seen articles via seen_articles.json (cached between runs by GitHub Actions).
"""

import feedparser
import requests
import smtplib
import re
import json
import os
import hashlib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
#  CONFIG — credentials come from GitHub Secrets
# ─────────────────────────────────────────────

EMAIL_CONFIG = {
    "sender":      os.environ.get("EMAIL_SENDER",    ""),
    "password":    os.environ.get("EMAIL_PASSWORD",  ""),
    "recipient":   os.environ.get("EMAIL_RECIPIENT", ""),
    "smtp_server": "smtp.gmail.com",
    "smtp_port":   587,
}

# Minimum contract value (in millions CAD/USD) to trigger an alert
# $50M+ moves mid-caps, $500M+ moves large-caps like Bombardier, CAE
MIN_CONTRACT_VALUE_MILLIONS = 50

# How far back to look in feed entries (hours) — matches cron interval
LOOKBACK_HOURS = 4

SEEN_ARTICLES_FILE = os.path.join(os.path.dirname(__file__), "seen_articles.json")

# ─────────────────────────────────────────────
#  NEWS SOURCES
# ─────────────────────────────────────────────

RSS_FEEDS = [
    # ── CANADA ──────────────────────────────────────────────────────────────
    # Best source — corporate press releases land here first (full text, free)
    {"name": "🇨🇦 CNW Group / Newswire.ca",  "url": "https://www.newswire.ca/rss/news.rss",          "country": "CA"},

    # Government press releases (official, always free full text)
    {"name": "🇨🇦 Canada.ca News Releases",   "url": "https://www.canada.ca/en/news/advanced-news-search/news-results.atom?typ=pressReleases&start=0", "country": "CA"},
    {"name": "🇨🇦 National Defence",          "url": "https://www.canada.ca/en/department-national-defence/news/advanced-news-search/news-results.atom?start=0", "country": "CA"},
    {"name": "🇨🇦 PSPC (Procurement)",        "url": "https://www.canada.ca/en/public-services-procurement/news/advanced-news-search/news-results.atom?start=0", "country": "CA"},
    {"name": "🇨🇦 Transport Canada",          "url": "https://www.canada.ca/en/transport-canada/news/advanced-news-search/news-results.atom?start=0", "country": "CA"},
    {"name": "🇨🇦 Infrastructure Canada",     "url": "https://www.canada.ca/en/office-infrastructure/news/advanced-news-search/news-results.atom?start=0", "country": "CA"},

    # ── UNITED STATES ───────────────────────────────────────────────────────
    # DoD contract digest — drops daily ~5pm ET, exact dollar values, always free
    {"name": "🇺🇸 Defense.gov Contracts",     "url": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=945&max=20", "country": "US"},
    # DoD news releases (catches announcements before the contract digest)
    {"name": "🇺🇸 Defense.gov News",          "url": "https://www.defense.gov/DesktopModules/ArticleCS/RSS.ashx?ContentType=1&Site=970&max=20", "country": "US"},
    # US corporate press releases — same role as CNW for Canada
    {"name": "🇺🇸 PR Newswire (Gov/Defence)", "url": "https://www.prnewswire.com/rss/news-releases-list.rss", "country": "US"},
    {"name": "🇺🇸 Business Wire",             "url": "https://feed.businesswire.com/rss/home/?rss=G7", "country": "US"},
    # SEC EDGAR 8-K filings — material contracts legally required within 4 business days
    {"name": "🇺🇸 SEC EDGAR 8-K Filings",    "url": "https://efts.sec.gov/LATEST/search-index?q=%22material+contract%22+%22government%22&dateRange=custom&startdt={lookback}&forms=8-K&hits.hits._source=period_of_report,display_date_filed,entity_name,file_num,period_of_report,biz_location,inc_states&hits.hits.highlight.file_date=true", "country": "US"},
    # NASA, DHS, DoE — big contract sources outside DoD
    {"name": "🇺🇸 NASA News",                 "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss", "country": "US"},
    {"name": "🇺🇸 Dept of Energy News",       "url": "https://www.energy.gov/rss.xml", "country": "US"},
]

# ─────────────────────────────────────────────
#  CONTRACT KEYWORDS
# ─────────────────────────────────────────────

CONTRACT_KEYWORDS = [
    # Canada
    "awarded contract", "contract award", "wins contract", "secures contract",
    "awarded a contract", "awarded $", "contract valued", "contract worth",
    "government contract", "federal contract", "procurement",
    "defence contract", "defense contract", "standing offer",
    "sole source", "DND contract", "RCMP contract",
    "Public Services and Procurement", "PSPC contract",
    "Infrastructure Canada", "Transport Canada contract",
    "request for proposal", "RFP awarded",
    # US
    "Department of Defense", "DoD contract", "Pentagon contract",
    "Army contract", "Navy contract", "Air Force contract",
    "Space Force contract", "DARPA", "indefinite-delivery",
    "IDIQ", "cost-plus", "firm-fixed-price", "task order",
    "prime contract", "awarded by the", "has been awarded",
    "contract modification", "NASA contract", "DHS contract",
    "Department of Energy contract", "GSA contract",
]

# ─────────────────────────────────────────────
#  PUBLIC COMPANY WATCHLIST
#  { "search term in article": ("TICKER", "Exchange") }
#  Add/remove freely — the more names you add, the better coverage
# ─────────────────────────────────────────────

COMPANY_WATCHLIST = {
    # ── CANADA: Defence & Aerospace ─────────────────────────────────────────
    "CAE":               ("CAE.TO",   "TSX"),
    "MDA Space":         ("MDA.TO",   "TSX"),
    "MDA Ltd":           ("MDA.TO",   "TSX"),
    "Magellan Aerospace":("MHI.TO",   "TSX"),
    "Bombardier":        ("BBD.B.TO", "TSX"),
    "StandardAero":      ("SAE",      "NYSE"),
    "Heroux-Devtek":     ("HRX.TO",   "TSX"),
    "Héroux-Devtek":     ("HRX.TO",   "TSX"),

    # ── CANADA: IT / Technology ──────────────────────────────────────────────
    "CGI Group":         ("GIB.A.TO", "TSX"),
    "CGI Inc":           ("GIB.A.TO", "TSX"),
    "OpenText":          ("OTEX.TO",  "TSX"),
    "Telus":             ("T.TO",     "TSX"),
    "Bell Canada":       ("BCE.TO",   "TSX"),
    "Rogers":            ("RCI.B.TO", "TSX"),
    "BlackBerry":        ("BB.TO",    "TSX"),

    # ── CANADA: Infrastructure & Engineering ────────────────────────────────
    "AtkinsRealis":      ("ATRL.TO",  "TSX"),
    "AtkinsRéalis":      ("ATRL.TO",  "TSX"),
    "SNC-Lavalin":       ("ATRL.TO",  "TSX"),
    "WSP Global":        ("WSP.TO",   "TSX"),
    "WSP Canada":        ("WSP.TO",   "TSX"),
    "Stantec":           ("STN.TO",   "TSX"),
    "Bird Construction": ("BDT.TO",   "TSX"),

    # ── CANADA: Energy ──────────────────────────────────────────────────────
    "Brookfield":        ("BN.TO",    "TSX"),

    # ── US: Defence & Aerospace (the big movers) ────────────────────────────
    "Lockheed Martin":   ("LMT",      "NYSE"),
    "Raytheon":          ("RTX",      "NYSE"),
    "RTX":               ("RTX",      "NYSE"),
    "Northrop Grumman":  ("NOC",      "NYSE"),
    "General Dynamics":  ("GD",       "NYSE"),
    "Boeing":            ("BA",       "NYSE"),
    "L3Harris":          ("LHX",      "NYSE"),
    "Leidos":            ("LDOS",     "NYSE"),
    "Booz Allen":        ("BAH",      "NYSE"),
    "Booz Allen Hamilton":("BAH",     "NYSE"),
    "SAIC":              ("SAIC",     "NASDAQ"),
    "Science Applications":("SAIC",  "NASDAQ"),
    "ManTech":           ("MANT",     "NASDAQ"),
    "Parsons":           ("PSN",      "NYSE"),
    "Kratos":            ("KTOS",     "NASDAQ"),
    "Rocket Lab":        ("RKLB",     "NASDAQ"),
    "Palantir":          ("PLTR",     "NYSE"),
    "Axon":              ("AXON",     "NASDAQ"),
    "TransDigm":         ("TDG",      "NYSE"),
    "Curtiss-Wright":    ("CW",       "NYSE"),
    "DRS Technologies":  ("DRS",      "NYSE"),
    "Leonardo DRS":      ("DRS",      "NYSE"),

    # ── US: IT / Cloud / Cyber (frequent gov contractors) ───────────────────
    "Microsoft":         ("MSFT",     "NASDAQ"),
    "Amazon":            ("AMZN",     "NASDAQ"),
    "AWS":               ("AMZN",     "NASDAQ"),
    "Google":            ("GOOGL",    "NASDAQ"),
    "IBM":               ("IBM",      "NYSE"),
    "Accenture":         ("ACN",      "NYSE"),
    "Leidos Holdings":   ("LDOS",     "NYSE"),
    "CrowdStrike":       ("CRWD",     "NASDAQ"),
    "Palo Alto":         ("PANW",     "NASDAQ"),
    "Elastic":           ("ESTC",     "NYSE"),
    "Oracle":            ("ORCL",     "NYSE"),

    # ── US: Energy & Infrastructure ─────────────────────────────────────────
    "Bechtel":           ("private",  "N/A"),
    "Fluor":             ("FLR",      "NYSE"),
    "Jacobs":            ("J",        "NYSE"),
    "AECOM":             ("ACM",      "NYSE"),
    "Kiewit":            ("private",  "N/A"),
}

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def load_seen_articles():
    if os.path.exists(SEEN_ARTICLES_FILE):
        with open(SEEN_ARTICLES_FILE, "r") as f:
            return set(json.load(f))
    return set()


def save_seen_articles(seen):
    with open(SEEN_ARTICLES_FILE, "w") as f:
        json.dump(list(seen), f)


def article_id(entry):
    key = entry.get("link") or entry.get("id") or entry.get("title") or ""
    return hashlib.md5(key.encode()).hexdigest()


def is_recent(entry):
    for field in ("published_parsed", "updated_parsed"):
        t = entry.get(field)
        if t:
            pub = datetime(*t[:6])
            return datetime.utcnow() - pub < timedelta(hours=LOOKBACK_HOURS)
    return True  # no date = include to be safe


def extract_dollar_amounts(text):
    """
    Returns list of values in CAD/USD millions.
    Handles: $1.2 billion, $500 million, $250M, $1.5B, $750,000,000
    """
    amounts = []

    pattern = r'\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|B|M|bn|m)\b'
    for match in re.finditer(pattern, text, re.IGNORECASE):
        value = float(match.group(1).replace(",", ""))
        unit  = match.group(2).lower()
        if unit in ("billion", "b", "bn"):
            value *= 1000
        amounts.append(value)

    # Raw format: $750,000,000
    for match in re.finditer(r'\$([\d]{1,3}(?:,[\d]{3}){2,})', text):
        value = float(match.group(1).replace(",", "")) / 1_000_000
        amounts.append(value)

    return amounts


def find_companies(text):
    found = []
    text_lower = text.lower()
    seen_tickers = set()
    for keyword, (ticker, exchange) in COMPANY_WATCHLIST.items():
        if ticker == "private":
            continue
        if keyword.lower() in text_lower and ticker not in seen_tickers:
            found.append((keyword, ticker, exchange))
            seen_tickers.add(ticker)
    return found


def has_contract_keywords(text):
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in CONTRACT_KEYWORDS)


def fetch_full_text(url):
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)[:6000]
    except Exception:
        return ""


# ─────────────────────────────────────────────
#  SCAN
# ─────────────────────────────────────────────

def scan_feeds():
    seen = load_seen_articles()
    alerts = []
    new_seen = set()

    for feed_info in RSS_FEEDS:
        feed_name = feed_info["name"]
        feed_url  = feed_info["url"]
        print(f"  Checking: {feed_name}")

        try:
            feed = feedparser.parse(feed_url)
        except Exception as e:
            print(f"  [WARN] Could not fetch {feed_name}: {e}")
            continue

        for entry in feed.entries:
            uid = article_id(entry)
            new_seen.add(uid)

            if uid in seen:
                continue
            if not is_recent(entry):
                continue

            title   = entry.get("title", "")
            summary = entry.get("summary", "") or entry.get("description", "")
            link    = entry.get("link", "")
            text    = f"{title} {summary}"

            if not has_contract_keywords(text):
                continue

            full_text = fetch_full_text(link) if link else ""
            combined  = f"{text} {full_text}"

            amounts    = extract_dollar_amounts(combined)
            max_amount = max(amounts) if amounts else None

            # Skip if we found an amount but it's below threshold
            if amounts and max_amount < MIN_CONTRACT_VALUE_MILLIONS:
                continue

            companies = find_companies(combined)

            alerts.append({
                "source":     feed_name,
                "title":      title,
                "summary":    summary[:500],
                "link":       link,
                "published":  entry.get("published", "Unknown time"),
                "amounts":    amounts,
                "max_amount": max_amount,
                "companies":  companies,
            })
            print(f"  [MATCH] {title[:80]}")

    # Persist seen set (cap size to avoid bloat)
    seen.update(new_seen)
    if len(seen) > 10000:
        seen = new_seen
    save_seen_articles(seen)

    return alerts


# ─────────────────────────────────────────────
#  EMAIL
# ─────────────────────────────────────────────

def format_amount(val_millions):
    if val_millions >= 1000:
        return f"~${val_millions/1000:.2f}B"
    return f"~${val_millions:.0f}M"


def build_email_html(alerts):
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    rows = ""

    for a in alerts:
        amount_badge = (
            f"<span style='background:#27ae60;color:#fff;padding:3px 8px;border-radius:4px;font-size:13px;'>"
            f"💰 {format_amount(a['max_amount'])}</span>"
            if a["max_amount"]
            else "<span style='color:#999;font-size:13px;'>💰 Amount not extracted — check article</span>"
        )

        if a["companies"]:
            ticker_pills = " ".join(
                f"<span style='background:#2980b9;color:#fff;padding:3px 8px;border-radius:4px;font-size:12px;margin-right:4px;'>"
                f"📈 {t} <span style='opacity:0.75;font-size:10px;'>({ex})</span></span>"
                for (_, t, ex) in a["companies"]
            )
            tickers_section = f"<p style='margin:8px 0;'>{ticker_pills}</p>"
        else:
            tickers_section = "<p style='color:#999;font-size:13px;'>📈 No watchlist match — review manually</p>"

        rows += f"""
        <div style='border:1px solid #e0e0e0;border-radius:8px;padding:18px;margin-bottom:18px;background:#fafafa;'>
          <p style='margin:0 0 6px;font-size:12px;color:#999;'>{a['source']} &nbsp;·&nbsp; {a['published']}</p>
          <h3 style='margin:0 0 8px;font-size:16px;color:#1a1a1a;'>{a['title']}</h3>
          <p style='margin:0 0 12px;font-size:14px;color:#444;line-height:1.5;'>{a['summary']}</p>
          <p style='margin:0 0 8px;'>{amount_badge}</p>
          {tickers_section}
          <a href='{a['link']}' style='color:#c0392b;font-size:13px;'>→ Read full article</a>
        </div>
        """

    return f"""
    <html><body style='font-family:Arial,sans-serif;max-width:680px;margin:auto;padding:20px;'>
      <div style='background:#c0392b;border-radius:8px;padding:20px;margin-bottom:24px;'>
        <h1 style='color:#fff;margin:0;font-size:22px;'>🇨🇦🇺🇸 Gov Contract Alert</h1>
        <p style='color:#f5c6c6;margin:6px 0 0;font-size:13px;'>{len(alerts)} new deal(s) found &nbsp;·&nbsp; {now}</p>
      </div>
      {rows}
      <p style='font-size:11px;color:#bbb;border-top:1px solid #eee;padding-top:12px;'>
        Automated monitor. Not financial advice. Verify all information before trading.
        Threshold: contracts ≥ ${MIN_CONTRACT_VALUE_MILLIONS}M.
      </p>
    </body></html>
    """


def send_email(alerts):
    if not all([EMAIL_CONFIG["sender"], EMAIL_CONFIG["password"], EMAIL_CONFIG["recipient"]]):
        print("[ERROR] Email credentials not set. Check GitHub Secrets.")
        return

    subject = f"🇨🇦🇺🇸 Gov Contract Alert: {len(alerts)} deal(s) — {datetime.utcnow().strftime('%b %d %H:%M UTC')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_CONFIG["sender"]
    msg["To"]      = EMAIL_CONFIG["recipient"]
    msg.attach(MIMEText(build_email_html(alerts), "html"))

    try:
        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            server.starttls()
            server.login(EMAIL_CONFIG["sender"], EMAIL_CONFIG["password"])
            server.sendmail(EMAIL_CONFIG["sender"], EMAIL_CONFIG["recipient"], msg.as_string())
        print(f"[EMAIL] Alert sent for {len(alerts)} article(s).")
    except Exception as e:
        print(f"[ERROR] Email failed: {e}")
        raise


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n[{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}] Scanning {len(RSS_FEEDS)} feeds (🇨🇦 Canada + 🇺🇸 US)...")
    alerts = scan_feeds()

    if alerts:
        print(f"\n[RESULT] {len(alerts)} alert(s) found. Sending email...")
        send_email(alerts)
    else:
        print("\n[RESULT] No new contract alerts this run.")
