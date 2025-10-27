import os, asyncio, datetime, requests, re
from playwright.async_api import async_playwright

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "Cxxxxxxxx")
TARGET_URL = "https://biskit.devskrf.cloud/crci/core-kpi/overview/summary/daily"
USE_YESTERDAY = os.getenv("USE_YESTERDAY", "1") == "1"

def fmt_krw(n: float) -> str:
    """숫자를 원화 형식으로 변환 (만 단위 처리 포함)"""
    if n >= 10000:
        return f"₩{n/10000:.1f}만"
    return "₩" + format(int(n), ",")

def parse_krw(text: str) -> float:
    """₩ 2,467.83 또는 ₩ 1,283.8 만 형태를 숫자로 변환"""
    text = text.strip()
    
    # "만" 단위 처리
    if "만" in text:
        num_part = re.sub(r'[^\d.]', '', text)
        return float(num_part) * 10000
    
    # 일반 숫자
    num_part = re.sub(r'[^\d.]', '', text)
    return float(num_part) if num_part else 0

def parse_number(text: str) -> int:
    """공백과 콤마를 제거하고 정수로 변환"""
    text = text.strip().replace(",", "").replace(" ", "")
    try:
        return int(text)
    except:
        return 0

async def scrape_kpis(date_str: str):
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        print(f"[INFO] Loading {TARGET_URL}")
        await page.goto(TARGET_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)  # 5초 대기 (Tableau 로딩)

        # ✅ 정확한 ID로 데이터 가져오기
        async def get_by_exact_value(value_name):
            try:
                # id 속성에 정확한 value가 포함된 요소 찾기
                selector = f'div[id*="{value_name}"]'
                el = page.locator(selector).first
                txt = (await el.text_content()) or ""
                result = txt.strip()
                print(f"[DEBUG] {value_name}: '{result}'")
                return result
            except Exception as e:
                print(f"[ERROR] Failed to get {value_name}: {e}")
                return ""

        # 실제 ID 값으로 데이터 가져오기
        au_text = await get_by_exact_value("CRCI_DAILY_BIGNUMBER_DAILY_AU_CHART")
        nu_text = await get_by_exact_value("CRCI_DAILY_BIGNUMBER_DAILY_NU_CHART")
        rev_text = await get_by_exact_value("CRCI_DAILY_BIGNUMBER_DAILY_REVENUE_CHART")
        rev_accum_text = await get_by_exact_value("CRCI_DAILY_BIGNUMBER_DAILY_REVENUE_ACCUM_CHART")

        await browser.close()

        # 데이터 파싱
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
    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(tz=kst).date()
    target = today - datetime.timedelta(days=1) if USE_YESTERDAY else today
    ds = target.strftime("%Y-%m-%d")

    kpi = asyncio.run(scrape_kpis(ds))
    post_to_slack(make_blocks(ds, kpi))
```

---

## 🎯 테스트 단계

1. **위 코드를 `kpi_to_slack.py`에 복사 → Commit**
2. **Actions → Run workflow** 실행
3. **로그에서 확인**:
```
   [DEBUG] CRCI_DAILY_BIGNUMBER_DAILY_AU_CHART: '965'
   [DEBUG] CRCI_DAILY_BIGNUMBER_DAILY_NU_CHART: '166'
   [DEBUG] CRCI_DAILY_BIGNUMBER_DAILY_REVENUE_CHART: '₩ 2,467.83'
   [INFO] Parsed KPI: {'DAU': '965', 'New Users': '166', ...}
