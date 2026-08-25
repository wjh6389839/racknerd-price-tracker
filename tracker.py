import os
import re
import csv
from datetime import datetime
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
ALERT_THRESHOLD = 10.88  # 触发微信提醒的目标价格阈值

SERVERCHAN_SENDKEY = os.getenv("SERVERCHAN_SENDKEY")

def get_lowest_price():
    """解析页面中所有套餐价格并返回全场最低价"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=25)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()
        
        # 匹配页面中所有的美元价格格式，例如 $9.89, $10.18, $11.88 等
        raw_prices = re.findall(r'\$(\d+\.\d{2})', text)
        
        valid_prices = []
        for p in raw_prices:
            val = float(p)
            # 过滤掉 0 元设置费或异常极小/极大数值，保留正常的年付 VPS 价格区间
            if 3.0 <= val <= 300.0:
                valid_prices.append(val)
        
        if not valid_prices:
            print("未在页面中找到有效的价格信息。")
            return None
            
        lowest_price = min(valid_prices)
        print(f"[{datetime.now()}] 成功抓取！页面共检测到 {len(valid_prices)} 个价格档位，最低价为: ${lowest_price:.2f} USD/年")
        return lowest_price
    except Exception as e:
        print(f"抓取页面出错: {e}")
        return None

def check_and_notify(price):
    """当最低价低于 10.88 美元时推送到微信"""
    if price >= ALERT_THRESHOLD:
        print(f"今日最低价 ${price:.2f} 未低于阈值 ${ALERT_THRESHOLD:.2f}，无需发送微信提醒。")
        return

    if not SERVERCHAN_SENDKEY:
        print("未配置 SERVERCHAN_SENDKEY，跳过微信推送。")
        return

    diff = ALERT_THRESHOLD - price
    title = f"🚨 捡漏提醒：RackNerd 出现超低价 VPS！仅需 ${price:.2f}/年"
    content = (
        f"### 🔥 RackNerd 特惠 VPS 破价提醒\n\n"
        f"- **今日全场最低价**：`${price:.2f}` USD/年\n"
        f"- **目标监控线**：`${ALERT_THRESHOLD:.2f}` USD/年\n"
        f"- **低于目标**：`${diff:.2f}` USD\n"
        f"- **检测时间**：`{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
        f"[👉 点击立即直达特惠页面抢购]({TARGET_URL})"
    )
    
    api_url = f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send"
    payload = {"title": title, "desp": content}
    try:
        resp = requests.post(api_url, data=payload, timeout=10)
        res = resp.json()
        if res.get("code") == 0:
            print("微信降价提醒发送成功！")
        else:
            print(f"微信推送接口返回异常: {res.get('message')}")
    except Exception as e:
        print(f"请求微信推送失败: {e}")

def record_price(price):
    """保存或更新当天的最低价格到 CSV"""
    today = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        df = pd.read_csv(CSV_FILE)
        if today in df['date'].astype(str).values:
            df.loc[df['date'].astype(str) == today, 'price'] = price
            df.to_csv(CSV_FILE, index=False)
            return
            
    file_exists = os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['date', 'price'])
        writer.writerow([today, price])

def render_chart():
    """生成走势折线图，并标出 10.88 警戒线及历史最低点"""
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
    
    # 绘制走势折线
    plt.plot(df['date'], df['price'], marker='o', markersize=5, color='#2563eb', linewidth=2.2, label='Daily Lowest Price ($)', zorder=3)
    
    # 标出 10.88 美元目标阈值线（橙色点划线）
    plt.axhline(y=ALERT_THRESHOLD, color='#ea580c', linestyle='-.', linewidth=1.5, alpha=0.9, label=f'Alert Target: < ${ALERT_THRESHOLD:.2f}', zorder=2)

    # 标出历史最低点（红色圆点）
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

if __name__ == "__main__":
    lowest_price = get_lowest_price()
    if lowest_price is not None:
        check_and_notify(lowest_price)
        record_price(lowest_price)
        render_chart()
