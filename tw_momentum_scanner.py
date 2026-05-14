import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import urllib3
import time

from io import StringIO
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# =====================================
# 關閉 SSL Warning
# =====================================
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =====================================
# Streamlit 設定
# =====================================
st.set_page_config(
    page_title="台股高動能掃描器",
    layout="wide"
)

st.title("🚀 台股高動能掃描器（全市場版）")

st.markdown("""
### 功能
- ✅ 自動抓取上市 / 上櫃 / ETF
- ✅ 超過 1800 檔股票
- ✅ 多線程高速掃描
- ✅ RSI + 動能分析
- ✅ 成交額過濾
- ✅ CSV下載
""")

# =====================================
# 掃描器類別
# =====================================
class TWStockScanner:

    def __init__(self):

        # 預設 5 億
        self.min_turnover = 5 * 100000000

        self.max_workers = 40

        self.stock_list = {}

    # =====================================
    # 抓取股票清單
    # =====================================
    def get_all_stocks(self):

        stocks = {}

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        try:

            def fetch_table(url):

                response = requests.get(
                    url,
                    headers=headers,
                    verify=False,
                    timeout=20
                )

                response.encoding = "utf-8"

                tables = pd.read_html(
                    StringIO(response.text)
                )

                df = tables[0]

                df.columns = df.iloc[0]

                df = df[1:]

                return df

            # =============================
            # 上市
            # =============================
            df_twse = fetch_table(
                "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            )

            for _, row in df_twse.iterrows():

                try:

                    code_name = str(
                        row["有價證券代號及名稱"]
                    )

                    parts = code_name.split()

                    if len(parts) < 2:
                        continue

                    stock_id = parts[0]

                    stock_name = " ".join(parts[1:])

                    if (
                        stock_id.isdigit()
                        and len(stock_id) == 4
                    ):

                        stocks[stock_id] = {
                            "name": stock_name,
                            "market": "上市"
                        }

                except:
                    continue

            # =============================
            # 上櫃
            # =============================
            df_otc = fetch_table(
                "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
            )

            for _, row in df_otc.iterrows():

                try:

                    code_name = str(
                        row["有價證券代號及名稱"]
                    )

                    parts = code_name.split()

                    if len(parts) < 2:
                        continue

                    stock_id = parts[0]

                    stock_name = " ".join(parts[1:])

                    if (
                        stock_id.isdigit()
                        and len(stock_id) == 4
                    ):

                        stocks[stock_id] = {
                            "name": stock_name,
                            "market": "上櫃"
                        }

                except:
                    continue

            # =============================
            # ETF
            # =============================
            df_etf = fetch_table(
                "https://isin.twse.com.tw/isin/C_public.jsp?strMode=7"
            )

            for _, row in df_etf.iterrows():

                try:

                    code_name = str(
                        row["有價證券代號及名稱"]
                    )

                    parts = code_name.split()

                    if len(parts) < 2:
                        continue

                    stock_id = parts[0]

                    stock_name = " ".join(parts[1:])

                    if (
                        stock_id.isdigit()
                        and len(stock_id) == 4
                    ):

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

    # =====================================
    # 分析單一股票
    # =====================================
    def analyze_stock(self, stock_id, market):

        try:

            suffix = ".TWO" if market == "上櫃" else ".TW"

            ticker = f"{stock_id}{suffix}"

            stock = yf.Ticker(ticker)

            hist = stock.history(
                period="1mo",
                auto_adjust=True
            )

            if hist.empty:
                return None

            hist = hist.dropna()

            # 最少 10 天資料
            if len(hist) < 10:
                return None

            close = hist["Close"]

            volume = hist["Volume"]

            turnover = close * volume

            avg_turnover = turnover.mean()

            # 成交額過濾
            if avg_turnover < self.min_turnover:
                return None

            # =============================
            # 漲幅計算
            # =============================
            r5_days = min(5, len(close)-1)

            r20_days = min(20, len(close)-1)

            r5 = (
                (close.iloc[-1] / close.iloc[-r5_days]) - 1
            ) * 100

            r20 = (
                (close.iloc[-1] / close.iloc[-r20_days]) - 1
            ) * 100

            # =============================
            # RSI
            # =============================
            delta = close.diff()

            gain = delta.where(delta > 0, 0)

            loss = -delta.where(delta < 0, 0)

            avg_gain = gain.rolling(14).mean()

            avg_loss = loss.rolling(14).mean()

            rs = avg_gain / avg_loss

            rsi = 100 - (100 / (1 + rs))

            latest_rsi = rsi.iloc[-1]

            if pd.isna(latest_rsi):
                latest_rsi = 50

            # =============================
            # 均線
            # =============================
            ma5 = close.tail(min(5, len(close))).mean()

            ma20 = close.mean()

            # =============================
            # 動能分數
            # =============================
            momentum_score = (
                r5 * 0.5 +
                r20 * 0.3 +
                latest_rsi * 0.2
            )

            return {

                "stock_id": stock_id,

                "stock_name":
                self.stock_list[stock_id]["name"],

                "market": market,

                "close":
                round(close.iloc[-1], 2),

                "return_5d":
                round(r5, 2),

                "return_20d":
                round(r20, 2),

                "rsi":
                round(latest_rsi, 2),

                "ma5":
                round(ma5, 2),

                "ma20":
                round(ma20, 2),

                "avg_turnover":
                round(avg_turnover / 100000000, 2),

                "momentum_score":
                round(momentum_score, 2),

                "stop_loss":
                round(close.iloc[-1] * 0.92, 2)
            }

        except Exception as e:

            return None

    # =====================================
    # 全市場掃描
    # =====================================
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

        with ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:

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
                    f"📈 掃描進度："
                    f"{completed}/{total} "
                    f"({progress*100:.1f}%)"
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

# =====================================
# Sidebar
# =====================================
st.sidebar.header("⚙️ 掃描設定")

min_turnover = st.sidebar.number_input(
    "最低平均成交額（億）",
    min_value=1,
    max_value=500,
    value=5,
    step=1
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
    min_value=10,
    max_value=80,
    value=40
)

st.sidebar.markdown("---")

st.sidebar.info("""
### 動能分數
- 5日漲幅 × 0.5
- 20日漲幅 × 0.3
- RSI × 0.2

### 注意
僅供研究用途  
非投資建議
""")

# =====================================
# 開始掃描
# =====================================
if st.button(
    "🚀 開始掃描全市場",
    type="primary",
    use_container_width=True
):

    scanner = TWStockScanner()

    scanner.min_turnover = (
        min_turnover * 100000000
    )

    scanner.max_workers = worker_count

    with st.spinner("⏳ 正在高速掃描市場..."):

        start_time = time.time()

        df = scanner.scan_market()

        elapsed = time.time() - start_time

    if not df.empty:

        st.success(
            f"✅ 掃描完成！找到 "
            f"{len(df)} 檔股票 "
            f"（耗時 {elapsed:.1f} 秒）"
        )

        st.balloons()

        # =====================================
        # 統計
        # =====================================
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            st.metric(
                "符合條件",
                len(df)
            )

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

        # =====================================
        # 表格
        # =====================================
        display_df = df.head(top_n).copy()

        display_df = display_df[
            [
                "stock_id",
                "stock_name",
                "market",
                "close",
                "return_5d",
                "return_20d",
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
            "RSI",
            "平均成交額(億)",
            "動能分數",
            "停損價"
        ]

        st.dataframe(
            display_df,
            use_container_width=True,
            height=700
        )

        # =====================================
        # CSV下載
        # =====================================
        csv = display_df.to_csv(
            index=False
        ).encode("utf-8-sig")

        st.download_button(
            label="📥 下載CSV",
            data=csv,
            file_name=f"tw_stock_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )

    else:

        st.warning(
            "⚠️ 沒有找到符合條件股票"
        )

# =====================================
# Footer
# =====================================
st.caption(
    f"""
📅 更新時間：
{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

資料來源：Yahoo Finance

⚠️ 僅供研究用途，非投資建議
"""
)