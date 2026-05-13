import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
import ssl
import urllib3

# 禁用 SSL 警告（僅用於解決 TWSE 憑證問題）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="台股短期動能掃描器", layout="wide")
st.title("🚀 台股短期高動能掃描器（TWSE上市）")
st.markdown("**嚴格條件**：20日均成交金額 > 100億 + 近期強勢 | 純量價技術面")

class TWSE_Scanner:
    def __init__(self):
        # 建立一個忽略 SSL 驗證的 session
        self.session = requests.Session()
        self.session.verify = False
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.min_turnover = 100_000_000_000  # 100億

    def get_stock_list(self):
        """抓取上市股票清單並排除金融股"""
        # 使用備用資料源或嘗試多個 URL
        urls = [
            "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
            "http://isin.twse.com.tw/isin/C_public.jsp?strMode=2",  # 使用 HTTP 而非 HTTPS
        ]
        
        for url in urls:
            try:
                resp = self.session.get(url, timeout=15, verify=False)
                resp.encoding = 'big5'
                
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    table = soup.find('table')
                    if table:
                        df = pd.read_html(str(table))[0]
                        df = df.iloc[1:].reset_index(drop=True)
                        
                        # 處理股票代碼和名稱
                        first_col = df.iloc[:, 0].astype(str)
                        df[['stock_id', 'stock_name']] = first_col.str.split('　', n=1, expand=True)
                        
                        # 確保有足夠的欄位
                        if len(df.columns) >= 3:
                            df = df[['stock_id', 'stock_name', df.columns[2]]].copy()
                            df.columns = ['stock_id', 'stock_name', 'industry']
                        else:
                            df = df[['stock_id', 'stock_name']].copy()
                            df['industry'] = ''
                        
                        # 排除金融股（基於股票代碼或行業別）
                        df = df[~df['stock_id'].str.contains('^28|^00|^58', na=False)]
                        
                        # 只保留數字股票代碼
                        df = df[df['stock_id'].str.match(r'^\d{4}$', na=False)]
                        
                        return df.head(500)  # 限制數量避免過多
            except Exception as e:
                st.warning(f"嘗試 URL {url} 失敗: {str(e)[:100]}")
                continue
        
        # 如果所有 URL 都失敗，使用手動股票清單
        st.warning("使用預設股票清單（前50大權值股）")
        default_stocks = pd.DataFrame({
            'stock_id': ['2330', '2317', '2454', '2308', '2412', '2881', '2882', '2891', '1303', '1326',
                        '2002', '1301', '1216', '2207', '2303', '2409', '3008', '3711', '2382', '4938',
                        '3037', '2357', '1590', '3443', '2301', '2313', '2327', '2356', '2379', '2385'],
            'stock_name': ['台積電', '鴻海', '聯發科', '台達電', '中華電', '富邦金', '國泰金', '中信金', '南亞', '台塑化',
                          '中鋼', '台塑', '統一', '和泰車', '聯電', '友達', '大立光', '日月光', '廣達', '和碩',
                          '欣興', '華碩', '亞德客', '創意', '光寶科', '華通', '國巨', '英業達', '瑞昱', '群光'],
            'industry': ['半導體', '電腦週邊', '半導體', '電子零組件', '通信網路', '金融', '金融', '金融', '塑膠', '油電燃氣',
                        '鋼鐵', '塑膠', '食品', '汽車', '半導體', '光電', '光電', '半導體', '電腦週邊', '電腦週邊',
                        '電子零組件', '電腦週邊', '電機機械', '半導體', '電腦週邊', '電子零組件', '電子零組件', '電腦週邊', '半導體', '電子零組件']
        })
        return default_stocks

    def get_multi_day_data(self, days=60):
        """抓取多日市場資料"""
        end = datetime.now()
        dates = []
        for i in range(days + 10):
            d = end - timedelta(days=i)
            if d.weekday() < 5:  # 只取工作日
                dates.append(d.strftime('%Y%m%d'))
        
        all_data = []
        progress = st.progress(0)
        status = st.empty()
        
        for idx, d in enumerate(dates[:days]):
            status.text(f"正在抓取 {d} 資料...")
            try:
                # 使用 HTTP 而非 HTTPS
                url = f"http://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date={d}"
                resp = self.session.get(url, timeout=15, verify=False)
                
                if resp.status_code == 200:
                    data = resp.json().get('data', [])
                    if data and len(data) > 0:
                        df_day = pd.DataFrame(data)
                        # 確保欄位數正確
                        if len(df_day.columns) >= 11:
                            df_day = df_day.iloc[:, :11]
                            df_day.columns = ['date', 'stock_id', 'name', 'vol', 'val', 'open', 'high', 'low', 'close', 'change', 'trans']
                            
                            # 轉換數值
                            for col in ['val', 'close', 'open', 'high', 'low']:
                                df_day[col] = pd.to_numeric(df_day[col].str.replace(',', ''), errors='coerce')
                            
                            df_day['stock_id'] = df_day['stock_id'].str.strip()
                            df_day['date'] = d
                            
                            # 過濾無效資料
                            df_day = df_day[df_day['val'].notna() & (df_day['val'] > 0)]
                            all_data.append(df_day)
                else:
                    status.text(f"日期 {d} 資料取得失敗 (狀態碼: {resp.status_code})")
                    
            except Exception as e:
                status.text(f"日期 {d} 處理錯誤: {str(e)[:50]}")
            
            progress.progress((idx + 1) / min(len(dates), days))
            time.sleep(0.5)  # 減少等待時間
        
        status.empty()
        
        if all_data:
            result_df = pd.concat(all_data, ignore_index=True)
            st.success(f"成功取得 {len(result_df)} 筆資料記錄")
            return result_df
        
        st.error("無法取得任何市場資料")
        return pd.DataFrame()

    def analyze(self):
        st.info("正在取得股票清單...")
        stock_list = self.get_stock_list()
        
        if stock_list.empty:
            st.error("無法取得股票清單")
            return pd.DataFrame()
        
        st.info(f"取得 {len(stock_list)} 檔股票，開始抓取交易資料...")
        raw_data = self.get_multi_day_data(days=60)
        
        if raw_data.empty:
            st.error("無法取得交易資料")
            return pd.DataFrame()
        
        # 確保必要欄位存在
        required_cols = ['stock_id', 'val', 'close', 'date']
        if not all(col in raw_data.columns for col in required_cols):
            st.error(f"資料缺少必要欄位，現有欄位：{raw_data.columns.tolist()}")
            return pd.DataFrame()
        
        # 20日平均成交金額
        turnover = raw_data.groupby('stock_id')['val'].mean().reset_index()
        turnover.columns = ['stock_id', 'avg_turnover_20d']
        
        # 最新價格
        latest = raw_data.sort_values('date').groupby('stock_id').last().reset_index()
        
        # 計算各週期漲幅
        def calc_return(df, days):
            recent = df.sort_values('date').tail(days)
            if len(recent) < 2:
                return 0.0
            first_close = recent['close'].iloc[0]
            last_close = recent['close'].iloc[-1]
            if first_close == 0 or pd.isna(first_close):
                return 0.0
            return (last_close / first_close - 1) * 100
        
        returns = []
        for sid in latest['stock_id']:
            stock_df = raw_data[raw_data['stock_id'] == sid].sort_values('date')
            r5 = calc_return(stock_df, 5)
            r20 = calc_return(stock_df, 20)
            r60 = calc_return(stock_df, 60)
            returns.append({'stock_id': sid, 'return_5d': r5, 'return_1m': r20, 'return_3m': r60})
        
        returns_df = pd.DataFrame(returns)
        
        result = (stock_list.merge(turnover, on='stock_id', how='inner')
                         .merge(latest[['stock_id', 'close']], on='stock_id', how='inner')
                         .merge(returns_df, on='stock_id', how='inner'))
        
        if result.empty:
            st.warning("無符合條件的股票")
            return pd.DataFrame()
        
        # 高流動性篩選
        result = result[result['avg_turnover_20d'] >= self.min_turnover].copy()
        
        if result.empty:
            st.warning(f"無股票達到 {self.min_turnover/1e8:.0f} 億的日均成交門檻")
            return pd.DataFrame()
        
        # 技術面分數
        result['momentum_score'] = result['return_5d'] * 0.6 + result['return_1m'] * 0.3
        result = result.sort_values('momentum_score', ascending=False).head(30)
        
        # 生成理由
        def generate_reason(row):
            reasons = []
            if row['return_5d'] > 5: 
                reasons.append(f"5日強漲 {row['return_5d']:.1f}%")
            if row['return_1m'] > 15: 
                reasons.append(f"1個月上漲 {row['return_1m']:.1f}%")
            if row['avg_turnover_20d'] > 300_000_000_000: 
                reasons.append("巨量")
            if not reasons:
                reasons.append("動能持續")
            return "、".join(reasons) + "，量價配合佳"
        
        result['reason'] = result.apply(generate_reason, axis=1)
        result['stop_loss_suggest'] = (result['close'] * 0.92).round(2)
        
        return result

