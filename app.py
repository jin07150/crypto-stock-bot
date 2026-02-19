import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.express as px
import datetime
import os
import numpy as np
import plotly.graph_objects as go
import time
import uuid
import urllib.parse

# [REFACTOR] 모듈 임포트
import utils
import data_manager
import ai_manager

from dotenv import load_dotenv
from real_estate_loader import get_apt_trade_data, get_district_codes

try:
    from streamlit_sortables import sort_items
except ImportError:
    sort_items = None

load_dotenv() # .env 파일 로드

# 앱 버전 정보
__version__ = "1.3.6"   

# 1. 페이지 설정은 반드시 스크립트 최상단에 위치해야 합니다.
st.set_page_config(page_title=f"통합 자산 모니터링 v{__version__}", page_icon="💰", layout="wide")

# [NEW] 앱 시작 시 설정 불러오기
if 'init_done' not in st.session_state:
    config = utils.load_config()
    if config:
        st.session_state['favorite_apts'] = config.get('favorite_apts', [])
        st.session_state['dashboard_order'] = config.get('dashboard_order', [])
        # 위젯 키에 해당하는 세션 상태를 미리 초기화하여 기본값으로 설정
        if 'selected_coins' in config: st.session_state['selected_coins_state'] = config['selected_coins']
        if 'selected_stocks' in config: st.session_state['selected_stocks_state'] = config['selected_stocks']
        if 'custom_stock' in config: st.session_state['custom_stock_state'] = config['custom_stock']
        if 'selected_ai_model' in config: st.session_state['selected_ai_model'] = config['selected_ai_model']
    
    # [FIX] 세션 상태 초기화 (Config에 없거나 로드 실패 시 기본값 설정)
    if 'selected_stocks_state' not in st.session_state:
        st.session_state['selected_stocks_state'] = ["삼성전자 (005930.KS)", "TIGER 미국S&P500 (360750.KS)", "TIGER 미국나스닥100 (133690.KS)", "TIGER 미국필라델피아반도체 (381180.KS)"]
    if 'custom_stock_state' not in st.session_state:
        st.session_state['custom_stock_state'] = ""
    
    # [NEW] 부동산 관심 단지 기본값 설정 (최초 실행 시 예시 데이터 제공)
    if 'favorite_apts' not in st.session_state:
        st.session_state['favorite_apts'] = [
            {
                "id": str(uuid.uuid4()),
                "lawd_cd": "11680", # 서울 강남구
                "region_name": "서울특별시 강남구",
                "apt_name": "은마"
            }
        ]
        
    st.session_state['init_done'] = True

if not utils.check_password():
    st.stop()

# [NEW] 관심 단지 목록 초기화 (세션 상태 사용)
if 'favorite_apts' not in st.session_state:
    st.session_state['favorite_apts'] = []

# [NEW] 선택된 자산 상태 관리
if 'selected_asset' not in st.session_state:
    st.session_state['selected_asset'] = None

# [NEW] 대시보드 아이템 순서 관리
if 'dashboard_order' not in st.session_state:
    st.session_state['dashboard_order'] = []

# [NEW] 선택적 캐시 삭제를 위한 타임스탬프
if 'cache_invalidation_ts' not in st.session_state:
    st.session_state['cache_invalidation_ts'] = {}

# [NEW] 아파트 목록 조회 데이터 캐시 (UI용)
if 'fetched_apt_data' not in st.session_state:
    st.session_state['fetched_apt_data'] = {}

