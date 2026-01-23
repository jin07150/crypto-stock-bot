import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import datetime
import os
from dotenv import load_dotenv
from real_estate_loader import get_apt_trade_data, get_district_codes

load_dotenv() # .env 파일 로드

# 1. 페이지 설정은 반드시 스크립트 최상단에 위치해야 합니다.
st.set_page_config(page_title="통합 자산 모니터링 대시보드", layout="wide")

# 2. 사이드바 설정 (입력값 받기)
with st.sidebar:
    st.title("⚙️ 설정")
    
    # 모듈 선택 (원하는 자산 유형만 활성화)
    active_modules = st.multiselect(
        "모니터링 항목 선택",
        ["Crypto", "Stock", "Real Estate"],
        default=["Crypto", "Stock", "Real Estate"]
    )
    st.divider()

    # 1. Crypto 설정
    coin_tickers = []
    if "Crypto" in active_modules:
        st.subheader("🪙 코인 설정")
        input_coins = st.text_input("코인 티커 (콤마로 구분)", value="KRW-BTC, KRW-ETH, KRW-XRP")
        coin_tickers = [t.strip() for t in input_coins.split(',') if t.strip()]

    # 2. Stock 설정
    stock_tickers = []
    if "Stock" in active_modules:
        st.subheader("📈 주식 설정")
        input_stocks = st.text_input("주식 티커 (콤마로 구분)", value="005930.KS, AAPL, TSLA")
        stock_tickers = [t.strip() for t in input_stocks.split(',') if t.strip()]
    
    # 3. 부동산 설정
    df_real_estate = pd.DataFrame()
    df_display = pd.DataFrame()
    
    if "Real Estate" in active_modules:
        st.subheader("🏠 부동산 설정")
        env_key = os.getenv("SERVICE_KEY", "")
        service_key = st.text_input("공공데이터포털 인증키", value=env_key, type="password", help="Decoding된 인증키를 입력하세요")
        
        # 지역 코드 데이터 로드
        @st.cache_data
        def load_district_codes():
            return get_district_codes()

        df_districts = load_district_codes()

        if not df_districts.empty:
            sido_list = df_districts['시도'].unique().tolist()
            selected_sido = st.selectbox("시/도", sido_list, index=sido_list.index("서울특별시") if "서울특별시" in sido_list else 0)
            
            sigungu_list = df_districts[df_districts['시도'] == selected_sido]['시군구'].unique().tolist()
            selected_sigungu = st.selectbox("시/군/구", sigungu_list)
            
            target_lawd = df_districts[(df_districts['시도'] == selected_sido) & (df_districts['시군구'] == selected_sigungu)]['lawd_cd'].iloc[0]
        else:
            target_lawd = st.text_input("부동산 지역 코드", value="11680")

        target_date = st.date_input("조회 기준일", datetime.date(2024, 1, 1))
        
        # 부동산 데이터 로딩 (설정값이 다 있을 때만)
        if service_key and target_lawd:
            deal_ymd = target_date.strftime("%Y%m")
            df_real_estate = get_apt_trade_data(service_key, target_lawd, deal_ymd)
            
            # 아파트 필터링 UI
            if not df_real_estate.empty:
                apt_list = ["전체"] + sorted(df_real_estate['아파트'].unique().tolist())
                selected_apt = st.selectbox("아파트 단지 선택", apt_list)
                if selected_apt != "전체":
                    df_display = df_real_estate[df_real_estate['아파트'] == selected_apt]
                else:
                    df_display = df_real_estate
    
    st.divider()
    if st.button("데이터 새로고침"):
        st.rerun()

# 3. 데이터 로딩 함수 분리 (개별 자산별 처리)
@st.cache_data(ttl=60) # 60초 동안 데이터 캐시 유지
def get_crypto_price(ticker):
    try:
        coin_url = f"https://api.upbit.com/v1/ticker?markets={ticker}"
        coin_resp = requests.get(coin_url).json()
        price = coin_resp[0]['trade_price']
        change = coin_resp[0]['signed_change_rate'] * 100
        return price, change
    except Exception:
        return 0, 0

@st.cache_data(ttl=60)
def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) >= 2:
            price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            return price, change
        else:
            return hist['Close'].iloc[-1], 0
    except Exception:
        return 0, 0

# 5. 메인 대시보드 UI 구성
st.title("📊 통합 자산 모니터링 대시보드")

st.subheader("📍 실시간 요약")

# 표시할 모든 메트릭 데이터를 수집
metrics_data = []

# 1. 코인 데이터 수집
for ticker in coin_tickers:
    price, change = get_crypto_price(ticker)
    metrics_data.append({
        "label": f"🪙 {ticker}",
        "value": f"{price:,.0f} KRW",
        "delta": f"{change:.2f}%"
    })

# 2. 주식 데이터 수집
for ticker in stock_tickers:
    price, change = get_stock_price(ticker)
    metrics_data.append({
        "label": f"📈 {ticker}",
        "value": f"{price:,.0f} KRW",
        "delta": f"{change:.2f}%"
    })

# 3. 부동산 데이터 수집
if "Real Estate" in active_modules:
    if not df_display.empty:
        recent_apt = df_display.iloc[0]
        metrics_data.append({
            "label": f"🏠 {recent_apt['아파트']}",
            "value": f"{recent_apt['거래금액']:,} 만원",
            "delta": "최근 실거래"
        })
    else:
        metrics_data.append({
            "label": "🏠 부동산",
            "value": "데이터 없음",
            "delta": "설정 확인"
        })

# 동적 그리드 레이아웃 (3열)
if metrics_data:
    cols = st.columns(3)
    for i, metric in enumerate(metrics_data):
        with cols[i % 3]:
            st.metric(label=metric["label"], value=metric["value"], delta=metric["delta"])
else:
    st.info("👈 사이드바에서 모니터링할 자산을 설정해주세요.")

st.divider()

# 상세 분석 탭
tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "📋 상세 데이터", "🤖 AI 리포트"])

with tab1:
    st.subheader("자산 가격 변동 추이")
    if not metrics_data:
        st.info("데이터가 없습니다.")
    else:
        st.info("차트 기능은 현재 준비 중입니다. (Plotly 연동 예정)")
    
with tab2:
    st.subheader("부동산 실거래 내역")
    if "Real Estate" in active_modules and not df_display.empty:
        st.dataframe(df_display, use_container_width=True)
    elif "Real Estate" in active_modules:
        st.warning("조회된 부동산 데이터가 없습니다. 사이드바에서 API 키와 지역코드를 확인해주세요.")
    else:
        st.info("부동산 모듈이 비활성화되어 있습니다.")

with tab3:
    st.subheader("💡 Gemini의 투자 조언")
    st.write("여기에 Gemini API를 연결하면 현재 가격 정보를 바탕으로 분석 리포트를 생성할 수 있습니다.")

# 스타일링
st.markdown("""
    <style>
    .stMetric {
        background-color: #f0f2f6;
        padding: 15px;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)