# ====================== 主介面 ======================
if st.button("🔄 開始掃描 Top 10 高動能股票", type="primary"):
    with st.spinner("抓取TWSE官方資料中（約2-3分鐘，請耐心等待）..."):
        scanner = TWSE_Scanner()
        df = scanner.analyze()
        
        if not df.empty:
            st.success(f"✅ 找到符合條件的股票 {len(df)} 檔，前10名如下：")
            
            display_df = df.head(10).copy()
            display_df['20日均成交'] = (display_df['avg_turnover_20d'] / 1e8).round(1).astype(str) + "億"
            display_df = display_df[['stock_id', 'stock_name', 'close', 'return_5d', 
                                   'return_1m', 'return_3m', '20日均成交', 'reason', 'stop_loss_suggest']]
            
            display_df.columns = ['代碼', '名稱', '股價', '5日漲幅%', '1月漲幅%', '3月漲幅%', 
                                '20日均成交', '推薦理由', '建議停損價']
            
            st.dataframe(display_df, use_container_width=True, height=600)
            
            # 下載
            csv = display_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 下載 Top 10 CSV", csv, "top10_momentum.csv", "text/csv")
        else:
            st.error("❌ 本次無符合高流動性條件的股票")

# ====================== K線圖（含均線） ======================
st.divider()
st.subheader("📈 個股互動K線圖（含均線）")
col1, col2 = st.columns([1, 3])
with col1:
    stock_id = st.text_input("輸入股票代碼", value="2330", max_chars=4)