# 2. 사이드바 설정 (입력값 받기)
with st.sidebar:
    st.markdown(f"""
        <div style="display: flex; justify-content: space-between; align-items: baseline;">
            <h1 style="margin: 0;">⚙️ 설정</h1>
            <span style="font-size: 0.8rem; color: grey;">v{__version__}</span>
        </div>
    """, unsafe_allow_html=True)
    
    # 1. Stock 설정
    with st.expander("📈 주식 설정", expanded=False):
        selected_stocks = st.multiselect(
            "주요 주식 선택",
            options=list(utils.STOCK_RECOMMENDATIONS.keys()),
            key="selected_stocks_state", # 세션 상태와 연동
            on_change=utils.save_config # 변경 시 저장
        )
        custom_stock_input = st.text_input("기타 주식 티커 입력 (콤마로 구분)", placeholder="예: 000270.KS, NFLX", key="custom_stock_state", on_change=utils.save_config)
    
    # 2. 부동산 설정
    with st.expander("🏠 부동산 설정", expanded=False):
        use_real_estate = st.checkbox("부동산 모니터링 활성화", value=True)
        
        if use_real_estate:
            # 환경 변수에서 키를 가져오거나, 없으면 입력창 표시
            env_key = os.getenv("DATA_GO_KR_API_KEY")
            if not env_key:
                service_key = st.text_input("공공데이터포털 인증키 (Decoding)", type="password", help=".env 파일에 DATA_GO_KR_API_KEY가 없습니다.", key="input_service_key")
            else:
                service_key = env_key
            
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

            # 부동산 데이터 로딩 (설정값이 다 있을 때만)
            # [변경] 선택한 조건을 즐겨찾기에 추가하는 로직으로 변경
            if service_key and target_lawd:
                # [NEW] 지역 변경 감지 및 검색 기준일 관리
                if 'last_lawd_cd' not in st.session_state:
                    st.session_state['last_lawd_cd'] = target_lawd
                    st.session_state['apt_search_date'] = datetime.date.today()
                
                if st.session_state['last_lawd_cd'] != target_lawd:
                    st.session_state['last_lawd_cd'] = target_lawd
                    st.session_state['apt_search_date'] = datetime.date.today()

                # 현재 검색 기준 년월 설정 (갱신 시마다 과거로 이동)
                current_search_dt = st.session_state['apt_search_date']
                deal_ymd = current_search_dt.strftime("%Y%m")
                cache_key = f"{target_lawd}_{deal_ymd}"
                
                # 1. 파일에 저장된 아파트 목록 불러오기 (API 호출 없이 즉시 로드)
                saved_apt_list = utils.get_apt_list(target_lawd)
                
                # 2. 세션에 저장된 거래 데이터 확인
                df_current = st.session_state['fetched_apt_data'].get(cache_key)
                
                col_list_info, col_refresh = st.columns([0.7, 0.3])
                trigger_fetch = False
                
                with col_list_info:
                    if saved_apt_list:
                        st.caption(f"✅ 저장된 목록: {len(saved_apt_list)}개")
                    else:
                        st.caption("ℹ️ 저장된 목록 없음")
                    # [NEW] 현재 조회 대상 월 표시
                    st.caption(f"📅 조회 대상: {current_search_dt.strftime('%Y.%m')}")
                
                with col_refresh:
                    # 목록이 있으면 '갱신', 없으면 '조회'
                    btn_label = "목록 갱신 🔄"
                    if st.button(btn_label, key="btn_refresh_apt", help=f"{current_search_dt.strftime('%Y년 %m월')} 데이터를 조회하여 목록에 추가합니다."):
                        st.session_state.setdefault('cache_invalidation_ts', {})[target_lawd] = time.time()
                        trigger_fetch = True
                
                if trigger_fetch:
                    ts = st.session_state.get('cache_invalidation_ts', {}).get(target_lawd, 0)
                    with st.spinner(f"{current_search_dt.strftime('%Y년 %m월')} 거래 데이터 조회 중..."):
                        df_temp = data_manager.fetch_apt_trade_data_cached(service_key, target_lawd, deal_ymd, _cache_ts=ts)
                        st.session_state['fetched_apt_data'][cache_key] = df_temp
                        df_current = df_temp
                        
                        # [NEW] 조회된 데이터에서 아파트 이름을 추출하여 파일에 저장/업데이트
                        if not df_temp.empty:
                            new_apts = df_temp['아파트'].unique().tolist()
                            saved_apt_list = utils.update_apt_list(target_lawd, new_apts)
                            st.toast(f"목록 업데이트 완료! ({len(new_apts)}개 단지 발견)", icon="✅")
                        else:
                            st.toast(f"{current_search_dt.strftime('%Y년 %m월')} 거래 내역이 없습니다.", icon="ℹ️")
                        
                        # [NEW] 다음 조회를 위해 한 달 전으로 이동
                        prev_month = current_search_dt.replace(day=1) - datetime.timedelta(days=1)
                        st.session_state['apt_search_date'] = prev_month
                
                # 아파트 선택 창 (저장된 목록 사용)
                selected_apt = st.selectbox(
                    "아파트 단지 선택", 
                    saved_apt_list, 
                    index=None, 
                    placeholder="아파트 이름을 검색하세요" if saved_apt_list else "목록 조회를 눌러주세요",
                    disabled=not saved_apt_list
                )
                
                if selected_apt:
                    # 선택된 아파트의 상세 정보를 보여주기 위해 데이터 로드 (메모리에 없을 경우)
                    if df_current is None:
                        with st.spinner("상세 데이터 불러오는 중..."):
                            ts = st.session_state.get('cache_invalidation_ts', {}).get(target_lawd, 0)
                            df_temp = data_manager.fetch_apt_trade_data_cached(service_key, target_lawd, deal_ymd, _cache_ts=ts)
                            st.session_state['fetched_apt_data'][cache_key] = df_temp
                            df_current = df_temp
                            # 로드한 김에 목록 업데이트
                            if not df_temp.empty:
                                new_apts = df_temp['아파트'].unique().tolist()
                                utils.update_apt_list(target_lawd, new_apts)

                    # 데이터 필터링 및 표시
                    if df_current is not None and not df_current.empty:
                        apt_df = df_current[df_current['아파트'] == selected_apt].sort_values(by='계약일', ascending=False)
                        
                        # 선택된 아파트의 거래 건수 표시
                        trade_count = len(apt_df)
                        st.caption(f"해당 기간 거래 건수: {trade_count}건")
                        
                        # [NEW] 최근 실거래가 프리뷰
                        if not apt_df.empty:
                            latest = apt_df.iloc[0]
                            st.info(f"💡 최근 실거래가: {latest['거래금액']:,}만원 ({latest['계약일']}, {latest['층']}층, {latest['전용면적']}㎡)")
                            
                            with st.expander("📋 상세 거래 내역 미리보기"):
                                st.dataframe(
                                    apt_df[['계약일', '거래금액', '전용면적', '층']], 
                                    width="stretch",
                                    hide_index=True
                                )
                    else:
                        st.warning(f"{current_search_dt.strftime('%Y년 %m월')} 거래 내역이 없습니다.")
                    
                    # 거래 내역이 없어도 관심 단지 추가는 가능하도록 버튼 표시
                    if st.button("관심 단지 추가 ➕"):
                        # 중복 확인 (ID 제외하고 내용으로 비교)
                        is_duplicate = False
                        for fav in st.session_state['favorite_apts']:
                            if (fav['lawd_cd'] == target_lawd and fav['apt_name'] == selected_apt):
                                is_duplicate = True
                                break
                        
                        if not is_duplicate:
                            item = {
                                "id": str(uuid.uuid4()), # 고유 ID 생성
                                "lawd_cd": target_lawd,
                                "region_name": f"{selected_sido} {selected_sigungu}",
                                "apt_name": selected_apt
                            }
                            st.session_state['favorite_apts'].append(item)
                            utils.save_config() # 저장
                            st.success(f"'{selected_apt}' 추가됨")
                        else:
                            st.warning("이미 목록에 있습니다.")
            elif not service_key:
                st.warning("⚠️ 공공데이터포털 인증키가 필요합니다.")

            # [NEW] 관심 목록 표시 및 삭제 기능
            if st.session_state['favorite_apts']:
                st.markdown("---")
                st.caption("📋 관심 단지 목록")
                for i, item in enumerate(st.session_state['favorite_apts']):
                    col1, col2 = st.columns([0.85, 0.15])
                    col1.text(f"{item['apt_name']}\n({item['region_name']})")
                    if col2.button("🗑️", key=f"del_{i}"):
                        st.session_state['favorite_apts'].pop(i)
                        utils.save_config() # 저장
                        st.rerun()

    # 3. Crypto 설정
    with st.expander("🪙 코인 설정", expanded=False):
        coin_market_dict = data_manager.get_upbit_markets()
        
        # [FIX] 코인 기본값 세션 상태 초기화
        if 'selected_coins_state' not in st.session_state:
            default_coins = []
            if coin_market_dict:
                # 딕셔너리 키 중에서 비트코인을 찾아서 기본값으로 설정
                for key in coin_market_dict.keys():
                    if "KRW-BTC" in key:
                        default_coins.append(key)
            st.session_state['selected_coins_state'] = default_coins
        
        # [FIX] API 장애 등으로 코인 목록이 비어있을 때 설정을 덮어쓰지 않도록 보호
        if coin_market_dict:
            selected_coins = st.multiselect(
                "코인 선택 (이름 검색 가능)", 
                options=list(coin_market_dict.keys()),
                key="selected_coins_state", # 세션 상태와 연동
                on_change=utils.save_config # 변경 시 저장
            )
        else:
            st.warning("⚠️ 코인 목록을 불러올 수 없습니다. (일시적 API 오류 또는 네트워크 문제)")
            selected_coins = st.session_state.get('selected_coins_state', [])

    # 4. AI 설정
    with st.expander("🤖 AI 설정", expanded=False):
        env_gemini_key = os.getenv("GEMINI_API_KEY")
        if not env_gemini_key:
            gemini_api_key = st.text_input("Gemini API Key", type="password", help="Google AI Studio에서 발급받은 키를 입력하세요.", key="gemini_api_key_input")
        else:
            gemini_api_key = env_gemini_key

        if gemini_api_key:
            available_models = ai_manager.get_available_gemini_models(gemini_api_key)
            
            if available_models:
                # 세션 상태에 모델이 없거나 유효하지 않으면 기본값 설정
                if 'selected_ai_model' not in st.session_state or st.session_state['selected_ai_model'] not in available_models:
                    # 선호하는 모델 우선순위
                    preferred = ['models/gemini-1.5-flash', 'models/gemini-1.5-flash-latest', 'models/gemini-pro']
                    default_model = available_models[0]
                    for p in preferred:
                        if p in available_models:
                            default_model = p
                            break
                    st.session_state['selected_ai_model'] = default_model

                st.selectbox("사용할 AI 모델 선택", available_models, key="selected_ai_model", on_change=utils.save_config)
            else:
                st.warning("사용 가능한 모델을 불러올 수 없습니다. API 키를 확인해주세요.")

    # [NEW] 설정 초기화 버튼
    with st.expander("⚠️ 설정 초기화", expanded=False):
        st.caption("대시보드가 정상적으로 보이지 않을 때 초기화를 시도해보세요.")
        
        def reset_callback():
            st.session_state['selected_stocks_state'] = ["삼성전자 (005930.KS)", "TIGER 미국S&P500 (360750.KS)", "TIGER 미국나스닥100 (133690.KS)", "TIGER 미국필라델피아반도체 (381180.KS)", "ACE KRX금현물 (411060.KS)"]
            st.session_state['selected_coins_state'] = ["비트코인 (KRW-BTC)"]
            st.session_state['selected_ai_model'] = "models/gemini-2.5-flash"
            st.session_state['favorite_apts'] = [
                {
                    "id": "b56be813-e8ef-4048-8f09-db34ac138cc3",
                    "lawd_cd": "27260",
                    "region_name": "대구광역시 수성구",
                    "apt_name": "만촌삼정그린코아에듀파크"
                },
                {
                    "id": "b1f92a1b-55c8-4cc8-aefd-8f150a02843f",
                    "lawd_cd": "27260",
                    "region_name": "대구광역시 수성구",
                    "apt_name": "만촌자이르네"
                },
                {
                    "id": "a4d76f32-e513-444d-b386-b0216842ca98",
                    "lawd_cd": "27260",
                    "region_name": "대구광역시 수성구",
                    "apt_name": "수성2차e-편한세상"
                },
                {
                    "id": "c8bcc6e0-17d7-40ae-bef1-fd47f9316567",
                    "lawd_cd": "27140",
                    "region_name": "대구광역시 동구",
                    "apt_name": "동서맨션"
                }
            ]
            st.session_state['dashboard_order'] = [
                "exchange:USD/KRW",
                "coin:비트코인 (KRW-BTC)",
                "stock_rec:삼성전자 (005930.KS)",
                "stock_rec:TIGER 미국S&P500 (360750.KS)",
                "stock_rec:TIGER 미국나스닥100 (133690.KS)",
                "stock_rec:TIGER 미국필라델피아반도체 (381180.KS)",
                "real_estate:b56be813-e8ef-4048-8f09-db34ac138cc3",
                "real_estate:b1f92a1b-55c8-4cc8-aefd-8f150a02843f",
                "real_estate:a4d76f32-e513-444d-b386-b0216842ca98",
                "real_estate:c8bcc6e0-17d7-40ae-bef1-fd47f9316567"
            ]
            st.session_state['custom_stock_state'] = ""
            st.session_state['fetched_apt_data'] = {}
            utils.save_config()

        if st.button("모든 설정 초기화 (Factory Reset)", type="primary", on_click=reset_callback):
            st.toast("설정이 초기화되었습니다.", icon="🔄")

    # [NEW] 설정 파일 상태 표시
    st.markdown("---")
    if os.path.exists(utils.CONFIG_FILE):
        last_mod = datetime.datetime.fromtimestamp(os.path.getmtime(utils.CONFIG_FILE)).strftime('%Y-%m-%d %H:%M')
        st.caption(f"✅ 설정 저장됨 (최근 수정: {last_mod})")
    else:
        st.caption("ℹ️ 기본 설정 사용 중 (저장된 파일 없음)")

    st.divider()
    if st.button("데이터 새로고침"):
        st.rerun()

