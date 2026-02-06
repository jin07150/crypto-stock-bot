import streamlit as st
import requests
import pandas as pd
import yfinance as yf
import datetime
from real_estate_loader import get_apt_trade_data

@st.cache_data(ttl=604800)
def fetch_apt_trade_data_cached(service_key, lawd_cd, deal_ymd, _cache_ts=0):
    return get_apt_trade_data(service_key, lawd_cd, deal_ymd)

@st.cache_data(ttl=604800)
def get_period_apt_data(service_key, lawd_cd, months=12, _cache_ts=0):
    if not service_key:
        return pd.DataFrame()
        
    today = datetime.date.today()
    all_dfs = []
    
    ym_to_fetch = []
    for i in range(months):
        current_date = today - pd.DateOffset(months=i)
        deal_ymd = current_date.strftime("%Y%m")
        ym_to_fetch.append(deal_ymd)

    with st.spinner(f"'{lawd_cd}' 지역의 최근 {months}개월 데이터를 불러옵니다..."):
        for deal_ymd in ym_to_fetch:
            df_month = fetch_apt_trade_data_cached(service_key, lawd_cd, deal_ymd, _cache_ts=_cache_ts)
            if not df_month.empty:
                all_dfs.append(df_month)
    
    return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()

@st.cache_data(ttl=86400)
def get_upbit_markets():
    try:
        url = "https://api.upbit.com/v1/market/all?isDetails=false"
        response = requests.get(url)
        data = response.json()
        market_dict = {}
        for item in data:
            if item['market'].startswith("KRW-"):
                market_dict[f"{item['korean_name']} ({item['market']})"] = item['market']
        return market_dict
    except Exception:
        return {}

@st.cache_data(ttl=60)
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

@st.cache_data(ttl=3600)
def get_exchange_rate(from_currency="USD", to_currency="KRW"):
    try:
        ticker_str = f"{from_currency}{to_currency}=X"
        if from_currency == "USD" and to_currency == "KRW":
            ticker_str = "KRW=X"
            
        ticker = yf.Ticker(ticker_str)
        hist = ticker.history(period="5d")
        
        if len(hist) >= 2:
            rate = hist['Close'].iloc[-1]
            prev = hist['Close'].iloc[-2]
            change = ((rate - prev) / prev) * 100
            return rate, change
        elif not hist.empty:
            return hist['Close'].iloc[-1], 0.0
        return None, 0.0
    except Exception:
        return None, 0.0
