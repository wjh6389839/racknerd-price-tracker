# 📉 RackNerd 特惠 VPS 最低价监控看板

> 🤖 **运行机制**：每日北京时间 10:00 自动扫描特惠列表中的全场最低价。  
> 🔔 **提醒阈值**：当最低价 **< $10.88/年** 时，自动触发微信模板消息推送。  
> 🔗 **监控地址**：[RackNerd Special Promos 直达页面](https://my.racknerd.com/index.php?rp=/store/special-promos)

---

### 📊 每日最低价走势图

![价格走势折线图](./price_trend.png)

---

### 📌 图例说明
* **蓝色折线**：特惠页面当天的**最低 VPS 价格**。
* **橙色虚线**：**$10.88 报警阈值线**（折线跌破此线即刻推送微信）。
* **红色标点**：监测记录以来的历史极低值。
* 历史原始数据：[`price_history.csv`](./price_history.csv)。