# 5. 메인 대시보드 UI 구성
st.title("📊 통합 자산 모니터링 대시보드")

st.subheader("📍 실시간 요약")

# [NEW] 환율 정보 가져오기 및 표시
usd_to_krw_rate, usd_change = data_manager.get_exchange_rate("USD", "KRW")
if usd_to_krw_rate:
    st.caption(f"현재 환율: 1 USD ≈ {usd_to_krw_rate:,.2f} KRW")

# 표시할 모든 메트릭 데이터를 수집
metrics_data = []

# [NEW] 환율 정보 추가
if usd_to_krw_rate:
    metrics_data.append({
        "label": "💵 달러 환율",
        "value": f"{usd_to_krw_rate:,.2f} KRW",
        "delta": f"{usd_change:.2f}%",
        "type": "exchange",
        "id": "KRW=X",
        "key": "exchange:USD/KRW"
    })

# 1. 코인 데이터 수집
for name in selected_coins:
    ticker = coin_market_dict.get(name)
    if ticker:
        price, change = data_manager.get_crypto_price(ticker)
        metrics_data.append({
            "label": f"🪙 {name}",
            "value": f"{price:,.0f} KRW",
            "delta": f"{change:.2f}%",
            "type": "coin",
            "id": name,
            "key": f"coin:{name}"
        })

