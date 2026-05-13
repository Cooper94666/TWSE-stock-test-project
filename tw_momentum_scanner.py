import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
import yfinance as yf
import io

st.set_page_config(page_title="台股短期動能掃描器", layout="wide")
st.title("🚀 台股短期高動能掃描器 - 全市場掃描")
st.markdown("**篩選條件**：20日均成交金額 > 100億 + 近期強勢 | 涵蓋所有上市股票")

class TWSE_Scanner:
    def __init__(self):
        self.min_turnover = 100_000_000_000  # 100億台幣
        self.all_stocks = {}  # 儲存所有股票

    def get_all_twse_stocks(self):
        """從證交所抓取所有上市股票清單"""
        try:
            # 方法1: 從證交所API獲取
            url = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
            resp = requests.get(url, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                stocks = {}
                for item in data:
                    stock_id = item.get('公司代號', '')
                    stock_name = item.get('公司名稱', '')
                    industry = item.get('產業別', '')
                    
                    # 只保留4碼數字的股票，排除認購權證、ETF等
                    if stock_id.isdigit() and len(stock_id) == 4:
                        # 排除金融股（可選）
                        # if not stock_id.startswith('28'):
                        stocks[stock_id] = {
                            'name': stock_name,
                            'industry': industry
                        }
                
                if stocks:
                    st.success(f"✅ 成功從證交所取得 {len(stocks)} 檔上市股票")
                    return stocks
            
            # 方法2: 備用方案 - 從證交所網頁抓取
            url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
            resp = requests.get(url, timeout=15)
            resp.encoding = 'big5'
            
            # 手動解析HTML表格
            import re
            stocks = {}
            lines = resp.text.split('\n')
            
            for line in lines:
                # 尋找股票代碼和名稱的模式
                match = re.search(r'(\d{4})　([^<]+)', line)
                if match:
                    stock_id = match.group(1)
                    stock_name = match.group(2).strip()
                    # 排除權證、ETF、受益憑證等
                    if not any(x in stock_name for x in ['權證', 'ETF', '受益憑證', '認購', '認售', '基金']):
                        if not stock_id.startswith(('00', '01')):  # 排除債券等
                            stocks[stock_id] = {
                                'name': stock_name,
                                'industry': '一般'
                            }
            
            if stocks:
                st.success(f"✅ 成功從證交所取得 {len(stocks)} 檔上市股票")
                return stocks
            
        except Exception as e:
            st.warning(f"從證交所抓取失敗: {str(e)[:100]}")
        
        # 方法3: 最後備案 - 使用預設清單但範圍更大
        st.info("使用擴充股票清單（台灣中型100 + 其他熱門股）")
        default_stocks = {
            # 電子股
            '2330': '台積電', '2317': '鴻海', '2454': '聯發科', '2303': '聯電', 
            '3443': '創意', '3035': '智原', '2379': '瑞昱', '3034': '聯詠',
            '2458': '義隆', '8016': '矽創', '5274': '信驊', '5269': '祥碩',
            '2382': '廣達', '3231': '緯創', '2356': '英業達', '4938': '和碩',
            '2324': '仁寶', '2353': '宏碁', '2357': '華碩', '2376': '技嘉',
            '2377': '微星', '2301': '光寶科', '2308': '台達電', '2327': '國巨',
            '2492': '華新科', '3044': '健鼎', '3037': '欣興', '3189': '景碩',
            '8046': '南電', '2313': '華通', '2368': '金像電', '2383': '台光電',
            '4958': '臻鼎-KY', '3008': '大立光', '2409': '友達', '3481': '群創',
            '2412': '中華電', '2345': '智邦', '5388': '中磊', '3596': '智易',
            '6285': '啟碁', '4904': '遠傳', '3045': '台灣大',
            # 傳產股
            '1301': '台塑', '1303': '南亞', '1326': '台塑化', '2002': '中鋼',
            '2014': '中鴻', '2027': '大成鋼', '1216': '統一', '1101': '台泥',
            '1102': '亞泥', '1402': '遠東新', '1504': '東元', '1605': '華新',
            '2207': '和泰車', '2201': '裕隆', '2105': '正新', '2106': '建大',
            '1907': '永豐餘', '1476': '儒鴻', '1477': '聚陽',
            # 金融股（如果需要）
            '2881': '富邦金', '2882': '國泰金', '2891': '中信金', '2886': '兆豐金',
            '2892': '第一金', '5880': '合庫金', '2884': '玉山金', '2885': '元大金',
            '2880': '華南金', '2883': '開發金', '2887': '台新金', '2888': '新光金'
        }
        
        stocks = {k: {'name': v, 'industry': '一般'} for k, v in default_stocks.items()}
        st.warning(f"使用備用清單，共 {len(stocks)} 檔股票")
        return stocks

    def get_stock_data(self, stock_id, period='60d'):
        """從 Yahoo Finance 獲取股票資料"""
        try:
            ticker = f"{stock_id}.TW"
            stock = yf.Ticker(ticker)
            
            # 獲取歷史資料
            hist = stock.history(period=period)
            
            if hist.empty or len(hist) < 5:
                return None
            
            # 計算成交金額
            volume = hist['Volume']
            close = hist['Close']
            turnover = volume * close
            
            df = pd.DataFrame({
                'date': hist.index,
                'stock_id': stock_id,
                'open': hist['Open'],
                'high': hist['High'],
                'low': hist['Low'],
                'close': hist['Close'],
                'volume': hist['Volume'],
                'turnover': turnover
            })
            
            return df
        except Exception:
            return None

    def analyze_all_stocks(self):
        """分析所有股票"""
        # 先獲取所有股票清單
        self.all_stocks = self.get_all_twse_stocks()
        
        if not self.all_stocks:
            st.error("無法取得股票清單")
            return pd.DataFrame()
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        stock_ids = list(self.all_stocks.keys())
        total_stocks = len(stock_ids)
        
        st.info(f"📊 共 {total_stocks} 檔股票需要分析，預計需要 {total_stocks * 1.5 / 60:.1f} 分鐘")
        
        # 建立一個容器來顯示即時結果
        result_container = st.empty()
        
        for idx, stock_id in enumerate(stock_ids):
            stock_name = self.all_stocks[stock_id]['name']
            status_text.text(f"📈 分析進度: {idx+1}/{total_stocks} - {stock_id} {stock_name}")
            
            # 獲取資料
            df = self.get_stock_data(stock_id, period='60d')
            
            if df is not None and len(df) >= 20:
                # 計算20日均成交金額
                avg_turnover = df['turnover'].tail(20).mean()
                
                # 高流動性篩選
                if avg_turnover >= self.min_turnover:
                    # 計算漲跌幅
                    closes = df['close'].values
                    r5 = ((closes[-1] / closes[-min(5, len(closes))] - 1) * 100) if len(closes) >= 5 else 0
                    r20 = ((closes[-1] / closes[-min(20, len(closes))] - 1) * 100) if len(closes) >= 20 else 0
                    r60 = ((closes[-1] / closes[0] - 1) * 100) if len(closes) >= 60 else 0
                    
                    result = {
                        'stock_id': stock_id,
                        'stock_name': stock_name,
                        'industry': self.all_stocks[stock_id].get('industry', '一般'),
                        'close': closes[-1],
                        'return_5d': r5,
                        'return_20d': r20,
                        'return_60d': r60,
                        'avg_turnover_20d': avg_turnover,
                        'momentum_score': r5 * 0.6 + r20 * 0.3
                    }
                    results.append(result)
                    
                    # 即時顯示找到的股票
                    if len(results) % 5 == 0:
                        temp_df = pd.DataFrame(results).sort_values('momentum_score', ascending=False)
                        result_container.info(f"📌 已找到 {len(results)} 檔符合條件的股票")
            
            # 更新進度
            progress_bar.progress((idx + 1) / total_stocks)
            
            # 避免請求過快
            time.sleep(0.3)
        
        status_text.empty()
        progress_bar.empty()
        
        if not results:
            return pd.DataFrame()
        
        # 轉換為 DataFrame 並排序
        result_df = pd.DataFrame(results)
        result_df = result_df.sort_values('momentum_score', ascending=False)
        
        # 計算停損價
        result_df['stop_loss'] = (result_df['close'] * 0.92).round(2)
        
        return result_df

# ====================== 主介面 ======================
st.markdown("---")

# 設定篩選條件
col1, col2 = st.columns(2)
with col1:
    min_turnover_billion = st.number_input(
        "最低日均成交金額（億台幣）",
        min_value=10,
        max_value=500,
        value=100,
        step=10,
        help="篩選條件：20日均成交金額需大於此值"
    )
with col2:
    top_n = st.number_input(
        "顯示前幾名",
        min_value=10,
        max_value=100,
        value=30,
        step=10,
        help="顯示動能分數最高的前N名股票"
    )

if st.button("🔍 開始掃描全市場高動能股票", type="primary", use_container_width=True):
    scanner = TWSE_Scanner()
    scanner.min_turnover = min_turnover_billion * 100_000_000
    
    with st.spinner("⏳ 正在分析全市場股票，請耐心等待（約5-10分鐘）..."):
        df = scanner.analyze_all_stocks()
        
        if not df.empty:
            st.success(f"✅ 找到 {len(df)} 檔符合高流動性條件的股票")
            
            # 準備顯示資料
            display_df = df.head(top_n).copy()
            display_df['return_5d'] = display_df['return_5d'].round(1)
            display_df['return_20d'] = display_df['return_20d'].round(1)
            display_df['return_60d'] = display_df['return_60d'].round(1)
            display_df['20日均成交'] = (display_df['avg_turnover_20d'] / 1e8).round(1).astype(str) + "億"
            display_df['收盤價'] = display_df['close'].round(2)
            
            display_cols = ['stock_id', 'stock_name', 'industry', '收盤價', 'return_5d', 
                           'return_20d', 'return_60d', '20日均成交', 'momentum_score', 'stop_loss']
            display_df = display_df[display_cols]
            
            display_df.columns = ['代碼', '名稱', '產業', '收盤價', '5日漲幅%', '20日漲幅%', 
                                '60日漲幅%', '20日均成交', '動能分數', '建議停損價']
            
            # 顯示統計資訊
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("符合條件股票", len(df))
            with col2:
                st.metric("平均5日漲幅", f"{display_df['5日漲幅%'].mean():.1f}%")
            with col3:
                st.metric("平均20日漲幅", f"{display_df['20日漲幅%'].mean():.1f}%")
            with col4:
                st.metric("平均動能分數", f"{display_df['動能分數'].mean():.1f}")
            
            # 顯示表格
            st.dataframe(display_df, use_container_width=True, height=500)
            
            # 產業分布圖
            st.subheader("📊 產業分布")
            industry_counts = display_df['產業'].value_counts().head(10)
            st.bar_chart(industry_counts)
            
            # 顯示前10名詳細資訊
            st.subheader("🏆 前10強動能股")
            for idx, row in display_df.head(10).iterrows():
                with st.container():
                    col1, col2, col3, col4, col5, col6 = st.columns([1, 1.5, 1.2, 1.2, 1.5, 1.5])
                    with col1:
                        st.metric("排名", idx+1)
                    with col2:
                        st.metric("代碼/名稱", f"{row['代碼']}\n{row['名稱']}")
                    with col3:
                        st.metric("股價", f"{row['收盤價']:.1f}")
                    with col4:
                        delta_color = "normal" if row['5日漲幅%'] >= 0 else "inverse"
                        st.metric("5日漲幅", f"{row['5日漲幅%']:.1f}%", 
                                 delta=f"{row['5日漲幅%']:.1f}%" if row['5日漲幅%'] >= 0 else f"{row['5日漲幅%']:.1f}%")
                    with col5:
                        st.metric("20日漲幅", f"{row['20日漲幅%']:.1f}%")
                    with col6:
                        st.metric("20日均成交", row['20日均成交'])
                    st.divider()
            
            # 下載功能
            csv = display_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載完整報告 (CSV)",
                data=csv,
                file_name=f"all_stocks_momentum_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )
        else:
            st.warning(f"⚠️ 無股票達到 {min_turnover_billion} 億的日均成交門檻，請降低門檻試試")

# 側邊欄說明
with st.sidebar:
    st.header("📌 使用說明")
    st.markdown("""
    **篩選邏輯**：
    - 20日均成交金額 ≥ 設定門檻
    - 動能分數 = 5日漲幅×0.6 + 20日漲幅×0.3
    - 建議停損價 = 股價 × 0.92
    
    **資料範圍**：
    - 涵蓋所有上市股票（約900-1000檔）
    - 資料來源：Yahoo Finance
    - 自動排除權證、ETF等
    
    **分析時間**：
    - 約需5-10分鐘
    - 進度條會顯示即時進度
    - 可即時看到找到的股票
    
    **注意事項**：
    - 僅供參考，非投資建議
    - 高動能伴隨高風險
    - 建議搭配基本面分析
    """)
    
    st.warning("⚠️ 免責聲明：本工具僅供參考，所有數據來自公開資訊，投資決策請自行判斷")

st.caption(f"最後更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 資料來源：TWSE + Yahoo Finance")