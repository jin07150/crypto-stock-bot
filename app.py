import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px
import datetime
import os
from dotenv import load_dotenv
from real_estate_loader import get_apt_trade_data, get_district_codes

load_dotenv() # .env 파일 로드

# 1. 페이지 설정은 반드시 스크립트 최상단에 위치해야 합니다.
st.set_page_config(page_title="통합 자산 모니터링 대시보드", layout="wide")

# [NEW] 부동산 데이터 캐싱 함수 (여러 단지 조회를 위해 함수 분리)
@st.cache_data(ttl=3600)
def fetch_apt_trade_data_cached(service_key, lawd_cd, deal_ymd):
    return get_apt_trade_data(service_key, lawd_cd, deal_ymd)

# [NEW] 업비트 마켓 코드 조회 (코인 검색용)
@st.cache_data(ttl=86400) # 하루에 한 번만 호출
def get_upbit_markets():
    try:
        url = "https://api.upbit.com/v1/market/all?isDetails=false"
        response = requests.get(url)
        data = response.json()
        # KRW 마켓만 필터링하고 {표시명: 티커} 딕셔너리 생성
        market_dict = {}
        for item in data:
            if item['market'].startswith("KRW-"):
                market_dict[f"{item['korean_name']} ({item['market']})"] = item['market']
        return market_dict
    except Exception:
        return {}

# [NEW] 관심 단지 목록 초기화 (세션 상태 사용)
if 'favorite_apts' not in st.session_state:
    st.session_state['favorite_apts'] = []

# [NEW] 선택된 자산 상태 관리
if 'selected_asset' not in st.session_state:
    st.session_state['selected_asset'] = None

# [NEW] 팝오버 강제 닫기를 위한 상태 키
if 'popover_refresh_key' not in st.session_state:
    st.session_state['popover_refresh_key'] = 0

# 2. 사이드바 설정 (입력값 받기)
with st.sidebar:
    st.title("⚙️ 설정")
    
    # 1. Crypto 설정
    with st.expander("🪙 코인 설정", expanded=False):
        coin_market_dict = get_upbit_markets()
        
        # 기본 선택값 설정
        default_coins = []
        if coin_market_dict:
            # 딕셔너리 키 중에서 비트코인, 이더리움, 리플을 찾아서 기본값으로 설정
            for key in coin_market_dict.keys():
                if "KRW-BTC" in key or "KRW-ETH" in key or "KRW-XRP" in key:
                    default_coins.append(key)
        
        selected_coins = st.multiselect(
            "코인 선택 (이름 검색 가능)", 
            options=list(coin_market_dict.keys()),
            default=default_coins,
            key="selected_coins_state" # 세션 상태와 연동
        )

    # 2. Stock 설정
    with st.expander("📈 주식 설정", expanded=False):
        # 주요 주식 추천 목록
        STOCK_RECOMMENDATIONS = {
            "삼성전자 (005930.KS)": "005930.KS", "SK하이닉스 (000660.KS)": "000660.KS",
            "현대차 (005380.KS)": "005380.KS", "NAVER (035420.KS)": "035420.KS",
            "카카오 (035720.KS)": "035720.KS",
            "TIGER 미국S&P500 (360750.KS)": "360750.KS",
            "TIGER 미국나스닥100 (133690.KS)": "133690.KS",
            "TIGER 미국필라델피아반도체 (381180.KS)": "381180.KS",
            "애플 (AAPL)": "AAPL",
            "테슬라 (TSLA)": "TSLA", "마이크로소프트 (MSFT)": "MSFT",
            "엔비디아 (NVDA)": "NVDA", "구글 (GOOGL)": "GOOGL", "아마존 (AMZN)": "AMZN"
        }
        
        selected_stocks = st.multiselect(
            "주요 주식 선택",
            options=list(STOCK_RECOMMENDATIONS.keys()),
            default=["삼성전자 (005930.KS)", "애플 (AAPL)", "테슬라 (TSLA)"],
            key="selected_stocks_state" # 세션 상태와 연동
        )
        custom_stock_input = st.text_input("기타 주식 티커 입력 (콤마로 구분)", placeholder="예: 000270.KS, NFLX", key="custom_stock_state")
    
    # 3. 부동산 설정
    with st.expander("🏠 부동산 설정", expanded=False):
        use_real_estate = st.checkbox("부동산 모니터링 활성화", value=True)
        
        if use_real_estate:
            service_key = os.getenv("SERVICE_KEY")
            
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
            # [변경] 선택한 조건을 즐겨찾기에 추가하는 로직으로 변경
            if service_key and target_lawd:
                deal_ymd = target_date.strftime("%Y%m")
                # 캐싱된 함수 사용하여 임시 데이터 로드
                df_temp = fetch_apt_trade_data_cached(service_key, target_lawd, deal_ymd)
                
                if not df_temp.empty:
                    apt_list = sorted(df_temp['아파트'].unique().tolist())
                    selected_apt = st.selectbox("아파트 단지 선택", apt_list)
                    
                    if st.button("관심 단지 추가 ➕"):
                        item = {
                            "lawd_cd": target_lawd,
                            "region_name": f"{selected_sido} {selected_sigungu}",
                            "apt_name": selected_apt,
                            "deal_ymd": deal_ymd
                        }
                        if item not in st.session_state['favorite_apts']:
                            st.session_state['favorite_apts'].append(item)
                            st.success(f"'{selected_apt}' 추가됨")
                        else:
                            st.warning("이미 목록에 있습니다.")
                else:
                    st.warning("해당 조건의 데이터가 없습니다.")

            # [NEW] 관심 목록 표시 및 삭제 기능
            if st.session_state['favorite_apts']:
                st.markdown("---")
                st.caption("📋 관심 단지 목록")
                for i, item in enumerate(st.session_state['favorite_apts']):
                    col1, col2 = st.columns([0.85, 0.15])
                    col1.text(f"{item['apt_name']}\n({item['region_name']})")
                    if col2.button("🗑️", key=f"del_{i}"):
                        st.session_state['favorite_apts'].pop(i)
                        st.rerun()

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
        # 통화 정보 가져오기 (기본값 KRW)
        currency = stock.fast_info.get('currency', 'KRW')
        
        hist = stock.history(period="2d")
        if len(hist) >= 2:
            price = hist['Close'].iloc[-1]
            prev_close = hist['Close'].iloc[-2]
            change = ((price - prev_close) / prev_close) * 100
            return price, change, currency
        else:
            return hist['Close'].iloc[-1], 0, currency
    except Exception:
        return 0, 0, "KRW"

