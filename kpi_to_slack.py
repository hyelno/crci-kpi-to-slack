import os, asyncio, datetime, requests, re
from playwright.async_api import async_playwright

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "Cxxxxxxxx")
TARGET_URL = "https://biskit.devskrf.cloud/crci/core-kpi/overview/summary/daily"
USE_YESTERDAY = os.getenv("USE_YESTERDAY", "1") == "1"

# SSO 로그인 정보 (GitHub Secrets에 저장)
KRAFTON_EMAIL = os.environ.get("KRAFTON_EMAIL")
KRAFTON_PASSWORD = os.environ.get("KRAFTON_PASSWORD")

def fmt_krw(n: float) -> str:
    if n >= 10000:
        return f"₩{n/10000:.1f}만"
    return "₩" + format(int(n), ",")

def parse_krw(text: str) -> float:
    text = text.strip()
    if "만" in text:
        num_part = re.sub(r'[^\d.]', '', text)
        return float(num_part) * 10000
    num_part = re.sub(r'[^\d.]', '', text)
    return float(num_part) if num_part else 0

def parse_number(text: str) -> int:
    text = text.strip().replace(",", "").replace(" ", "")
    try:
        return int(text)
    except:
        return 0

async def login_and_scrape(date_str: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        try:
            print(f"[INFO] Loading {TARGET_URL}")
            await page.goto(TARGET_URL, timeout=60000)
            
            # ============================================
            # 1단계: DevSisters SSO (크래프톤 직원 로그인)
            # ============================================
            print("[INFO] Step 1: Waiting for DevSisters SSO page
