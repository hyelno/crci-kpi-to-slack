import os, asyncio, datetime, requests, re, json
from playwright.async_api import async_playwright

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "Cxxxxxxxx")
TARGET_URL = "https://biskit.devskrf.cloud/crci/core-kpi/overview/summary/daily"
USE_YESTERDAY = os.getenv("USE_YESTERDAY", "1") == "1"

# 쿠키 정보 (GitHub Secrets에서 가져옴)
BISKIT_COOKIES = os.environ.get("BISKIT_COOKIES")

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

async def scrape_with_cookies(date_str: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        
        # 쿠키 로드
        if BISKIT_COOKIES:
            try:
                cookies = json.loads(BISKIT_COOKIES)
                await ctx.add_cookies(cookies)
                print(f"[INFO] Loaded {len(cookies)} cookies")
            except Exception as e:
                print(f"[ERROR] Failed to load cookies: {e}")
                raise
        else:
            raise Exception("BISKIT_COOKIES not found in environment!")
        
        page = await ctx.new_page()

        try:
            print(f"[INFO] Loading {TARGET_URL} with cookies...")
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
            
            # 페이지 로딩 대기
            print("[INFO] Waiting for dashboard to load...")
            await page.wait_for_timeout(15000)
            
            print(f"[INFO] Current URL: {page.url}")
            print(f"[INFO] Page title: {await page.title()}")
            
            # 로그인 확인
            if "login" in page.url.lower() or "auth" in page.url.lower():
                print("[ERROR] Still on login page - cookies expired or invalid!")
                await page.screenshot(path="login_failed.png")
                raise Exception("Authentication failed - cookies may be expired")
            
            # HTML에 CRCI 요소 확인
            html = await page.content()
            if "CRCI_DAILY_BIGNUMBER" in html:
                print("[INFO] ✅ Dashboard loaded successfully!")
            else:
                print("[WARN] ❌ Dashboard elements not found")
                await page.screenshot(path="dashboard_failed.png")
            
            # 데이터 추출
            async def get_by_exact_value(value_name):
                try:
                    selector = f'div[id*="{value_name}"]'
                    el = page.locator(selector).first
                    txt = (await el.text_content(timeout=15000)) or ""
                    result = txt.strip()
                    print(f"[DEBUG] {value_name}: '{result}'")
                    return result
                except Exception as e:
                    print(f"[ERROR] Failed to get {value_name}: {e}")
                    return ""

            au_text = await get_by_exact_value("CRCI_DAILY_BIGNUMBER_DAILY_AU_CHART")
            nu_text = await get_by_exact_value("CRCI_DAILY_BIGNUMBER_DAILY_NU_CHART")
            rev_text = await get_by_exact_value("CRCI_DAILY_BIGNUMBER_DAILY_REVENUE_CHART")
            rev_accum_text = await get_by_exact_value("CRCI_DAILY_BIGNUMBER_DAILY_REVENUE_ACCUM_CHART")

            await browser.close()

            au = parse_number(au_text)
            nu = parse_number(nu_text)
            revenue = parse_krw(rev_text)
            revenue_accum = parse_krw(rev_accum_text)

            kpi = {
                "DAU": f"{au:,}" if au > 0 else "-",
                "New Users": f"{nu:,}" if nu > 0 else "-",
                "일매출": fmt_krw(revenue) if revenue > 0 else "-",
                "누적매출": fmt_krw(revenue_accum) if revenue_accum > 0 else "-",
            }
            
            print(f"[INFO] Parsed KPI: {kpi}")
            return kpi
            
        except Exception as e:
            print(f"[ERROR] Scraping failed: {e}")
            import traceback
            traceback.print_exc()
            await browser.close()
            raise

def make_blocks(date_str, kpi):
    title = f":bar_chart: CookieRun India Daily KPI — {date_str}"
    fields = [
        f"*DAU*: {kpi['DAU']}",
        f"*New Users*: {kpi['New Users']}",
        f"*일매출*: {kpi['일매출']}",
        f"*누적매출*: {kpi['누적매출']}",
    ]
    return [
        {"type":"header","text":{"type":"plain_text","text":title}},
        {"type":"section","fields":[{"type":"mrkdwn","text":f} for f in fields]},
        {"type":"context","elements":[
            {"type":"mrkdwn","text":"<https://biskit.devskrf.cloud/crci/core-kpi/overview/summary/daily|원본 대시보드>"}
        ]}
    ]

def post_to_slack(blocks):
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    payload = {"channel": SLACK_CHANNEL, "blocks": blocks, "text":"CookieRun India Daily KPI"}
    res = requests.post(url, headers=headers, json=payload, timeout=30).json()
    if not res.get("ok"):
        raise SystemExit(f"Slack error: {res}")
    print("[SUCCESS] Message posted to Slack")

if __name__ == "__main__":
    if not BISKIT_COOKIES:
        raise SystemExit("[ERROR] BISKIT_COOKIES must be set in GitHub Secrets!")
    
    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(tz=kst).date()
    target = today - datetime.timedelta(days=1) if USE_YESTERDAY else today
    ds = target.strftime("%Y-%m-%d")

    kpi = asyncio.run(scrape_with_cookies(ds))
    post_to_slack(make_blocks(ds, kpi))
