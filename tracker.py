import os
import re
import csv
from datetime import datetime
from curl_cffi import requests as cffi_requests
import requests
from bs4 import BeautifulSoup
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

TARGET_URL = "https://my.racknerd.com/index.php?rp=/store/special-promos"
CSV_FILE = "price_history.csv"
CHART_FILE = "price_trend.png"
ALERT_THRESHOLD = 10.88

SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY")

def get_lowest_price():
    """使用 curl_cffi 模拟真实 Chrome 浏览器指纹穿透 403 防火墙"""
    try:
        # impersonate="chrome120" 会自动伪装完整的 TLS 指纹及 HTTP/2 协议栈
        response = cffi_requests.get(
            TARGET_URL,
            impersonate="chrome120",
            timeout=30,
            headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Sec-Ch-Ua": '"Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            }
        )
        print(f"[{datetime.now()}] 网页响应状态码: {response.status_code}")
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'noscript']):
            tag.decompose()
        page_text = soup.get_text()

        # 正则提取页面中所有的美元价格
        raw_prices = re.findall(r'\$\s*(\d+\.\d{2})', page_text)
        if not raw_prices:
            raw_prices = re.findall(r'(\d+\.\d{2})\s*USD', page_text, re.IGNORECASE)

        valid_prices = []
        for p in raw_prices:
            try:
                val = float(p)
                # 过滤掉非正常年付价格（如 0 元设置费或异常极值）
                if 4.0 <= val <= 200.0:
                    valid_prices.append(val)
            except ValueError:
                continue

        if not valid_prices:
            print("❌ 警告：未能在网页中提取到有效价格数据。")
            return None
            
        lowest_price = min(valid_prices)
        print(f"✅ 抓取成功！匹配到 {len(valid_prices)} 个套餐，当前全场最低价为: ${lowest_price:.2f} USD/年")
        return lowest_price

    except Exception as e:
        print(f"❌ 抓取页面异常: {e}")
        return None

def check_and_notify(price):
    """当最低价低于 10.88 美元时推送到微信"""
    if price >= ALERT_THRESHOLD:
        print(f"ℹ️ 今日最低价 ${price:.2f} >= 阈值 ${ALERT_THRESHOLD:.2f}，不触发微信推送。")
        return

    if not SERVERCHAN_SENDKEY:
        print("ℹ️ 未检测到 SERVERCHAN_SENDKEY，跳过微信推送。")
        return

    diff = ALERT_THRESHOLD - price
    title = f"🚨 捡漏提醒：RackNerd 出现超低价 VPS！仅需 ${price:.2f}/年"
    content = (
        f"### 🔥 RackNerd 特惠 VPS 破价提醒\n\n"
        f"- **今日全场最低价**：`${price:.2f}` USD/年\n"
        f"- **监控警戒线**：`${ALERT_THRESHOLD:.2f}` USD/年\n"
        f"- **低于警戒线**：`${diff:.2f}` USD\n"
        f"- **抓取时间**：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
        f"[👉 点击立即直达特惠页面抢购]({TARGET_URL})"
    )
    
    api_url = f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send"
    payload = {"title": title, "desp": content}
    try:
        resp = requests.post(api_url, data=payload, timeout=10)
        res = resp.json()
        if res.get("code") == 0:
            print("✅ 微信降价提醒发送成功！")
        else:
            print(f"❌ 微信推送返回错误: {res.get('message')}")
    except Exception as e:
        print(f"❌ 微信推送请求失败: {e}")

def record_price(price):
    """保存或更新当天的最低价格到 CSV"""
    today = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        df = pd.read_csv(CSV_FILE)
        if today in df['date'].astype(str).values:
            df.loc[df['date'].astype(str) == today, 'price'] = price
            df.to_csv(CSV_FILE, index=False)
            print(f"📝 今日 ({today}) 记录已更新。")
            return
            
    file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['date', 'price'])
        writer.writerow([today, price])
    print(f"📝 今日 ({today}) 价格已写入 CSV: ${price:.2f}")

def render_chart():
    """生成走势折线图"""
    if not os.path.exists(CSV_FILE) or os.path.getsize(CSV_FILE) == 0:
        return
    df = pd.read_csv(CSV_FILE)
    if df.empty:
        return

    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    
    min_price = df['price'].min()
    latest_row = df.iloc[-1]
    min_records = df[df['price'] == min_price]
    
    plt.figure(figsize=(10, 5), dpi=180)
    plt.style.use('seaborn-v0_8-whitegrid' if 'seaborn-v0_8-whitegrid' in plt.style.available else 'default')
    
    plt.plot(df['date'], df['price'], marker='o', markersize=5, color='#2563eb', linewidth=2.2, label='Daily Lowest Price ($)', zorder=3)
    plt.axhline(y=ALERT_THRESHOLD, color='#ea580c', linestyle='-.', linewidth=1.5, alpha=0.9, label=f'Alert Target: < ${ALERT_THRESHOLD:.2f}', zorder=2)
    plt.scatter(min_records['date'], min_records['price'], color='#dc2626', s=110, zorder=5, edgecolors='black', linewidth=1.2, label='Lowest Point')
    
    for _, row in min_records.iterrows():
        plt.annotate(
            f"Lowest: ${row['price']:.2f}",
            (row['date'], row['price']),
            textcoords="offset points",
            xytext=(0, 12),
            ha='center',
            fontsize=9.5,
            fontweight='bold',
            color='#b91c1c',
            bbox=dict(boxstyle="round,pad=0.25", fc="#fee2e2", ec="#ef4444", lw=0.8)
        )
    
    plt.title(f"RackNerd Special Promos Lowest Price Tracker\nToday: ${latest_row['price']:.2f}  |  Recorded Low: ${min_price:.2f}", fontsize=12, fontweight='bold', pad=12)
    plt.xlabel("Date", fontsize=10, labelpad=8)
    plt.ylabel("Annual Price ($ USD)", fontsize=10, labelpad=8)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    if len(df) > 1:
        plt.gcf().autofmt_xdate(rotation=30)
    plt.legend(loc='best', frameon=True, fontsize=9)
    plt.tight_layout()
    plt.savefig(CHART_FILE)
    plt.close()
    print("📊 价格走势图渲染完毕。")

if __name__ == "__main__":
    lowest_price = get_lowest_price()
    if lowest_price is not None:
        check_and_notify(lowest_price)
        record_price(lowest_price)
        render_chart()