# 2. 주식 데이터 수집
for name in selected_stocks:
    ticker = utils.STOCK_RECOMMENDATIONS.get(name)
    if ticker:
        price, change, currency = data_manager.get_stock_price(ticker)
        
        # 통화에 따른 포맷팅
        if currency == "USD":
            value_fmt = f"${price:,.2f}"
            # [NEW] 원화 환산 가격 추가
            if usd_to_krw_rate:
                krw_price = price * usd_to_krw_rate
                value_fmt += f" (≈ {krw_price:,.0f} 원)"
        elif currency == "KRW":
            value_fmt = f"{price:,.0f} KRW"
        else:
            value_fmt = f"{price:,.2f} {currency}"
            
        metrics_data.append({
            "label": f"📈 {name}",
            "value": value_fmt,
            "delta": f"{change:.2f}%",
            "type": "stock_rec",
            "id": name,
            "key": f"stock_rec:{name}"
        })

if custom_stock_input:
    custom_tickers = [t.strip() for t in custom_stock_input.split(',') if t.strip()]
    for ticker in custom_tickers:
        price, change, currency = data_manager.get_stock_price(ticker)
        
        # 통화에 따른 포맷팅
        if currency == "USD":
            value_fmt = f"${price:,.2f}"
            # [NEW] 원화 환산 가격 추가
            if usd_to_krw_rate:
                krw_price = price * usd_to_krw_rate
                value_fmt += f" (≈ {krw_price:,.0f} 원)"
        elif currency == "KRW":
            value_fmt = f"{price:,.0f} KRW"
        else:
            value_fmt = f"{price:,.2f} {currency}"
            
        metrics_data.append({
            "label": f"📈 {ticker}",
            "value": value_fmt,
            "delta": f"{change:.2f}%",
            "type": "stock_custom",
            "id": ticker,
            "key": f"stock_custom:{ticker}"
        })

# 3. 부동산 데이터 수집
df_display = pd.DataFrame() # 상세 데이터 탭을 위한 통합 데이터프레임

if use_real_estate:
    if st.session_state['favorite_apts']:
        with st.spinner("부동산 데이터 업데이트 중..."):
            for idx, item in enumerate(st.session_state['favorite_apts']):
                # 기존 데이터에 ID가 없는 경우 호환성 처리
                if 'id' not in item: item['id'] = str(uuid.uuid4())
                
                # 각 관심 단지별 데이터 로드
                # [IMPROVE] 최근 3개월 데이터를 조회하여 가장 최신 거래 정보를 표시 (거래 절벽 대응)
                ts = st.session_state.get('cache_invalidation_ts', {}).get(item['lawd_cd'], 0)
                df = data_manager.get_period_apt_data(service_key, item['lawd_cd'], months=3, _cache_ts=ts)
                
                if not df.empty:
                    # 해당 아파트만 필터링 및 최신순 정렬
                    apt_df = df[df['아파트'] == item['apt_name']].sort_values(by='계약일', ascending=False)
                    
                    if not apt_df.empty:
                        # 상세 데이터 병합 (대시보드 전체 분석용)
                        df_display = pd.concat([df_display, apt_df], ignore_index=True)
                        
                        # 메트릭(요약) 추가 - 가장 최신 거래 1건
                        recent = apt_df.iloc[0]
                        
                        # 계약일 포맷팅 (YYYY-MM-DD -> MM-DD)
                        deal_date = str(recent['계약일'])
                        if len(deal_date) >= 10: deal_date = deal_date[5:]
                        
                        metrics_data.append({
                            "label": f"🏠 {item['apt_name']}",
                            "value": f"{recent['거래금액']:,} 만원",
                            "delta": f"{deal_date} | {recent['층']}층 ({recent['전용면적']}㎡)",
                            "type": "real_estate",
                            "id": idx,
                            "key": f"real_estate:{item['id']}"
                        })
                    else:
                        metrics_data.append({"label": f"🏠 {item['apt_name']}", "value": "최근 3개월 거래 없음", "delta": "-", "type": "real_estate", "id": idx, "key": f"real_estate:{item['id']}"})
                else:
                    metrics_data.append({"label": f"🏠 {item['apt_name']}", "value": "데이터 없음", "delta": "API 확인", "type": "real_estate", "id": idx, "key": f"real_estate:{item['id']}"})
    else:
        metrics_data.append({
            "label": "🏠 부동산",
            "value": "관심 단지 없음",
            "delta": "설정에서 추가",
            "type": "info",
            "id": None,
            "key": "info:real_estate"
        })