# 5. 메인 대시보드 UI 구성
st.title("📊 통합 자산 모니터링 대시보드")

st.subheader("📍 실시간 요약")

# 표시할 모든 메트릭 데이터를 수집
metrics_data = []

# 1. 코인 데이터 수집
for name in selected_coins:
    ticker = coin_market_dict.get(name)
    if ticker:
        price, change = get_crypto_price(ticker)
        metrics_data.append({
            "label": f"🪙 {name}",
            "value": f"{price:,.0f} KRW",
            "delta": f"{change:.2f}%",
            "type": "coin",
            "id": name
        })

# 2. 주식 데이터 수집
for name in selected_stocks:
    ticker = STOCK_RECOMMENDATIONS.get(name)
    if ticker:
        price, change, currency = get_stock_price(ticker)
        
        # 통화에 따른 포맷팅
        if currency == "USD":
            value_fmt = f"${price:,.2f}"
        elif currency == "KRW":
            value_fmt = f"{price:,.0f} KRW"
        else:
            value_fmt = f"{price:,.2f} {currency}"
            
        metrics_data.append({
            "label": f"📈 {name}",
            "value": value_fmt,
            "delta": f"{change:.2f}%",
            "type": "stock_rec",
            "id": name
        })

if custom_stock_input:
    custom_tickers = [t.strip() for t in custom_stock_input.split(',') if t.strip()]
    for ticker in custom_tickers:
        price, change, currency = get_stock_price(ticker)
        
        # 통화에 따른 포맷팅
        if currency == "USD":
            value_fmt = f"${price:,.2f}"
        elif currency == "KRW":
            value_fmt = f"{price:,.0f} KRW"
        else:
            value_fmt = f"{price:,.2f} {currency}"
            
        metrics_data.append({
            "label": f"📈 {ticker}",
            "value": value_fmt,
            "delta": f"{change:.2f}%",
            "type": "stock_custom",
            "id": ticker
        })

# 3. 부동산 데이터 수집
df_display = pd.DataFrame() # 상세 데이터 탭을 위한 통합 데이터프레임

