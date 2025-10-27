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
            print("[INFO] Step 1: Waiting for DevSisters SSO page...")
            
            # "크래프톤 직원 로그인" 버튼 찾기 (여러 가능한 텍스트)
            try:
                # 버튼 클릭 (한글 또는 영문 텍스트)
                krafton_button = page.locator('text="크래프톤 직원 로그인"').or_(page.locator('text="Krafton Employee Login"'))
                await krafton_button.click(timeout=10000)
                print("[INFO] Clicked '크래프톤 직원 로그인' button")
            except:
                print("[WARN] '크래프톤 직원 로그인' button not found, trying alternative...")
                # 대안: 직접 링크로 이동
                pass
            
            await page.wait_for_timeout(2000)
            
            # Microsoft SSO 로그인
            print("[INFO] Entering credentials for Microsoft SSO...")
            
            # 이메일 입력
            try:
                email_input = page.locator('input[name="loginfmt"]').or_(page.locator('input[type="email"]'))
                await email_input.fill(KRAFTON_EMAIL, timeout=10000)
                print(f"[INFO] Entered email: {KRAFTON_EMAIL[:3]}***")
                
                # "다음" 버튼 클릭
                next_button = page.locator('input[type="submit"]').or_(page.locator('button:has-text("Next")'))
                await next_button.click()
                await page.wait_for_timeout(2000)
            except Exception as e:
                print(f"[WARN] Email step: {e}")
            
            # 비밀번호 입력
            try:
                password_input = page.locator('input[name="passwd"]').or_(page.locator('input[type="password"]'))
                await password_input.fill(KRAFTON_PASSWORD, timeout=10000)
                print("[INFO] Entered password")
                
                # "로그인" 버튼 클릭
                signin_button = page.locator('input[type="submit"]').or_(page.locator('button:has-text("Sign in")'))
                await signin_button.click()
                await page.wait_for_timeout(3000)
            except Exception as e:
                print(f"[WARN] Password step: {e}")
            
            # "로그인 유지" 화면이 나올 수 있음
            try:
                stay_signed_in = page.locator('input[type="submit"]').or_(page.locator('button:has-text("Yes")'))
                await stay_signed_in.click(timeout=5000)
                print("[INFO] Clicked 'Stay signed in'")
            except:
                print("[INFO] No 'Stay signed in' prompt")
            
            await page.wait_for_timeout(3000)
            
            # ============================================
            # 2단계: CRCI Krafton SSO
            # ============================================
            print("[INFO] Step 2: Waiting for CRCI Krafton SSO page...")
            
            # "Krafton" 버튼 클릭
            try:
                krafton_button_2 = page.locator('button:has-text("Krafton")').or_(page.locator('text="Krafton"'))
                await krafton_button_2.click(timeout=10000)
                print("[INFO] Clicked 'Krafton' button")
                await page.wait_for_timeout(5000)
            except Exception as e:
                print(f"[WARN] Krafton button step: {e}")
            
            # Microsoft SSO 다시 (자동으로 넘어갈 수도 있음)
            try:
                # 이미 로그인되어 있으면 자동으로 넘어감
                # 아니면 다시 이메일 입력
                email_input_2 = page.locator('input[name="loginfmt"]').or_(page.locator('input[type="email"]'))
                if await email_input_2.is_visible(timeout=5000):
                    await email_input_2.fill(KRAFTON_EMAIL)
                    next_btn = page.locator('input[type="submit"]')
                    await next_btn.click()
                    await page.wait_for_timeout(2000)
                    
                    password_input_2 = page.locator('input[name="passwd"]')
                    await password_input_2.fill(KRAFTON_PASSWORD)
                    signin_btn = page.locator('input[type="submit"]')
                    await signin_btn.click()
                    await page.wait_for_timeout(3000)
                    print("[INFO] Completed second SSO login")
            except:
                print("[INFO] Second SSO auto-passed (already authenticated)")
            
            # ============================================
            # 3단계: 대시보드 로딩 대기
            # ============================================
            print("[INFO] Waiting for dashboard to load...")
            await page.wait_for_timeout(15000)  # Tableau 로딩 대기
            
            print(f"[INFO] Final URL: {page.url}")
            
            # ============================================
            # 4단계: 데이터 추출
            # ============================================
            async def get_by_exact_value(value_name):
                try:
                    selector = f'div[id*="{value_name}"]'
                    el = page.locator(selector).first
                    txt = (await el.text_content(timeout=10000)) or ""
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
            print(f"[ERROR] Login/Scraping failed: {e}")
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
    if not KRAFTON_EMAIL or not KRAFTON_PASSWORD:
        raise SystemExit("[ERROR] KRAFTON_EMAIL and KRAFTON_PASSWORD must be set in GitHub Secrets!")
    
    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(tz=kst).date()
    target = today - datetime.timedelta(days=1) if USE_YESTERDAY else today
    ds = target.strftime("%Y-%m-%d")

    kpi = asyncio.run(login_and_scrape(ds))
    post_to_slack(make_blocks(ds, kpi))