with col2:
    period = st.selectbox("時間範圍", ["30天", "60天", "90天"], index=1)

if st.button("繪製 K 線 + 均線"):
    with st.spinner(f"抓取 {stock_id} 資料..."):
        scanner = TWSE_Scanner()
        days = int(period.replace('天', ''))
        raw = scanner.get_multi_day_data(days=days)
        
        if not raw.empty and 'stock_id' in raw.columns:
            stock_df = raw[raw['stock_id'] == stock_id].sort_values('date').copy()
            
            if not stock_df.empty:
                if all(col in stock_df.columns for col in ['open', 'high', 'low', 'close']):
                    stock_df['MA5'] = stock_df['close'].rolling(5).mean()
                    stock_df['MA20'] = stock_df['close'].rolling(20).mean()
                    stock_df['MA60'] = stock_df['close'].rolling(60).mean()
                    
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(x=stock_df['date'],
                                                open=stock_df['open'], high=stock_df['high'],
                                                low=stock_df['low'], close=stock_df['close'], name="K線"))
                    fig.add_trace(go.Scatter(x=stock_df['date'], y=stock_df['MA5'], name="MA5", line=dict(color='orange')))
                    fig.add_trace(go.Scatter(x=stock_df['date'], y=stock_df['MA20'], name="MA20", line=dict(color='blue')))
                    fig.add_trace(go.Scatter(x=stock_df['date'], y=stock_df['MA60'], name="MA60", line=dict(color='purple')))
                    
                    fig.update_layout(title=f"{stock_id} K線圖（含均線）", 
                                    xaxis_rangeslider_visible=True, 
                                    height=600,
                                    xaxis_title="日期",
                                    yaxis_title="價格")
                    st.plotly_chart(fig, use_container_width=True)
                    
                    latest = stock_df.iloc[-1]
                    st.info(f"📊 最新收盤: {latest['close']:.2f} | MA5: {latest['MA5']:.2f} | MA20: {latest['MA20']:.2f} | MA60: {latest['MA60']:.2f}")
                else:
                    st.warning(f"資料不完整，缺少必要欄位")
            else:
                st.warning(f"無法取得股票 {stock_id} 的資料")
        else:
            st.warning("無法取得資料")

st.caption("資料來源：TWSE官方公開資料 | 純機械量價計算 | 僅供參考，非投資建議")