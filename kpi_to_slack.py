import os, datetime, requests

# GitHub Secrets로부터 가져옴
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL", "#bi-daily")

def make_blocks(date_str, kpi):
    title = f":bar_chart: CookieRun India Daily KPI — {date_str}"
    fields = [
        f"*DAU*: {kpi.get('DAU','-')}",
        f"*New Users*: {kpi.get('New Users','-')}",
        f"*Revenue*: {kpi.get('Revenue','-')}",
        f"*ARPDAU*: {kpi.get('ARPDAU','-')}",
        f"*D1 Retention*: {kpi.get('Retention D1','-')}",
    ]
    return [
        {"type": "header", "text": {"type": "plain_text", "text": title}},
        {"type": "section", "fields": [{"type":"mrkdwn","text": f} for f in fields]},
        {"type": "context", "elements": [
            {"type":"mrkdwn", "text": "<https://biskit.devskrf.cloud/crci/core-kpi/overview/summary/daily|원본 대시보드>"}
        ]}
    ]

def post_to_slack(blocks):
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    payload = {
        "channel": SLACK_CHANNEL,
        "blocks": blocks,
        "text": "CookieRun India Daily KPI",  # fallback
    }
    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()
    res = r.json()
    if not res.get("ok"):
        raise Exception(f"Slack error: {res}")

if __name__ == "__main__":
    # 테스트용 더미 데이터
    kpi = {
        "DAU": "123,456",
        "New Users": "7,890",
        "Revenue": "₩12,345,678",
        "ARPDAU": "₩100",
        "Retention D1": "45.6%",
    }

    kst = datetime.timezone(datetime.timedelta(hours=9))
    ds = datetime.datetime.now(tz=kst).date().strftime("%Y-%m-%d")
    blocks = make_blocks(ds, kpi)
    post_to_slack(blocks)