if use_real_estate:
    service_key = os.getenv("SERVICE_KEY")
    if st.session_state['favorite_apts']:
        for idx, item in enumerate(st.session_state['favorite_apts']):
            # 각 관심 단지별 데이터 로드
            df = fetch_apt_trade_data_cached(service_key, item['lawd_cd'], item['deal_ymd'])
            
            if not df.empty:
                # 해당 아파트만 필터링
                apt_df = df[df['아파트'] == item['apt_name']]
                if not apt_df.empty:
                    # 상세 데이터 병합
                    df_display = pd.concat([df_display, apt_df], ignore_index=True)
                    
                    # 메트릭(요약) 추가
                    recent = apt_df.iloc[0] # 최신 거래
                    metrics_data.append({
                        "label": f"🏠 {item['apt_name']}",
                        "value": f"{recent['거래금액']:,} 만원",
                        "delta": f"{recent['층']}층 ({recent['전용면적']}㎡)",
                        "type": "real_estate",
                        "id": idx
                    })
                else:
                    metrics_data.append({"label": f"🏠 {item['apt_name']}", "value": "거래 없음", "delta": "-", "type": "real_estate", "id": idx})
            else:
                metrics_data.append({"label": f"🏠 {item['apt_name']}", "value": "데이터 없음", "delta": "API 확인", "type": "real_estate", "id": idx})
    else:
        metrics_data.append({
            "label": "🏠 부동산",
            "value": "관심 단지 없음",
            "delta": "설정에서 추가",
            "type": "info",
            "id": None
        })

# 동적 그리드 레이아웃 (3열)
if metrics_data:
    cols = st.columns(3)
    for i, metric in enumerate(metrics_data):
        with cols[i % 3]:
            # 정보성 메시지인 경우 (삭제/차트 기능 없음)
            if metric.get("type") == "info":
                with st.container(border=True):
                    st.metric(label=metric["label"], value=metric["value"], delta=metric["delta"])
            else:
                # 상호작용 가능한 아이템: 버튼으로 변경 (클릭 시 차트 자동 선택)
                # 버튼 라벨에 주요 정보 표시 (줄바꿈으로 구분)
                btn_label = f"{metric['label']}\n{metric['value']}"
                
                if st.button(btn_label, key=f"btn_{i}", use_container_width=True):
                    st.session_state['selected_asset'] = metric
                    st.rerun()
else:
    st.info("👈 사이드바에서 모니터링할 자산을 설정해주세요.")

st.divider()

# 상세 분석 탭
tab1, tab2, tab3 = st.tabs(["📊 차트 분석", "📋 상세 데이터", "🤖 AI 리포트"])

