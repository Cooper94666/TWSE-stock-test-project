import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import urllib3
import time

from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# =========================
# SSL 修復
# =========================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =========================
# Streamlit 設定
# =========================
st.set_page_config(
    page_title="台股高動能掃描器",
    layout="wide"
)

st.title("🚀 台股高動能掃描器（全市場版）")

st.markdown("""
### 功能特色
- ✅ 自動抓取上市 / 上櫃 / ETF
- ✅ 超過 1800 檔股票
- ✅ 多線程高速掃描
- ✅ RSI + 動能分析
- ✅ 成交量過濾
- ✅ CSV下載
""")

# =========================
# Scanner Class
# =========================
class TWStockScanner:

    def __init__(self):

        self.min_turnover = 100_000_000_000
        self.max_workers = 20
        self.stock_list = {}

    # =========================
    # 取得股票清單
    # =========================
    def get_all_stocks(self):

        stocks = {}

        try:

            headers = {
                "User-Agent": "Mozilla/5.0"
            }

            def fetch_table(url):

                response = requests.get(
                    url,
                    headers=headers,
                    verify=False,
                    timeout=20
                )

                response.encoding = "utf-8"

                tables = pd.read_html(response.text)

                df = tables[0]

                df.columns = df.iloc[0]

                df = df[1:]

                return df

            # =====================
            # 上市
            # =====================
            df_twse = fetch_table(
                "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            )

            for _, row in df_twse.iterrows():

                try:

                    code_name = str(row["有價證券代號及名稱"])

                    parts = code_name.split()

                    if len(parts) < 2:
                        continue

                    stock_id = parts[0]
                    stock_name = " ".join(parts[1:])

                    if stock_id.isdigit() and len(stock_id) == 4:

                        stocks[stock_id] = {
                            "name": stock_name,
                            "market": "上市"
                        }

                except:
                    continue

            # =====================
            # 上櫃
            # =====================
            df_otc = fetch_table(
                "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
            )

            for _, row in df_otc.iterrows():

                try:

                    code_name = str(row["有價證券代號及名稱"])

                    parts = code_name.split()

                    if len(parts) < 2:
                        continue

                    stock_id = parts[0]
                    stock_name = " ".join(parts[1:])

                    if stock_id.isdigit() and len(stock_id) == 4:

                        stocks[stock_id] = {
                            "name": stock_name,
                            "market": "上櫃"
                        }

                except:
                    continue

            # =====================
            # ETF
            # =====================
            df_etf = fetch_table(
                "https://isin.twse.com.tw/isin/C_public.jsp?strMode=7"
            )

            for _, row in df_etf.iterrows():

                try:

                    code_name = str(row["有價證券代號及名稱"])

                    parts = code_name.split()

                    if len(parts) < 2:
                        continue

                    stock_id = parts[0]
                    stock_name = " ".join(parts[1:])

                    if stock_id.isdigit() and len(stock_id) == 4:

                        stocks[stock_id] = {
                            "name": stock_name,
                            "market": "ETF"
                        }

                except:
                    continue

            return stocks

        except Exception as e:

            st.error(f"❌ 股票清單取得失敗：{e}")

            return {}

    # =========================
    # 單一股票分析
    # =========================
    def analyze_stock(self, stock_id, market):

        try:

            suffix = ".TWO" if market == "上櫃" else ".TW"

            ticker = f"{stock_id}{suffix}"

            stock = yf.Ticker(ticker)

            hist = stock.history(
                period="3mo",
                auto_adjust=True
            )

            if hist.empty:
                return None

            hist = hist.dropna()

            if len(hist) < 25:
                return None

            close = hist["Close"]
            volume = hist["Volume"]

            turnover = close * volume

            avg_turnover = turnover.tail(20).mean()

            # 成交額過濾
            if avg_turnover < self.min_turnover:
                return None

            # 漲幅
            r5 = (
                (close.iloc[-1] / close.iloc[-5]) - 1
            ) * 100

            r20 = (
                (close.iloc[-1] / close.iloc[-20]) - 1
            ) * 100

            if len(close) >= 60:
                r60 = (
                    (close.iloc[-1] / close.iloc[-60]) - 1
                ) * 100
            else:
                r60 = 0

            # 均線
            ma5 = close.tail(5).mean()
            ma20 = close.tail(20).mean()

            # RSI
            delta = close.diff()

            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)

            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()

            rs = avg_gain / avg_loss

            rsi = 100 - (100 / (1 + rs))

            latest_rsi = rsi.iloc[-1]

            # 動能分數
            momentum_score = (
                r5 * 0.5 +
                r20 * 0.3 +
                latest_rsi * 0.2
            )

            return {
                "stock_id": stock_id,
                "stock_name": self.stock_list[stock_id]["name"],
                "market": market,
                "close": round(close.iloc[-1], 2),
                "return_5d": round(r5, 2),
                "return_20d": round(r20, 2),
                "return_60d": round(r60, 2),
                "avg_turnover": round(avg_turnover / 100000000, 2),
                "ma5": round(ma5, 2),
                "ma20": round(ma20, 2),
                "rsi": round(latest_rsi, 2),
                "momentum_score": round(momentum_score, 2),
                "stop_loss": round(close.iloc[-1] * 0.92, 2)
            }

        except:
            return None

    # =========================
    # 全市場掃描
    # =========================
    def scan_market(self):

        self.stock_list = self.get_all_stocks()

        if not self.stock_list:
            return pd.DataFrame()

        results = []

        stock_ids = list(self.stock_list.keys())

        total = len(stock_ids)

        progress_bar = st.progress(0)

        status = st.empty()

        completed = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:

            futures = {

                executor.submit(
                    self.analyze_stock,
                    stock_id,
                    self.stock_list[stock_id]["market"]
                ): stock_id

                for stock_id in stock_ids
            }

            for future in as_completed(futures):

                completed += 1

                progress = completed / total

                progress_bar.progress(progress)

                status.text(
                    f"📈 掃描進度：{completed}/{total} ({progress*100:.1f}%)"
                )

                result = future.result()

                if result:
                    results.append(result)

        progress_bar.empty()
        status.empty()

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)

        df = df.sort_values(
            by="momentum_score",
            ascending=False
        )

        return df

