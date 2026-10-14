import os
import re
import sys
import glob
from datetime import datetime, timedelta, timezone
import pandas as pd
import matplotlib.pyplot as plt
import requests
from curl_cffi import requests as cffi_requests

# ================= 基础配置 =================
TARGET_URL = "https://my.racknerd.com/index.php?rp=/store/special-promos"
ALERT_PRICE = 10.88  # 低于或等于此价格触发微信推送
SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")

# 自动识别仓库中已有的 csv 和 png 文件名，保持与 README.md 引用一致
existing_csvs = glob.glob("*.csv")
CSV_FILE = existing_csvs[0] if existing_csvs else "price_history.csv"

existing_pngs = glob.glob("*.png")
CHART_FILE = existing_pngs[0] if existing_pngs else "price_trend.png"
# ============================================


def get_beijing_time():
    """获取北京时间"""
    utc_now = datetime.now(timezone.utc)
    return utc_now + timedelta(hours=8)


def fetch_lowest_price():
    """使用 curl_cffi 模拟真实 Chrome 指纹抓取最低价，绕过 Cloudflare 403"""
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Referer": "https://my.racknerd.com/",
        "Cache-Control": "no-cache",
    }

    # 依次尝试多种主流浏览器 TLS 指纹
    browsers = ["chrome124", "chrome120", "chrome116", "safari17_0", "edge101"]

    for browser in browsers:
        try:
            resp = cffi_requests.get(
                TARGET_URL,
                impersonate=browser,
                headers=headers,
                timeout=30
            )
            print(f"[{datetime.now()}] ({browser}) 网页响应状态码: {resp.status_code}")

            if resp.status_code == 200 and "Just a moment" not in resp.text:
                # 匹配形如 $21.99 或 $ 10.88 的价格数字
                matches = re.findall(r'\$\s*(\d+\.\d{2})', resp.text)
                # 过滤出合理区间内的年付价格（排除域名或高价独服干扰）
                prices = [float(p) for p in matches if 5.0 <= float(p) <= 500.0]

                if prices:
                    lowest = min(prices)
                    print(f"✅ 成功获取页面价格列表: {sorted(list(set(prices)))}")
                    print(f"🔥 当前最低特惠价格: ${lowest:.2f} USD")
                    return lowest
                else:
                    print("⚠️ 页面访问成功(200)，但未匹配到有效价格（可能当前无特惠套餐）。")
            else:
                print(f"⚠️ 指纹 {browser} 被拦截或返回验证页，尝试切换下一个...")

        except Exception as e:
            print(f"⚠️ 指纹 {browser} 请求异常: {e}")

    print("❌ 抓取页面异常: 所有浏览器指纹均未能突破拦截或页面无数据")
    sys.exit(1)  # 返回非零状态码，让 GitHub Actions 准确提示失败而非假绿勾


def update_price_history(date_str, lowest_price):
    """更新历史价格 CSV 数据"""
    if os.path.exists(CSV_FILE):
        try:
            df = pd.read_csv(CSV_FILE)
            # 兼容原有列名（不管之前叫 date/price 还是 Date/Price）
            col_date, col_price = df.columns[0], df.columns[1]
        except Exception:
            col_date, col_price = "Date", "Price"
            df = pd.DataFrame(columns=[col_date, col_price])
    else:
        col_date, col_price = "Date", "Price"
        df = pd.DataFrame(columns=[col_date, col_price])

    # 如果当天已有记录则更新最低价，没有则追加新行
    if date_str in df[col_date].astype(str).values:
        df.loc[df[col_date].astype(str) == date_str, col_price] = lowest_price
    else:
        new_row = pd.DataFrame({col_date: [date_str], col_price: [lowest_price]})
        df = pd.concat([df, new_row], ignore_index=True)

    df.to_csv(CSV_FILE, index=False)
    print(f"📁 历史数据已更新至: {CSV_FILE} (共 {len(df)} 条记录)")
    return df, col_date, col_price