# [NEW] 순서 동기화 및 정렬
# 1. 현재 존재하는 모든 키 수집
current_keys = [m['key'] for m in metrics_data]

# 2. 세션에 저장된 순서 리스트 업데이트 (삭제된 항목 제거)
# [FIX] 일시적인 데이터 로드 실패 시 설정이 삭제되는 것을 방지하기 위해 자동 삭제 로직 제거
# st.session_state['dashboard_order'] = [k for k in st.session_state['dashboard_order'] if k in current_keys]

# 3. 새로운 항목을 순서 리스트 끝에 추가
for k in current_keys:
    if k not in st.session_state['dashboard_order']:
        st.session_state['dashboard_order'].append(k)

# 4. 저장된 순서대로 metrics_data 정렬
metrics_map = {m['key']: m for m in metrics_data}
ordered_metrics = []
for k in st.session_state['dashboard_order']:
    if k in metrics_map:
        ordered_metrics.append(metrics_map[k])

# [NEW] 사이드바에 드래그 앤 드롭 순서 변경 위젯 추가
with st.sidebar:
    st.divider()
    st.subheader("⇅ 순서 변경")
    if sort_items and ordered_metrics:
        # 현재 표시된 라벨 목록 생성
        labels = [m['label'] for m in ordered_metrics]
        # 드래그 앤 드롭 위젯 표시
        sorted_labels = sort_items(labels)
        
        # 순서가 변경되었다면 세션 상태 업데이트
        if sorted_labels != labels:
            label_to_key = {m['label']: m['key'] for m in ordered_metrics}
            new_order = [label_to_key[lbl] for lbl in sorted_labels if lbl in label_to_key]
            
            # [FIX] 화면에 보이지 않는 항목(데이터 로드 실패 등)이 삭제되지 않도록 보존
            visible_keys = set(label_to_key.values())
            hidden_items = [k for k in st.session_state['dashboard_order'] if k not in visible_keys]
            
            st.session_state['dashboard_order'] = new_order + hidden_items
            utils.save_config() # 순서 변경 저장
            st.rerun()
    elif not sort_items:
        st.warning("'streamlit-sortables' 라이브러리가 필요합니다.")

