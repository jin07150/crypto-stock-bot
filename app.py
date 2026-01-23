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
    st.subheader("관심 자산 설정")
    target_coin = st.text_input("코인 티커", value="KRW-BTC")
    target_stock = st.text_input("주식 티커", value="005930.KS")
    
    st.subheader("부동산 설정")
    # 실제 사용 시 API 키 입력 필요
    env_key = os.getenv("SERVICE_KEY", "")
    service_key = st.text_input("공공데이터포털 인증키", value=env_key, type="password", help="Decoding된 인증키를 입력하세요 (.env에 SERVICE_KEY로 설정 가능)")
    
    # 지역 코드 데이터 로드 (캐싱 적용)
    @st.cache_data
    def load_district_codes():
        return get_district_codes()

    df_districts = load_district_codes()

    if not df_districts.empty:
        # 1. 시/도 선택
        sido_list = df_districts['시도'].unique().tolist()
        selected_sido = st.selectbox("시/도", sido_list, index=sido_list.index("서울특별시") if "서울특별시" in sido_list else 0)
        
        # 2. 시/군/구 선택 (선택된 시/도에 해당하는 목록만 필터링)
        sigungu_list = df_districts[df_districts['시도'] == selected_sido]['시군구'].unique().tolist()
        selected_sigungu = st.selectbox("시/군/구", sigungu_list)
        
        # 선택된 지역의 코드(5자리) 추출
        target_lawd = df_districts[(df_districts['시도'] == selected_sido) & (df_districts['시군구'] == selected_sigungu)]['lawd_cd'].iloc[0]
    else:
        target_lawd = st.text_input("부동산 지역 코드", value="11680") # 데이터 로드 실패 시 수동 입력

    target_date = st.date_input("조회 기준일", datetime.date(2024, 1, 1))
    
    st.divider()
    if st.button("데이터 새로고침"):
        st.rerun()

# 3. 데이터 로딩 함수 (캐싱 적용으로 성능 최적화)
@st.cache_data(ttl=60) # 60초 동안 데이터 캐시 유지
def fetch_market_data(coin_ticker, stock_ticker):
    # 코인 데이터 (Upbit)
    try:
        coin_url = f"https://api.upbit.com/v1/ticker?markets={coin_ticker}"
        coin_resp = requests.get(coin_url).json()
        coin_price = coin_resp[0]['trade_price']
        coin_change = coin_resp[0]['signed_change_rate'] * 100 # 백분율 변환
    except Exception:
        coin_price, coin_change = 0, 0

    # 주식 데이터 (Yahoo Finance)
    try:
        stock = yf.Ticker(stock_ticker)
        hist = stock.history(period="2d") # 전일 대비 등락률 계산을 위해 2일치 조회
        if len(hist) >= 2:
            stock_price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            stock_change = ((stock_price - prev_close) / prev_close) * 100
        else:
            stock_price = hist['Close'].iloc[-1]
            stock_change = 0
    except Exception:
        stock_price, stock_change = 0, 0
        
    return coin_price, coin_change, stock_price, stock_change

# 4. 실제 데이터 가져오기
btc_price, btc_change, stock_price, stock_change = fetch_market_data(target_coin, target_stock)

# 부동산 데이터 로딩
df_real_estate = pd.DataFrame()
if service_key:
    deal_ymd = target_date.strftime("%Y%m")
    df_real_estate = get_apt_trade_data(service_key, target_lawd, deal_ymd)

# 아파트 선택 필터링 (데이터가 있을 경우 사이드바에 추가)
df_display = df_real_estate
if not df_real_estate.empty:
    with st.sidebar:
        apt_list = ["전체"] + sorted(df_real_estate['아파트'].unique().tolist())
        selected_apt = st.selectbox("아파트 단지 선택", apt_list)
        if selected_apt != "전체":
            df_display = df_real_estate[df_real_estate['아파트'] == selected_apt]

# 5. 메인 대시보드 UI 구성
st.title("📊 통합 자산 모니터링 대시보드")

st.subheader("📍 실시간 요약")
m1, m2, m3 = st.columns(3)

# Metric 표시 (실제 데이터 연동)
m1.metric(label=f"{target_coin}", value=f"{btc_price:,.0f} KRW", delta=f"{btc_change:.2f}%")
m2.metric(label=f"{target_stock}", value=f"{stock_price:,.0f} KRW", delta=f"{stock_change:.2f}%")

if not df_display.empty:
    recent_apt = df_display.iloc[0]
    # 거래금액은 만원 단위이므로 10000을 곱해 원 단위로 표시하거나 '만원' 텍스트 유지
    m3.metric(label=f"부동산 ({recent_apt['아파트']})", value=f"{recent_apt['거래금액']:,} 만원", delta="최근 실거래")
else:
    m3.metric(label="부동산 데이터", value="데이터 없음", delta="설정 확인 필요")

st.divider()

# 상세 분석 탭
tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "📋 상세 데이터", "🤖 AI 리포트"])

with tab1:
    st.subheader("자산 가격 변동 추이")
    col_chart1, col_chart2 = st.columns(2)
    with col_chart1:
        st.info(f"{target_coin} 차트 (준비중)")
    with col_chart2:
        st.info(f"{target_stock} 차트 (준비중)")
    
with tab2:
    st.subheader("부동산 실거래 내역")
    if not df_display.empty:
        st.dataframe(df_display, use_container_width=True)
    else:
        st.warning("조회된 부동산 데이터가 없습니다. 사이드바에서 API 키와 지역코드를 확인해주세요.")

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