# =========================
# Sidebar
# =========================
st.sidebar.header("⚙️ 掃描設定")

min_turnover = st.sidebar.number_input(
    "最低20日均成交額（億）",
    min_value=10,
    max_value=500,
    value=100,
    step=10
)

top_n = st.sidebar.number_input(
    "顯示前幾名",
    min_value=10,
    max_value=200,
    value=50,
    step=10
)

worker_count = st.sidebar.slider(
    "多線程數量",
    min_value=5,
    max_value=50,
    value=20
)

st.sidebar.markdown("---")

st.sidebar.info("""
### 動能分數
- 5日漲幅 × 0.5
- 20日漲幅 × 0.3
- RSI × 0.2

### 注意
僅供研究參考
非投資建議
""")

# =========================
# 開始掃描
# =========================
if st.button(
    "🚀 開始掃描全市場",
    type="primary",
    use_container_width=True
):

    scanner = TWStockScanner()

    scanner.min_turnover = min_turnover * 100000000

    scanner.max_workers = worker_count

    with st.spinner("⏳ 正在高速掃描市場..."):

        start = time.time()

        df = scanner.scan_market()

        elapsed = time.time() - start

    if not df.empty:

        st.success(
            f"✅ 掃描完成！找到 {len(df)} 檔股票 "
            f"（耗時 {elapsed:.1f} 秒）"
        )

        st.balloons()

        # =====================
        # 統計
        # =====================
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric("符合條件", len(df))

        with c2:
            st.metric(
                "平均5日漲幅",
                f"{df['return_5d'].mean():.2f}%"
            )

        with c3:
            st.metric(
                "平均20日漲幅",
                f"{df['return_20d'].mean():.2f}%"
            )

        with c4:
            st.metric(
                "最高動能",
                f"{df['momentum_score'].max():.2f}"
            )

        # =====================
        # 表格
        # =====================
        display_df = df.head(top_n).copy()

        display_df = display_df[
            [
                "stock_id",
                "stock_name",
                "market",
                "close",
                "return_5d",
                "return_20d",
                "return_60d",
                "rsi",
                "avg_turnover",
                "momentum_score",
                "stop_loss"
            ]
        ]

        display_df.columns = [
            "代碼",
            "名稱",
            "市場",
            "收盤價",
            "5日漲幅%",
            "20日漲幅%",
            "60日漲幅%",
            "RSI",
            "20日均成交(億)",
            "動能分數",
            "停損價"
        ]

        st.dataframe(
            display_df,
            use_container_width=True,
            height=700
        )

        # =====================
        # CSV下載
        # =====================
        csv = display_df.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            label="📥 下載CSV",
            data=csv,
            file_name=f"momentum_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

    else:

        st.warning("⚠️ 找不到符合條件股票")

# =========================
# Footer
# =========================
st.caption(
    f"""
📅 更新時間：
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

資料來源：Yahoo Finance
僅供研究用途，非投資建議
"""
)