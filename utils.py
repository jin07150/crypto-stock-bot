import streamlit as st
import os
import json
import time
import requests
import datetime
import xml.etree.ElementTree as ET

# 주요 주식 추천 목록
STOCK_RECOMMENDATIONS = {
    "삼성전자 (005930.KS)": "005930.KS", "SK하이닉스 (000660.KS)": "000660.KS",
    "현대차 (005380.KS)": "005380.KS", "NAVER (035420.KS)": "035420.KS",
    "카카오 (035720.KS)": "035720.KS",
    "TIGER 미국S&P500 (360750.KS)": "360750.KS",
    "TIGER 미국나스닥100 (133690.KS)": "133690.KS",
    "TIGER 미국필라델피아반도체 (381180.KS)": "381180.KS",
    "ACE KRX금현물 (411060.KS)": "411060.KS",
    "애플 (AAPL)": "AAPL",
    "테슬라 (TSLA)": "TSLA", "마이크로소프트 (MSFT)": "MSFT",
    "엔비디아 (NVDA)": "NVDA", "구글 (GOOGL)": "GOOGL", "아마존 (AMZN)": "AMZN"
}

CONFIG_FILE = "dashboard_config.json"
APT_LIST_FILE = "apt_list.json"
AUTH_FILE = ".auth_session"

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_config():
    config = {
        "favorite_apts": st.session_state.get("favorite_apts", []),
        "selected_coins": st.session_state.get("selected_coins_state", []),
        "selected_stocks": st.session_state.get("selected_stocks_state", []),
        "custom_stock": st.session_state.get("custom_stock_state", ""),
        "dashboard_order": st.session_state.get("dashboard_order", []),
        "selected_ai_model": st.session_state.get("selected_ai_model", "models/gemini-1.5-flash")
    }
    
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Config save failed: {e}")

def check_password():
    password = os.getenv("APP_PASSWORD")
    if not password:
        return True

    # [NEW] 저장된 인증 세션 확인 (30분 유효)
    if "password_correct" not in st.session_state:
        if os.path.exists(AUTH_FILE):
            try:
                with open(AUTH_FILE, "r") as f:
                    auth_data = json.load(f)
                    if auth_data.get("expiry", 0) > time.time():
                        st.session_state["password_correct"] = True
            except:
                pass

    if "password_attempts" not in st.session_state:
        st.session_state["password_attempts"] = 0
    if "block_until" not in st.session_state:
        st.session_state["block_until"] = 0

    if time.time() < st.session_state["block_until"]:
        remaining = int(st.session_state["block_until"] - time.time())
        st.error(f"⚠️ 입력 횟수 초과! {remaining}초 후에 다시 시도해주세요.")
        return False

    def password_entered():
        # [NEW] 이미 인증 성공한 경우 중복 실행 방지 (on_change와 on_click 동시 발생 시)
        if st.session_state.get("password_correct", False):
            return

        # [FIX] KeyError 방지를 위해 get() 사용
        if st.session_state.get("password", "") == password:
            st.session_state["password_correct"] = True
            st.session_state["password_attempts"] = 0
            
            # [NEW] 인증 성공 시 30분간 유효한 세션 파일 저장
            try:
                with open(AUTH_FILE, "w") as f:
                    json.dump({"expiry": time.time() + 1800}, f)
            except Exception as e:
                print(f"Auth save failed: {e}")

            if "password" in st.session_state:
                del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
            st.session_state["password_attempts"] += 1
            if st.session_state["password_attempts"] >= 5:
                st.session_state["block_until"] = time.time() + 30
                st.session_state["password_attempts"] = 0

    if "password_correct" not in st.session_state:
        st.text_input("🔐 비밀번호를 입력하세요", type="password", on_change=password_entered, key="password")
        st.button("확인", on_click=password_entered)
        return False
    elif not st.session_state["password_correct"]:
        if time.time() < st.session_state["block_until"]:
            remaining = int(st.session_state["block_until"] - time.time())
            st.error(f"⚠️ 입력 횟수 초과! {remaining}초 후에 다시 시도해주세요.")
            return False
        st.text_input("🔐 비밀번호를 입력하세요", type="password", on_change=password_entered, key="password")
        st.button("확인", on_click=password_entered)
        st.error(f"비밀번호가 틀렸습니다. ({st.session_state['password_attempts']}/5회 시도)")
        return False
    else:
        return True

def display_news(keyword):
    """Google News RSS를 검색하여 뉴스를 표시하는 함수"""
    try:
        st.caption(f"'{keyword}' 관련 최신 뉴스 (Google News)")
        url = f"https://news.google.com/rss/search?q={keyword}&hl=ko&gl=KR&ceid=KR:ko"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            items = root.findall('.//item')
            
            if items:
                for item in items[:5]:
                    title = item.find('title').text
                    link = item.find('link').text
                    pub_date = item.find('pubDate').text
                    source_elem = item.find('source')
                    source = source_elem.text if source_elem is not None else "Google News"
                    
                    with st.container(border=True):
                        st.markdown(f"**[{title}]({link})**")
                        try:
                            dt = datetime.datetime.strptime(pub_date, "%a, %d %b %Y %H:%M:%S %Z")
                            date_str = dt.strftime('%Y-%m-%d %H:%M')
                            st.caption(f"{source} | {date_str}")
                        except:
                            st.caption(f"{source} | {pub_date}")
            else:
                st.info("관련 뉴스가 없습니다.")
        else:
            st.warning("뉴스 데이터를 가져오지 못했습니다.")
    except Exception as e:
        st.error(f"뉴스 로딩 중 오류: {e}")

def get_apt_list(lawd_cd):
    """저장된 아파트 목록 파일에서 해당 지역의 아파트 리스트를 불러옵니다."""
    if os.path.exists(APT_LIST_FILE):
        try:
            with open(APT_LIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(lawd_cd, [])
        except:
            return []
    return []

def update_apt_list(lawd_cd, new_list):
    """새로운 아파트 목록을 기존 파일에 병합하여 저장합니다."""
    data = {}
    if os.path.exists(APT_LIST_FILE):
        try:
            with open(APT_LIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            data = {}
    
    current_list = data.get(lawd_cd, [])
    # 기존 목록과 새 목록을 합치고 중복 제거 후 정렬
    updated_set = set(current_list)
    updated_set.update(new_list)
    updated_list = sorted(list(updated_set))
    
    data[lawd_cd] = updated_list
    
    try:
        with open(APT_LIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Failed to save apt list: {e}")
        
    return updated_list
