import requests
import pandas as pd
import xml.etree.ElementTree as ET
import traceback

def get_apt_trade_data(service_key: str, lawd_cd: str, deal_ymd: str) -> pd.DataFrame:
    """
    국토교통부 아파트매매 실거래가 API를 조회하여 DataFrame으로 반환합니다.
    """
    # 국토교통부 아파트매매 실거래가 상세 자료 조회 URL
    url = "http://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
    
    params = {
        "serviceKey": requests.utils.unquote(service_key), # API 키 디코딩 적용
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": "1000",  # 한 페이지 결과 수
        "pageNo": "1"        # 페이지 번호
    }
    
    try:
        print(f"🔍 [API Request] LAWD_CD: {lawd_cd}, DEAL_YMD: {deal_ymd}")
        response = requests.get(url, params=params)
        
        print(f"📡 [API Response] Status: {response.status_code}")
        print(f"🔗 [Full URL]: {response.url}")
        
        # 응답 상태 확인
        if response.status_code != 200:
            print(f"❌ [HTTP Error]: {response.status_code}")
            print(f"📄 [Response Body]: {response.text}")
            return pd.DataFrame()
            
        # XML 파싱
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            print(f"❌ [XML Parse Error]: {e}")
            print(f"📄 [Response Content]: {response.text}")
            return pd.DataFrame()
        
        # API 에러 응답 확인
        result_code = root.find("header/resultCode")
        result_msg = root.find("header/resultMsg")
        
        if result_code is not None:
            print(f"ℹ️ [API Result] Code: {result_code.text}, Msg: {result_msg.text if result_msg is not None else ''}")
            # 성공 코드가 '00' 또는 '000'일 수 있음
            if result_code.text not in ["00", "000"]:
                print(f"❌ [API Error]: {result_msg.text if result_msg is not None else 'Unknown'} (Code: {result_code.text})")
                return pd.DataFrame()
        
        items = root.findall("body/items/item")
        print(f"✅ [Data Found]: {len(items)} items")
        
        if not items:
            return pd.DataFrame()

        data_list = []
        for item in items:
            # XML 태그 값 추출 헬퍼 함수
            def get_text(tag):
                node = item.find(tag)
                return node.text.strip() if node is not None and node.text else ""

            # 거래금액 쉼표 제거 및 숫자 변환 (태그명 변경: 거래금액 -> dealAmount)
            amount_str = get_text("dealAmount").replace(',', '')
            amount = int(amount_str) if amount_str.isdigit() else 0
            
            # 전용면적 float 변환 (태그명 변경: 전용면적 -> excluUseAr)
            area_str = get_text("excluUseAr")
            area = float(area_str) if area_str else 0.0

            data_list.append({
                "아파트": get_text("aptNm"),       # 아파트 -> aptNm
                "법정동": get_text("umdNm"),       # 법정동 -> umdNm
                "거래금액": amount,
                "전용면적": area,
                "층": get_text("floor"),           # 층 -> floor
                "건축년도": get_text("buildYear"), # 건축년도 -> buildYear
                "년": get_text("dealYear"),        # 년 -> dealYear
                "월": get_text("dealMonth"),       # 월 -> dealMonth
                "일": get_text("dealDay"),         # 일 -> dealDay
                "계약일": f"{get_text('dealYear')}-{get_text('dealMonth').zfill(2)}-{get_text('dealDay').zfill(2)}"
            })
            
        df = pd.DataFrame(data_list)
        
        return df
        
    except Exception as e:
        print(f"Error occurred: {e}")
        traceback.print_exc()
        return pd.DataFrame()

def get_district_codes() -> pd.DataFrame:
    """
    대한민국 행정구역(시군구) 코드를 가져옵니다.
    제공된 딕셔너리 데이터를 기반으로 DataFrame을 생성합니다.
    """
    # 지역 명칭을 키로, 코드를 값으로 하는 딕셔너리
    REGION_CODES = {
        # 서울특별시
        "서울 강남구": "11680",
        "서울 서초구": "11650",
        "서울 송파구": "11710",
        "서울 마포구": "11440",
        "서울 용산구": "11170",
        "서울 성동구": "11200",
        "서울 종로구": "11110",
        
        # 대구광역시
        "대구 수성구": "27260",
        "대구 중구": "27110",
        "대구 동구": "27140",
        "대구 서구": "27170",
        "대구 남구": "27200",
        "대구 북구": "27230",
        "대구 달서구": "27290",
        "대구 달성군": "27710"
    }
    
    data = []
    for name, code in REGION_CODES.items():
        parts = name.split()
        if len(parts) >= 2:
            sido = parts[0]
            sigungu = " ".join(parts[1:])
            
            # UI 편의를 위해 시도 명칭 확장 (서울 -> 서울특별시)
            if sido == "서울": sido = "서울특별시"
            elif sido == "대구": sido = "대구광역시"
            
            data.append({
                "시도": sido,
                "시군구": sigungu,
                "lawd_cd": code
            })
    
    df = pd.DataFrame(data)
    return df.sort_values(by=['시도', '시군구'])