def generate_chart(df, col_date, col_price):
    """生成与原图风格一致但修复了排版 Bug 的价格走势图"""
    # 取最近 30 天的数据绘制，避免日期过多挤在一起
    plot_df = df.tail(30).copy()
    dates = plot_df[col_date].astype(str).tolist()
    prices = plot_df[col_price].astype(float).tolist()

    today_price = prices[-1]
    recorded_low = df[col_price].astype(float).min()

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    fig, ax = plt.subplots(figsize=(10.5, 5.5), dpi=150)

    # 1. 绘制每日最低价蓝色折线
    ax.plot(dates, prices, color="#1f57eb", linewidth=2.2, marker="o", markersize=6, label="Daily Lowest Price ($)", zorder=3)

    # 2. 绘制橙色目标警戒线
    ax.axhline(y=ALERT_PRICE, color="#e66100", linestyle="-.", linewidth=1.6, label=f"Alert Target: < ${ALERT_PRICE:.2f}", zorder=2)

    # 3. 标出视图内的最低价格红点
    min_in_view = min(prices)
    min_dates = [d for d, p in zip(dates, prices) if p == min_in_view]
    min_vals = [p for p in prices if p == min_in_view]
    ax.scatter(min_dates, min_vals, color="#d92323", edgecolor="black", s=110, linewidth=1.2, zorder=5, label="Lowest Point")

    # 4. 绘制顶部红色价格标签框（若点数过多则智能抽样显示，防止重叠）
    step = 1 if len(dates) <= 10 else max(1, len(dates) // 8)
    for i, (d, p) in enumerate(zip(dates, prices)):
        if i % step == 0 or i == len(dates) - 1 or p < min_in_view:
            ax.annotate(
                f"Lowest: ${p:.2f}",
                xy=(d, p),
                xytext=(0, 12),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8.5,
                fontweight="bold",
                color="#b31b1b",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#ffe6e6", edgecolor="#ff4d4d", linewidth=0.9),
                zorder=6
            )

    # 5. 设置标题与坐标轴（用 \$ 转义防止 Matplotlib 把两个 $ 之间识别为数学斜体公式）
    ax.set_title(
        f"RackNerd Special Promos Lowest Price Tracker\nToday: \\${today_price:.2f} | Recorded Low: \\${recorded_low:.2f}",
        fontsize=12,
        fontweight="bold",
        pad=14
    )
    ax.set_xlabel("Date", fontsize=10, labelpad=8)
    ax.set_ylabel("Annual Price ($ USD)", fontsize=10, labelpad=8)

    # 动态调整 Y 轴范围，给顶部气泡留出足够空间
    y_min = min(min(prices), ALERT_PRICE) - 1.2
    y_max = max(prices) + 2.2
    ax.set_ylim(y_min, y_max)

    plt.xticks(rotation=30, ha="right", fontsize=9)
    plt.yticks(fontsize=9)
    ax.grid(True, linestyle="-", alpha=0.6)
    ax.legend(loc="center right", frameon=True, facecolor="white", framealpha=0.9, fontsize=9.5)

    plt.tight_layout()
    plt.savefig(CHART_FILE, dpi=150)
    plt.close()
    print(f"📊 走势图已重新生成并保存至: {CHART_FILE}")


def send_wechat_notification(price):
    """通过 Server酱 发送微信低价提醒"""
    if not SENDKEY:
        print("ℹ️ 未配置 SERVERCHAN_SENDKEY，跳过微信推送。")
        return

    url = f"https://sctapi.ftqq.com/{SENDKEY}.send"
    title = f"🚨 RackNerd 出现神价：${price:.2f}/年！"
    desp = (
        f"### 监控到 RackNerd 特惠页面出现低价套餐！\n\n"
        f"- **当前最低价**：`${price:.2f} USD/年`\n"
        f"- **设定警戒线**：`${ALERT_PRICE:.2f} USD/年`\n"
        f"- **抢购直达链接**：[点击前往 RackNerd 活动页]({TARGET_URL})\n"
    )
    try:
        res = requests.post(url, data={"title": title, "desp": desp}, timeout=15)
        print(f"📨 微信推送结果: {res.text}")
    except Exception as e:
        print(f"⚠️ 微信推送失败: {e}")


if __name__ == "__main__":
    today_str = get_beijing_time().strftime("%Y-%m-%d")
    print(f"🚀 开始执行 RackNerd 价格监控 ({today_str})...")

    lowest_price = fetch_lowest_price()
    df, col_date, col_price = update_price_history(today_str, lowest_price)
    generate_chart(df, col_date, col_price)

    if lowest_price <= ALERT_PRICE:
        print(f"🎉 触发低价阈值 (<= ${ALERT_PRICE})，正在发送微信提醒...")
        send_wechat_notification(lowest_price)
    else:
        print(f"☕ 当前最低价 ${lowest_price:.2f} 高于警戒线 ${ALERT_PRICE:.2f}，无需推送。")