with tab1:
    st.subheader("자산 가격 변동 추이")
    target = st.session_state.get('selected_asset')
    
    if target:
        # 헤더, 기간 선택기, 삭제 버튼을 나란히 배치
        col_title, col_period, col_del = st.columns([0.3, 0.5, 0.2])
        with col_title:
            st.markdown(f"### {target['label']}")
        with col_period:
            period = st.radio(
                "조회 기간", 
                ["1주일", "1개월", "3개월", "1년", "5년", "10년", "전체"], 
                index=1, 
                horizontal=True,
                label_visibility="collapsed"
            )
        with col_del:
            # 현재 선택된 자산 삭제 버튼
            if st.button("대시보드에서 삭제", key="del_current_asset", type="primary"):
                metric = target
                if metric["type"] == "coin":
                    if metric["id"] in st.session_state['selected_coins_state']:
                        st.session_state['selected_coins_state'].remove(metric["id"])
                elif metric["type"] == "stock_rec":
                    if metric["id"] in st.session_state['selected_stocks_state']:
                        st.session_state['selected_stocks_state'].remove(metric["id"])
                elif metric["type"] == "stock_custom":
                    current_input = st.session_state['custom_stock_state']
                    tickers = [t.strip() for t in current_input.split(',') if t.strip()]
                    if metric["id"] in tickers:
                        tickers.remove(metric["id"])
                    st.session_state['custom_stock_state'] = ", ".join(tickers)
                elif metric["type"] == "real_estate":
                    # 인덱스 유효성 확인 후 삭제
                    if 0 <= metric["id"] < len(st.session_state['favorite_apts']):
                        st.session_state['favorite_apts'].pop(metric["id"])
                
                st.session_state['selected_asset'] = None
                st.rerun()
        
        # 1. 코인 차트 (업비트)
        if target['type'] == 'coin':
            coin_market_dict = get_upbit_markets()
            ticker = coin_market_dict.get(target['id'])
            if ticker:
                try:
                    # 기간별 API 호출 설정
                    if period == "1주일":
                        url = f"https://api.upbit.com/v1/candles/days?market={ticker}&count=7"
                    elif period == "1개월":
                        url = f"https://api.upbit.com/v1/candles/days?market={ticker}&count=30"
                    elif period == "3개월":
                        url = f"https://api.upbit.com/v1/candles/days?market={ticker}&count=90"
                    elif period == "1년":
                        url = f"https://api.upbit.com/v1/candles/weeks?market={ticker}&count=52"
                    elif period == "5년":
                        url = f"https://api.upbit.com/v1/candles/months?market={ticker}&count=60"
                    elif period == "10년":
                        url = f"https://api.upbit.com/v1/candles/months?market={ticker}&count=120"
                    else: # 전체
                        url = f"https://api.upbit.com/v1/candles/months?market={ticker}&count=200"

                    df = pd.DataFrame(requests.get(url).json())
                    df['trade_price'] = df['trade_price'].astype(float)
                    df['date'] = pd.to_datetime(df['candle_date_time_kst'])
                    
                    fig = px.line(df, x='date', y='trade_price', title=f"{target['label']} 가격 추이")
                    fig.update_layout(hovermode="x unified") # 마우스 오버 시 정보 표시
                    st.plotly_chart(fig, use_container_width=True)
                except:
                    st.error("차트 데이터를 불러올 수 없습니다.")
        
        # 2. 주식 차트 (Yahoo Finance)
        elif target['type'] in ['stock_rec', 'stock_custom']:
            ticker = target['id']
            if target['type'] == 'stock_rec':
                ticker = STOCK_RECOMMENDATIONS.get(target['id'])
            
            if ticker:
                try:
                    # 기간별 파라미터 매핑
                    yf_period = "1mo"
                    if period == "1주일": yf_period = "5d"
                    elif period == "1개월": yf_period = "1mo"
                    elif period == "3개월": yf_period = "3mo"
                    elif period == "1년": yf_period = "1y"
                    elif period == "5년": yf_period = "5y"
                    elif period == "10년": yf_period = "10y"
                    else: yf_period = "max"

                    df = yf.Ticker(ticker).history(period=yf_period)
                    
                    # 인덱스(Date)를 컬럼으로 변환하여 Plotly에 사용
                    df = df.reset_index()
                    fig = px.line(df, x='Date', y='Close', title=f"{target['label']} 주가 추이")
                    fig.update_layout(hovermode="x unified")
                    st.plotly_chart(fig, use_container_width=True)
                except:
                    st.error("차트 데이터를 불러올 수 없습니다.")

        # 3. 부동산 차트 (최근 거래 내역)
        elif target['type'] == 'real_estate':
            if period != "1개월":
                st.caption("ℹ️ 부동산 데이터는 설정된 '조회 기준일'의 월간 데이터만 표시됩니다.")
                
            if use_real_estate and not df_display.empty:
                # 현재 로드된 데이터 중 해당 아파트 데이터만 필터링
                # (참고: API 구조상 과거 전체 내역을 가져오려면 추가 호출이 필요하지만, 여기선 현재 로드된 데이터로 시각화)
                apt_name = st.session_state['favorite_apts'][target['id']]['apt_name']
                chart_data = df_display[df_display['아파트'] == apt_name].copy()
                if not chart_data.empty:
                    chart_data['계약일_full'] = chart_data['계약일'].astype(str) # 간단한 시각화를 위해 문자열로 처리
                    
                    fig = px.bar(chart_data, x='계약일_full', y='거래금액', title=f"{target['label']} 거래 내역")
                    fig.update_layout(hovermode="x unified")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("표시할 거래 내역이 없습니다.")
    else:
        st.info("👆 대시보드 카드의 메뉴(⋮)에서 '차트 보기'를 선택하면 상세 그래프가 표시됩니다.")
    
