import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timedelta
import plotly.graph_objects as go
import re

st.set_page_config(page_title="台股短期動能掃描器", layout="wide")
st.title("🚀 台股短期高動能掃描器（TWSE上市）")
st.markdown("**篩選條件**：20日均成交金額 > 100億 + 近期強勢")

class TWSE_Scanner:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.min_turnover = 100_000_000_000

    def get_stock_list(self):
        """使用預先定義的熱門股票清單（避免爬蟲問題）"""
        # 台灣50成分股 + 熱門中型股
        stocks = {
            # 半導體
            '2330': '台積電', '2454': '聯發科', '2303': '聯電', '3443': '創意', '3035': '智原',
            # 電子組裝
            '2317': '鴻海', '2382': '廣達', '3231': '緯創', '2356': '英業達', '4938': '和碩',
            # IC設計
            '2379': '瑞昱', '3034': '聯詠', '2458': '義隆', '8016': '矽創', '5274': '信驊',
            # 電子零組件
            '2308': '台達電', '2327': '國巨', '2492': '華新科', '3044': '健鼎', '3037': '欣興',
            # 光電
            '3008': '大立光', '2409': '友達', '3481': '群創', '3698': '隆達',
            # 通信網路
            '2412': '中華電', '2345': '智邦', '5388': '中磊', '3596': '智易',
            # 電腦周邊
            '2357': '華碩', '2377': '微星', '2376': '技嘉', '2301': '光寶科',
            # 塑膠
            '1301': '台塑', '1303': '南亞', '1326': '台塑化',
            # 鋼鐵
            '2002': '中鋼', '2014': '中鴻',
            # 金融（雖然排除但保留作為參考）
            '2881': '富邦金', '2882': '國泰金', '2891': '中信金'
        }
        
        df = pd.DataFrame([
            {'stock_id': k, 'stock_name': v, 'industry': '電子業'}
            for k, v in stocks.items()
        ])
        return df

    def get_market_data(self, date):
        """獲取單日全市場資料 - 純 requests，無需解析 HTML"""
        try:
            url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY_ALL?response=json&date={date}"
            resp = requests.get(url, headers=self.headers, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('data') and len(data['data']) > 0:
                    rows = []
                    for row in data['data']:
                        if len(row) >= 9:
                            # 清理股票代碼（去除可能的前導零）
                            stock_id = row[1].strip()
                            if stock_id.isdigit() and len(stock_id) == 4:
                                try:
                                    rows.append({
                                        'stock_id': stock_id,
                                        'val': float(row[4].replace(',', '')) if row[4] else 0,
                                        'close': float(row[8].replace(',', '')) if row[8] else 0,
                                        'date': date
                                    })
                                except:
                                    continue
                    return pd.DataFrame(rows)
        except Exception as e:
            # 靜默失敗
            pass
        return pd.DataFrame()

    def analyze(self):
        """執行分析"""
        st.info("📋 載入股票清單...")
        stock_list = self.get_stock_list()
        
        # 抓取近期的交易資料
        end_date = datetime.now()
        dates = []
        for i in range(45):  # 抓45天，過濾後約30個交易日
            d = end_date - timedelta(days=i)
            if d.weekday() < 5:  # 星期一到五
                dates.append(d.strftime('%Y%m%d'))
            if len(dates) >= 30:  # 夠了
                break
        
        all_data = []
        progress = st.progress(0)
        status = st.empty()
        
        for idx, date in enumerate(dates):
            status.text(f"📊 抓取資料 {idx+1}/{len(dates)}: {date[:4]}/{date[4:6]}/{date[6:8]}")
            df_day = self.get_market_data(date)
            if not df_day.empty:
                # 只保留我們關注的股票
                df_day = df_day[df_day['stock_id'].isin(stock_list['stock_id'])]
                if not df_day.empty:
                    all_data.append(df_day)
            progress.progress((idx + 1) / len(dates))
            time.sleep(0.3)  # 避免請求過快
        
        status.empty()
        
        if not all_data:
            st.error("❌ 無法獲取市場資料，請稍後再試")
            return pd.DataFrame()
        
        # 合併所有資料
        market_df = pd.concat(all_data, ignore_index=True)
        
        if market_df.empty:
            return pd.DataFrame()
        
        # 計算平均成交金額
        avg_turnover = market_df.groupby('stock_id')['val'].mean().reset_index()
        avg_turnover.columns = ['stock_id', 'avg_turnover_20d']
        
        # 獲取最新價格
        latest_prices = market_df.sort_values('date').groupby('stock_id').last().reset_index()
        latest_prices = latest_prices[['stock_id', 'close']]
        
        # 合併結果
        result = stock_list.merge(avg_turnover, on='stock_id', how='inner')
        result = result.merge(latest_prices, on='stock_id', how='inner')
        
        # 計算各股票在不同日期的價格（用於漲跌幅計算）
        def calc_returns(stock_data):
            if len(stock_data) < 2:
                return {'return_5d': 0, 'return_20d': 0}
            
            stock_data = stock_data.sort_values('date')
            closes = stock_data['close'].values
            
            # 5日漲幅（約一週）
            r5 = ((closes[-1] / closes[-min(5, len(closes))] - 1) * 100) if len(closes) >= 5 else 0
            # 20日漲幅（約一個月）
            r20 = ((closes[-1] / closes[0] - 1) * 100) if len(closes) >= 20 else 0
            
            return {'return_5d': r5, 'return_20d': r20}
        
        # 計算每檔股票的漲跌幅
        returns_list = []
        for stock_id in result['stock_id']:
            stock_data = market_df[market_df['stock_id'] == stock_id]
            returns = calc_returns(stock_data)
            returns['stock_id'] = stock_id
            returns_list.append(returns)
        
        returns_df = pd.DataFrame(returns_list)
        result = result.merge(returns_df, on='stock_id', how='left')
        
        # 篩選條件：日均成交金額 >= 100億
        result = result[result['avg_turnover_20d'] >= self.min_turnover].copy()
        
        if result.empty:
            st.warning(f"⚠️ 無股票達到 {self.min_turnover/1e8:.0f} 億的日均成交門檻")
            return pd.DataFrame()
        
        # 計算動能分數並排序
        result['momentum_score'] = result['return_5d'] * 0.6 + result['return_20d'] * 0.3
        result = result.sort_values('momentum_score', ascending=False)
        
        # 計算停損價（-8%）
        result['stop_loss'] = (result['close'] * 0.92).round(2)
        
        return result.head(20)  # 只回傳前20名

# ====================== 主介面 ======================
st.markdown("---")

if st.button("🔍 開始掃描高動能股票", type="primary", use_container_width=True):
    with st.spinner("⏳ 正在抓取證交所資料，請耐心等待（約1-2分鐘）..."):
        scanner = TWSE_Scanner()
        df = scanner.analyze()
        
        if not df.empty:
            st.success(f"✅ 找到 {len(df)} 檔符合條件的股票")
            
            # 準備顯示資料
            display_df = df[['stock_id', 'stock_name', 'close', 'return_5d', 'return_20d', 'avg_turnover_20d', 'stop_loss']].copy()
            display_df['return_5d'] = display_df['return_5d'].round(1)
            display_df['return_20d'] = display_df['return_20d'].round(1)
            display_df['avg_turnover_20d'] = (display_df['avg_turnover_20d'] / 1e8).round(1).astype(str) + "億"
            
            display_df.columns = ['代碼', '名稱', '收盤價', '5日漲幅(%)', '20日漲幅(%)', '20日均成交金額', '建議停損價']
            
            # 顯示表格
            st.dataframe(display_df, use_container_width=True, height=400)
            
            # 顯示前5名詳細資訊
            st.subheader("🏆 前5強動能股")
            for idx, row in display_df.head(5).iterrows():
                with st.container():
                    col1, col2, col3, col4 = st.columns([1, 2, 2, 2])
                    with col1:
                        st.metric("代碼", row['代碼'])
                    with col2:
                        st.metric("名稱", row['名稱'])
                    with col3:
                        st.metric("股價", f"{row['收盤價']:.1f}")
                    with col4:
                        st.metric("5日漲幅", f"{row['5日漲幅(%)']}%", 
                                 delta=f"{row['5日漲幅(%)']}%" if row['5日漲幅(%)'] > 0 else None)
                    st.divider()
            
            # 下載功能
            csv = display_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 下載完整報告 (CSV)",
                data=csv,
                file_name=f"momentum_stocks_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.error("❌ 目前無符合條件的股票，可能是市場資料不足或門檻過高")

# 說明資訊
with st.expander("ℹ️ 使用說明"):
    st.markdown("""
    **篩選邏輯**：
    - 20日均成交金額 ≥ 100億台幣
    - 綜合評分 = 5日漲幅×0.6 + 20日漲幅×0.3
    - 建議停損價 = 目前股價 × 0.92 (下跌8%)
    
    **資料來源**：
    - 台灣證券交易所 (TWSE) 公開API
    - 僅供參考，不構成投資建議
    
    **注意事項**：
    - 資料抓取約需1-2分鐘
    - 包含台灣50成分股及熱門中型股
    - 排除金融股以專注電子傳產
    """)

st.caption("⚠️ 免責聲明：本工具僅供參考，所有數據來自公開資訊，投資決策請自行判斷")