# 동적 그리드 레이아웃 (3열)
if ordered_metrics:
    cols = st.columns(3)
    for i, metric in enumerate(ordered_metrics):
        with cols[i % 3]:
            # 정보성 메시지인 경우 (삭제/차트 기능 없음)
            if metric.get("type") == "info":
                with st.container(border=True):
                    st.metric(label=metric["label"], value=metric["value"], delta=metric["delta"])
            else:
                # 상호작용 가능한 아이템: 버튼으로 변경 (클릭 시 차트 자동 선택)
                # 버튼 라벨에 주요 정보 표시 (줄바꿈으로 구분)
                btn_label = f"{metric['label']}\n{metric['value']}"
                
                if st.button(btn_label, key=f"btn_{i}", width="stretch"):
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
        lawd_cd_for_cache = None
        if target['type'] == 'real_estate' and 0 <= target['id'] < len(st.session_state['favorite_apts']):
            lawd_cd_for_cache = st.session_state['favorite_apts'][target['id']]['lawd_cd']

        # 헤더, 기간 선택기, 삭제 버튼을 나란히 배치
        if target['type'] in ['coin', 'stock_rec', 'stock_custom', 'exchange']:
            col_title, col_period, col_del = st.columns([0.3, 0.5, 0.2])
        else: # 부동산
            col_title, col_period, col_del = st.columns([0.3, 0.5, 0.2])

        with col_title:
            st.markdown(f"### {target['label']}")

        with col_period:
            if target['type'] in ['coin', 'stock_rec', 'stock_custom', 'exchange']:
                period = st.radio(
                    "조회 기간", 
                    ["1주일", "1개월", "3개월", "1년", "5년", "10년", "전체"], 
                    index=3, 
                    horizontal=True,
                    label_visibility="collapsed",
                    key="period_crypto_stock"
                )
            elif target['type'] == 'real_estate':
                period = st.radio(
                    "조회 기간",
                    ["1년", "3년", "5년"],
                    index=0,
                    horizontal=True,
                    label_visibility="collapsed",
                    key="period_real_estate"
                )
            
            if target['type'] == 'real_estate' and lawd_cd_for_cache:
                if st.button("🔄 캐시 새로고침"):
                    st.session_state.setdefault('cache_invalidation_ts', {})[lawd_cd_for_cache] = time.time()
                    st.toast(f"'{target['label']}' 지역의 캐시가 삭제되었습니다.", icon="🧹")
                    st.rerun()
                
                ts = st.session_state.get('cache_invalidation_ts', {}).get(lawd_cd_for_cache, 0)
                if ts > 0:
                    kst = datetime.timezone(datetime.timedelta(hours=9))
                    dt_kst = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).astimezone(kst)
                    st.caption(f"최근 갱신: {dt_kst.strftime('%Y-%m-%d %H:%M')} (KST)")
        
        with col_del:
            # 현재 선택된 자산 삭제 버튼
            if target['type'] != 'exchange' and st.button("대시보드에서 삭제", key="del_current_asset", type="primary"):
                if target["type"] == "coin":
                    if target["id"] in st.session_state['selected_coins_state']:
                        st.session_state['selected_coins_state'].remove(target["id"])
                        utils.save_config()
                elif target["type"] == "stock_rec":
                    if target["id"] in st.session_state['selected_stocks_state']:
                        st.session_state['selected_stocks_state'].remove(target["id"])
                elif target["type"] == "stock_custom":
                    current_input = st.session_state['custom_stock_state']
                    tickers = [t.strip() for t in current_input.split(',') if t.strip()]
                    if target["id"] in tickers:
                        tickers.remove(target["id"])
                    st.session_state['custom_stock_state'] = ", ".join(tickers)
                    utils.save_config()
                elif target["type"] == "real_estate":
                    # 인덱스 유효성 확인 후 삭제
                    if 0 <= target["id"] < len(st.session_state['favorite_apts']):
                        st.session_state['favorite_apts'].pop(target["id"])
                        utils.save_config()
                
                # [NEW] 대시보드 순서 설정에서도 제거
                if target['key'] in st.session_state['dashboard_order']:
                    st.session_state['dashboard_order'].remove(target['key'])
                
                st.session_state['selected_asset'] = None
                st.rerun()
        
        # 1. 코인 차트 (업비트)
        if target['type'] == 'coin':
            coin_market_dict = data_manager.get_upbit_markets()
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
                    st.plotly_chart(fig, width="stretch")
                except:
                    st.error("차트 데이터를 불러올 수 없습니다.")
        
        # 2. 주식 차트 (Yahoo Finance)
        elif target['type'] in ['stock_rec', 'stock_custom', 'exchange']:
            ticker = target['id']
            if target['type'] == 'stock_rec':
                ticker = utils.STOCK_RECOMMENDATIONS.get(target['id'])
            
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
                    
                    if df.empty:
                        st.warning("해당 기간의 데이터가 없습니다.")
                    else:
                        # 인덱스(Date)를 컬럼으로 변환하여 Plotly에 사용
                        df = df.reset_index()
                        
                        # 날짜 컬럼 식별 (Date 또는 Datetime)
                        date_col = 'Date'
                        if 'Date' not in df.columns:
                            date_col = 'Datetime' if 'Datetime' in df.columns else df.columns[0]

                        fig = px.line(df, x=date_col, y='Close', title=f"{target['label']} 추이")
                        fig.update_layout(hovermode="x unified")
                        st.plotly_chart(fig, width="stretch")
                except Exception as e:
                    st.error(f"차트 데이터를 불러올 수 없습니다: {e}")

        # 3. 부동산 차트 (최근 거래 내역)
        elif target['type'] == 'real_estate':
            st.caption(f"ℹ️ 부동산 차트는 최근 {period}간의 평형별 실거래가 추이를 보여줍니다.")
            
            # 인덱스 유효성 확인
            if not (use_real_estate and 0 <= target['id'] < len(st.session_state['favorite_apts'])):
                st.warning("선택된 부동산 정보를 찾을 수 없습니다. 목록에서 삭제되었을 수 있습니다.")
            else:
                apt_info = st.session_state['favorite_apts'][target['id']]
                apt_name = apt_info['apt_name']
                lawd_cd = apt_info['lawd_cd']
                
                months = 12
                if period == "3년": months = 36
                elif period == "5년": months = 60
                
                ts = st.session_state.get('cache_invalidation_ts', {}).get(lawd_cd, 0)
                period_data = data_manager.get_period_apt_data(service_key, lawd_cd, months=months, _cache_ts=ts)
                
                if period_data.empty:
                    st.info(f"최근 {period}간 해당 지역의 거래 데이터가 없습니다.")
                else:
                    apt_period_data = period_data[period_data['아파트'] == apt_name].copy()
                    
                    if apt_period_data.empty:
                        st.info(f"최근 {period}간 '{apt_name}'의 거래 데이터가 없습니다.")
                    else:
                        # 데이터 전처리
                        apt_period_data['평형'] = round(apt_period_data['전용면적'] / 3.3058, 1)
                        bins = [0, 20, 30, 40, 50, 60, 1000]
                        labels = ['20평 미만', '20평대', '30평대', '40평대', '50평대', '60평 이상']
                        apt_period_data['평형대'] = pd.cut(apt_period_data['평형'], bins=bins, labels=labels, right=False)
                        apt_period_data['계약일'] = pd.to_datetime(apt_period_data['계약일'])
                        
                        # [NEW] 전용면적별 데이터 나열
                        unique_areas = sorted(apt_period_data['전용면적'].unique())
                        
                        # 1. 요약 정보 (테이블)
                        st.markdown(f"#### 📊 전용면적별 요약 (최근 {period})")
                        summary_data = []
                        for area in unique_areas:
                            sub_df = apt_period_data[apt_period_data['전용면적'] == area]
                            summary_data.append({
                                "전용면적": f"{area}㎡",
                                "평형": f"{round(area/3.3058, 1)}평",
                                "거래량": f"{len(sub_df)}건",
                                "평균가": f"{sub_df['거래금액'].mean()/10000:.2f}억",
                                "최고가": f"{sub_df['거래금액'].max()/10000:.2f}억",
                                "최저가": f"{sub_df['거래금액'].min()/10000:.2f}억"
                            })
                        st.dataframe(pd.DataFrame(summary_data), hide_index=True, width="stretch")

                        # 2. 상세 정보 (탭 구성)
                        if unique_areas:
                            st.markdown("#### 📈 면적별 상세 분석")
                            tabs = st.tabs([f"{area}㎡" for area in unique_areas])
                            
                            for i, area in enumerate(unique_areas):
                                with tabs[i]:
                                    filtered_df = apt_period_data[apt_period_data['전용면적'] == area].copy()
                                    filtered_df['거래금액_억'] = filtered_df['거래금액'] / 10000
                                    
                                    # 차트와 표를 좌우로 배치하여 공간 절약
                                    c1, c2 = st.columns([0.6, 0.4])
                                    
                                    with c1:
                                        fig = px.scatter(
                                            filtered_df.sort_values('계약일'), 
                                            x='계약일', y='거래금액_억', 
                                            hover_data=['층', '전용면적', '평형', '거래금액'],
                                            template='plotly_white', # 깔끔한 흰색 배경
                                            color_discrete_sequence=['#4C78A8'] # 차분한 파란색
                                        )
                                        
                                        # [NEW] 추세선 및 변동폭(채널) 추가 - Trend 방향과 폭 시각화
                                        if len(filtered_df) >= 2:
                                            df_sorted = filtered_df.sort_values('계약일')
                                            # 회귀분석을 위한 수치형 변환
                                            x_numeric = df_sorted['계약일'].map(lambda x: x.timestamp())
                                            y_values = df_sorted['거래금액_억']
                                            
                                            # [CHANGED] 다차 회귀분석 (Polynomial Regression)
                                            # 데이터 개수에 따라 차수 동적 결정 (최대 3차)
                                            degree = min(3, len(filtered_df) - 1)
                                            coeffs = np.polyfit(x_numeric, y_values, degree)
                                            poly_eqn = np.poly1d(coeffs)
                                            trend_line = poly_eqn(x_numeric)
                                            
                                            # 변동폭 계산 (Standard Deviation of Residuals)
                                            # 다차 회귀이므로 복잡한 예측 구간 공식 대신 잔차 표준편차 활용
                                            residuals = y_values - trend_line
                                            std_dev = residuals.std()
                                            
                                            # 민감도 1.5배 적용 (약 87% 신뢰구간)
                                            upper_bound = trend_line + (1.5 * std_dev)
                                            lower_bound = trend_line - (1.5 * std_dev)
                                            
                                            # 1. 상단 밴드 (투명선)
                                            fig.add_trace(go.Scatter(
                                                x=df_sorted['계약일'], y=upper_bound,
                                                mode='lines', line=dict(width=0),
                                                showlegend=False, hoverinfo='skip'
                                            ))
                                            # 2. 하단 밴드 (상단과 채우기 = Trend Width)
                                            fig.add_trace(go.Scatter(
                                                x=df_sorted['계약일'], y=lower_bound,
                                                mode='lines', line=dict(width=0),
                                                fill='tonexty', fillcolor='rgba(76, 120, 168, 0.1)',
                                                showlegend=False, hoverinfo='skip'
                                            ))
                                            # 3. 추세선 (중앙)
                                            fig.add_trace(go.Scatter(
                                                x=df_sorted['계약일'], y=trend_line,
                                                mode='lines', name='추세',
                                                line=dict(color='rgba(255, 99, 71, 0.8)', width=2, dash='dash'),
                                                showlegend=False # [CHANGED] 범례 숨김
                                            ))
                                        
                                        # 마커 디자인 개선 (크기 확대, 테두리 추가, 투명도)
                                        fig.update_traces(
                                            marker=dict(size=12, line=dict(width=1, color='white'), opacity=0.8)
                                        )
                                        
                                        # 레이아웃 정리 (타이틀 폰트, 여백, 축 설정)
                                        fig.update_layout(
                                            title=dict(text=f"{area}㎡ 실거래가 추이", font=dict(size=18, color="#333333")),
                                            yaxis_title="거래금액 (억원)", 
                                            xaxis_title=None, # X축 타이틀 제거
                                            height=500, # [CHANGED] 차트 높이 확대
                                            margin=dict(t=50, b=20, l=20, r=20),
                                            hovermode="closest"
                                        )
                                        fig.update_yaxes(tickformat=".2f")
                                        
                                        st.plotly_chart(fig, width="stretch")
                                    
                                    with c2:
                                        st.markdown("**거래 내역**")
                                        filtered_df['거래금액(억)'] = filtered_df['거래금액_억'].apply(lambda x: f"{x:.2f}억")
                                        st.dataframe(
                                            filtered_df[['계약일', '거래금액(억)', '층']].sort_values('계약일', ascending=False),
                                            width="stretch",
                                            hide_index=True,
                                            height=400
                                        )
    else:
        st.info("👆 대시보드에서 항목을 클릭하면 상세 차트가 표시됩니다.")
    