with tab2:
    st.subheader("상세 정보 및 뉴스")
    target = st.session_state.get('selected_asset')
    
    if target:
        st.markdown(f"### {target['label']}")
        
        # 1. 주식 뉴스
        if target['type'] in ['stock_rec', 'stock_custom']:
            ticker = target['id']
            # 주식 추천 딕셔너리 (참조용)
            STOCK_RECOMMENDATIONS = {
                "삼성전자 (005930.KS)": "005930.KS", "SK하이닉스 (000660.KS)": "000660.KS",
                "현대차 (005380.KS)": "005380.KS", "NAVER (035420.KS)": "035420.KS",
                "카카오 (035720.KS)": "035720.KS",
                "TIGER 미국S&P500 (360750.KS)": "360750.KS",
                "TIGER 미국나스닥100 (133690.KS)": "133690.KS",
                "TIGER 미국필라델피아반도체 (381180.KS)": "381180.KS",
                "애플 (AAPL)": "AAPL",
                "테슬라 (TSLA)": "TSLA", "마이크로소프트 (MSFT)": "MSFT",
                "엔비디아 (NVDA)": "NVDA", "구글 (GOOGL)": "GOOGL", "아마존 (AMZN)": "AMZN"
            }
            
            if target['type'] == 'stock_rec':
                ticker = STOCK_RECOMMENDATIONS.get(target['id'], target['id'])
            
            try:
                st.caption(f"Ticker: {ticker} 관련 최신 뉴스 (Yahoo Finance)")
                stock = yf.Ticker(ticker)
                news = stock.news
                if news:
                    for item in news:
                        with st.container(border=True):
                            link = item.get('link')
                            title = item.get('title')
                            publisher = item.get('publisher')
                            pub_time = item.get('providerPublishTime')
                            
                            st.markdown(f"**[{title}]({link})**")
                            if pub_time:
                                date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M')
                                st.caption(f"{publisher} | {date_str}")
                            else:
                                st.caption(f"{publisher}")
                else:
                    st.info("최근 뉴스가 없습니다.")
            except Exception:
                st.error("뉴스 데이터를 불러오는 중 오류가 발생했습니다.")

        # 2. 코인 뉴스
        elif target['type'] == 'coin':
            coin_market_dict = get_upbit_markets()
            upbit_ticker = coin_market_dict.get(target['id'])
            
            if upbit_ticker:
                # KRW-BTC -> BTC-USD 변환 시도 (Yahoo Finance 뉴스용)
                yf_ticker = upbit_ticker.replace("KRW-", "") + "-USD"
                st.caption(f"Ticker: {yf_ticker} 관련 최신 뉴스 (Yahoo Finance)")
                
                try:
                    coin = yf.Ticker(yf_ticker)
                    news = coin.news
                    if news:
                        for item in news:
                            with st.container(border=True):
                                link = item.get('link')
                                title = item.get('title')
                                publisher = item.get('publisher')
                                pub_time = item.get('providerPublishTime')
                                
                                st.markdown(f"**[{title}]({link})**")
                                if pub_time:
                                    date_str = datetime.datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M')
                                    st.caption(f"{publisher} | {date_str}")
                                else:
                                    st.caption(f"{publisher}")
                    else:
                        st.info("최근 뉴스가 없습니다.")
                except:
                    pass
            
            # 네이버 검색 링크 추가
            query = target['label'].split('(')[0].replace("🪙", "").strip()
            st.markdown(f"🔗 [네이버 뉴스 검색: {query}](https://search.naver.com/search.naver?where=news&query={query})")

        # 3. 부동산 상세
        elif target['type'] == 'real_estate':
            if use_real_estate and not df_display.empty:
                if 0 <= target['id'] < len(st.session_state['favorite_apts']):
                    apt_info = st.session_state['favorite_apts'][target['id']]
                    apt_name = apt_info['apt_name']
                    
                    st.write(f"**{apt_name} 실거래 내역**")
                    # 해당 아파트 데이터 필터링
                    apt_df = df_display[df_display['아파트'] == apt_name]
                    st.dataframe(apt_df, use_container_width=True)
                    
                    st.divider()
                    st.subheader("관련 정보")
                    query = f"{apt_info['region_name']} {apt_name}"
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"🏢 [네이버 부동산 단지정보](https://land.naver.com/search/search.naver?query={query})")
                    with col2:
                        st.markdown(f"📰 [관련 뉴스 검색](https://search.naver.com/search.naver?where=news&query={query})")
                else:
                    st.warning("선택된 부동산 정보를 찾을 수 없습니다.")
            else:
                st.info("부동산 데이터가 없습니다.")
                
    else:
        st.info("👆 대시보드에서 항목을 선택하면 상세 정보와 뉴스를 확인할 수 있습니다.")

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
    
    /* 삭제 버튼 스타일: 투명하고 작게 */
    div[data-testid="stVerticalBlockBorderWrapper"] button {
        border: none !important;
        background: transparent !important;
        color: #cccccc !important;
        padding: 0 !important;
        font-size: 0.8rem !important;
        line-height: 1 !important;
        min-height: 0 !important;
        margin-top: 0px !important;
    }
    
    div[data-testid="stVerticalBlockBorderWrapper"] button:hover {
        color: #ff4b4b !important;
        background: rgba(255, 75, 75, 0.1) !important;
        border-radius: 50% !important;
    }

    /* 삭제 버튼이 있는 오른쪽 컬럼 정렬 */
    div[data-testid="stVerticalBlockBorderWrapper"] [data-testid="column"]:nth-of-type(2) {
        display: flex;
        justify-content: flex-end;
        align-items: flex-start;
    }
    
    /* Primary 버튼(삭제) 스타일: 작게 설정 */
    button[kind="primary"] {
        padding: 0.2rem 0.5rem !important;
        font-size: 0.8rem !important;
        min-height: 0px !important;
        height: auto !important;
    }
    </style>
    """, unsafe_allow_html=True)