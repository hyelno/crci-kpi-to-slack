import os, asyncio, datetime, requests
from playwright.async_api import async_playwright

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL   = os.environ.get("SLACK_CHANNEL", "Cxxxxxxxx")  # 채널ID 권장
TARGET_URL      = os.getenv("BISKIT_DASHBOARD_URL", "https://biskit.devskrf.cloud/crci/core-kpi/overview/summary/daily")
USE_YESTERDAY   = os.getenv("USE_YESTERDAY", "1") == "1"  # 집계 시차 고려 기본: 어제

def fmt_krw(n: int) -> str:
    return "₩" + format(int(n), ",")

def pct_text(x: str) -> str:
    s = str(x).strip()
    if s.endswith("%"):
        return s
    try:
        v = float(s)
        if v <= 1: v *= 100
        return f"{v:.1f}%"
    except:
        return s

async def scrape_kpis(date_str: str):
    """
    ✅ 숫자를 읽어오는 '셀렉터'만 맞추면 됩니다.
    아래 1차/2차/3차 방식 중 Lynn 화면에서 되는 걸 그대로 두세요.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        await page.goto(TARGET_URL, wait_until="domcontentloaded")

        # (선택) 날짜 선택 UI가 있다면 여기에 조작 추가
        # await page.click("[data-testid='date-picker']")
        # await page.fill("[data-testid='date-input']", date_str)
        # await page.press("[data-testid='date-input']", "Enter")
        # await page.wait_for_timeout(1200)

        # --- KPI 추출 ---
        # 1차: data-testid가 있는 경우 (있다면 가장 안정적)
        async def get_by_testid(tid):
            try:
                el = page.locator(f"[data-testid='{tid}']").first
                txt = (await el.text_content()) or ""
                return txt.strip()
            except:
                return ""

        # 2차: 카드 라벨(예: DAU) 텍스트 기준으로 형제 요소 숫자 찾기 (Tableau/대시보드 공용 패턴)
        async def get_by_label(label):
            try:
                el = page.locator(f"text={label}").first
                # 라벨 바로 근처 숫자 노드 탐색
                parent = el.locator("xpath=..")
                num = await parent.locator("xpath=.//following::*[1]").first.text_content()
                return (num or "").strip()
            except:
                return ""

        # 3차: 마지막 수단 – 페이지 전체에서 라벨 다음의 숫자 패턴 매칭
        async def robust(label):
            txt = await page.content()
            import re
            # 라벨과 숫자 사이 HTML이 끼어들 수 있어 느슨한 정규식
            m = re.search(rf"{label}[\s\S]{{0,80}}?([₩]?\s?\d[\d,\.]*)", txt, re.IGNORECASE)
            return m.group(1).strip() if m else ""

        # 우선순위별 가져오기 (필요 시 testid 값만 바꾸면 됩니다)
        dau  = await get_by_testid("kpi-dau")          or await get_by_label("DAU")          or await robust("DAU")
        newu = await get_by_testid("kpi-new-users")     or await get_by_label("New Users")    or await robust("New Users")
        rev  = await get_by_testid("kpi-revenue")       or await get_by_label("Revenue")      or await robust("Revenue")
        arpd = await get_by_testid("kpi-arpdau")        or await get_by_label("ARPDAU")       or await robust("ARPDAU")
        d1   = await get_by_testid("kpi-d1")            or await get_by_label("D1")           or await robust("D1")

        await browser.close()

        def to_int(x):
            s = str(x).replace("₩","").replace(",","").strip()
            # 소수점 있으면 반올림
            try:
                return int(round(float(s)))
            except:
                return 0

        kpi = {
            "DAU": f"{to_int(dau):,}" if dau else "-",
            "New Users": f"{to_int(newu):,}" if newu else "-",
            "Revenue": fmt_krw(to_int(rev)) if rev else "-",
            "ARPDAU": fmt_krw(to_int(arpd)) if arpd else "-",
            "D1 Retention": pct_text(d1) if d1 else "-",
        }
        return kpi

def make_blocks(date_str, kpi):
    title = f":bar_chart: CookieRun India Daily KPI — {date_str}"
    fields = [
        f"*DAU*: {kpi['DAU']}",
        f"*New Users*: {kpi['New Users']}",
        f"*Revenue*: {kpi['Revenue']}",
        f"*ARPDAU*: {kpi['ARPDAU']}",
        f"*D1 Retention*: {kpi['D1 Retention']}",
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

if __name__ == "__main__":
    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(tz=kst).date()
    target = today - datetime.timedelta(days=1) if USE_YESTERDAY else today
    ds = target.strftime("%Y-%m-%d")

    kpi = asyncio.run(scrape_kpis(ds))
    post_to_slack(make_blocks(ds, kpi))