with tab2:
    st.subheader("상세 정보 및 뉴스")
    target = st.session_state.get('selected_asset')
    
    if target:
        st.markdown(f"### {target['label']}")
        
        # 검색어 추출 (이모지 제거 및 괄호 앞부분 추출)
        query = target['label']
        for emoji in ["🪙", "📈", "💵", "🏠"]:
            query = query.replace(emoji, "")
        query = query.split('(')[0].strip()
        
        if target['type'] == 'exchange':
            query = "원달러 환율"

        # 1. 뉴스 (주식, 코인, 환율)
        if target['type'] in ['stock_rec', 'stock_custom', 'exchange', 'coin']:
            utils.display_news(query)
            
            # 코인인 경우 네이버 검색 링크 추가
            if target['type'] == 'coin':
                 st.markdown(f"🔗 [네이버 뉴스 검색: {query}](https://search.naver.com/search.naver?where=news&query={query})")

        # 2. 부동산 상세
        elif target['type'] == 'real_estate':
            if use_real_estate and not df_display.empty:
                if 0 <= target['id'] < len(st.session_state['favorite_apts']):
                    apt_info = st.session_state['favorite_apts'][target['id']]
                    apt_name = apt_info['apt_name']
                    
                    st.write(f"**{apt_name} 실거래 내역**")
                    # 해당 아파트 데이터 필터링
                    apt_df = df_display[df_display['아파트'] == apt_name]
                    st.dataframe(apt_df, width="stretch")
                    
                    st.divider()
                    st.subheader("관련 정보")
                    # 검색어 URL 인코딩 처리
                    raw_query = f"{apt_info['region_name']} {apt_name}"
                    encoded_query = urllib.parse.quote(raw_query)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"🏢 [네이버 부동산 단지정보](https://land.naver.com/search/search.naver?query={encoded_query})")
                    with col2:
                        st.markdown(f"📰 [관련 뉴스 검색](https://search.naver.com/search.naver?where=news&query={encoded_query})")
                else:
                    st.warning("선택된 부동산 정보를 찾을 수 없습니다.")
            else:
                st.info("부동산 데이터가 없습니다.")
                
    else:
        st.info("👆 대시보드에서 항목을 선택하면 상세 정보와 뉴스를 확인할 수 있습니다.")

with tab3:
    st.subheader("🤖 AI 투자 분석 리포트")
    
    # Gemini API Key 확인
    if not gemini_api_key:
        st.warning("⚠️ Gemini API Key가 설정되지 않았습니다. 사이드바의 'AI 설정'에서 키를 입력하거나 .env 파일에 GEMINI_API_KEY를 설정해주세요.")
    else:
        target = st.session_state.get('selected_asset')
        
        if target and target.get('type') != 'info':
            st.markdown(f"### 📊 {target['label']} 심층 분석")
            
            if st.button("AI 리포트 생성하기 ✨", type="primary", width="stretch"):
                with st.spinner(f"Gemini가 {target['label']} 데이터를 분석하고 있습니다..."):
                    try:
                        # 컨텍스트 데이터 수집
                        context_text = f"자산명: {target['label']}\n현재가: {target['value']}\n변동률: {target['delta']}\n"
                        
                        # 1. 코인 데이터 추가 수집
                        if target['type'] == 'coin':
                            coin_market_dict = data_manager.get_upbit_markets()
                            ticker = coin_market_dict.get(target['id'])
                            if ticker:
                                url = f"https://api.upbit.com/v1/candles/days?market={ticker}&count=7"
                                candles = requests.get(url).json()
                                context_text += "\n[최근 7일 가격 추이]\n"
                                for c in candles:
                                    context_text += f"날짜: {c['candle_date_time_kst'][:10]}, 종가: {c['trade_price']}, 등락률: {c['change_rate']*100:.2f}%\n"

                        # 2. 주식 데이터 추가 수집
                        elif target['type'] in ['stock_rec', 'stock_custom', 'exchange']:
                            ticker = target['id']
                            if target['type'] == 'stock_rec':
                                ticker = utils.STOCK_RECOMMENDATIONS.get(target['id'], target['id'])
                            
                            stock = yf.Ticker(ticker)
                            hist = stock.history(period="1mo")
                            context_text += "\n[최근 1개월 주가 추이 요약]\n"
                            context_text += f"최고가: {hist['High'].max()}\n최저가: {hist['Low'].min()}\n평균가: {hist['Close'].mean()}\n"
                            
                            # 뉴스 헤드라인 추가
                            news = stock.news
                            if news:
                                context_text += "\n[최근 관련 뉴스 헤드라인]\n"
                                for n in news[:3]:
                                    context_text += f"- {n['title']}\n"

                        # 3. 부동산 데이터 추가 수집
                        elif target['type'] == 'real_estate':
                            if 0 <= target['id'] < len(st.session_state['favorite_apts']):
                                apt_info = st.session_state['favorite_apts'][target['id']]
                                
                                # API Key 확보
                                r_key = os.getenv("DATA_GO_KR_API_KEY")
                                if not r_key:
                                    r_key = st.session_state.get("input_service_key")
                                
                                if r_key:
                                    ts = st.session_state.get('cache_invalidation_ts', {}).get(apt_info['lawd_cd'], 0)
                                    yearly_df = data_manager.get_period_apt_data(r_key, apt_info['lawd_cd'], months=12, _cache_ts=ts)
                                    if not yearly_df.empty:
                                        apt_df = yearly_df[yearly_df['아파트'] == apt_info['apt_name']]
                                        if not apt_df.empty:
                                            context_text += f"\n[대상 아파트: {apt_info['apt_name']} - 최근 1년 거래 요약]\n"
                                            
                                            # 전용면적별 통계 추가
                                            for area in sorted(apt_df['전용면적'].unique()):
                                                area_df = apt_df[apt_df['전용면적'] == area]
                                                avg_p = area_df['거래금액'].mean()
                                                max_p = area_df['거래금액'].max()
                                                min_p = area_df['거래금액'].min()
                                                cnt = len(area_df)
                                                context_text += f"- 전용 {area}㎡: {cnt}건 거래, 평균 {avg_p:.0f}만원 (최고 {max_p}, 최저 {min_p})\n"
                                            
                                            context_text += f"최근 거래일: {apt_df['계약일'].max()}\n"

                                            # 주변 아파트 비교 (같은 법정동)
                                            if '법정동' in yearly_df.columns:
                                                target_dong = apt_df.iloc[0]['법정동']
                                                surrounding = yearly_df[(yearly_df['법정동'] == target_dong) & (yearly_df['아파트'] != apt_info['apt_name'])].copy()
                                                
                                                if not surrounding.empty:
                                                    context_text += f"\n[주변 아파트 ({target_dong}) 비교 데이터]\n"
                                                    # 평당가(3.3m2) 계산
                                                    my_avg_py = (apt_df['거래금액'] / apt_df['전용면적'] * 3.3).mean()
                                                    other_avg_py = (surrounding['거래금액'] / surrounding['전용면적'] * 3.3).mean()
                                                    
                                                    context_text += f"- 대상 단지 평균 평당가: {my_avg_py:.0f}만원\n"
                                                    context_text += f"- 주변 단지 평균 평당가: {other_avg_py:.0f}만원\n"
                                                    
                                                    # 주변 시세 상위 단지
                                                    surrounding['평당가'] = surrounding['거래금액'] / surrounding['전용면적'] * 3.3
                                                    top_apts = surrounding.groupby('아파트')['평당가'].mean().sort_values(ascending=False).head(3)
                                                    context_text += "- 주변 시세 상위 단지 (평당가):\n"
                                                    for name, val in top_apts.items():
                                                        context_text += f"  * {name}: {val:.0f}만원\n"

                        # Gemini 호출 (ai_manager 사용)
                        model_name = st.session_state.get('selected_ai_model', 'models/gemini-1.5-flash')
                        report = ai_manager.generate_investment_report(gemini_api_key, model_name, context_text)
                        st.markdown(report)
                        
                    except Exception as e:
                        st.error(f"리포트 생성 중 오류가 발생했습니다: {e}")
        else:
            st.info("👆 대시보드에서 분석할 자산 항목을 선택해주세요.")

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