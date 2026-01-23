import requests
import pandas as pd
import xml.etree.ElementTree as ET

def get_apt_trade_data(service_key: str, lawd_cd: str, deal_ymd: str) -> pd.DataFrame:
    """
    국토교통부 아파트매매 실거래가 API를 조회하여 DataFrame으로 반환합니다.
    """
    # 국토교통부 아파트매매 실거래가 상세 자료 조회 URL
    url = "http://openapi.molit.go.kr/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTradeDev"
    
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": "100",  # 한 페이지 결과 수
        "pageNo": "1"        # 페이지 번호
    }
    
    try:
        response = requests.get(url, params=params)
        
        # 응답 상태 확인
        if response.status_code != 200:
            return pd.DataFrame()
            
        # XML 파싱
        root = ET.fromstring(response.content)
        
        items = root.findall("body/items/item")
        
        if not items:
            return pd.DataFrame()

        data_list = []
        for item in items:
            # XML 태그 값 추출 헬퍼 함수
            def get_text(tag):
                node = item.find(tag)
                return node.text.strip() if node is not None and node.text else ""

            data_list.append({
                "아파트": get_text("아파트"),
                "법정동": get_text("법정동"),
                "거래금액": get_text("거래금액"),
                "전용면적": get_text("전용면적"),
                "층": get_text("층"),
                "건축년도": get_text("건축년도"),
                "계약일": get_text("일")
            })
            
        df = pd.DataFrame(data_list)
        
        # 데이터 타입 정리: 거래금액에서 콤마 제거 후 정수형으로 변환
        if '거래금액' in df.columns:
            df['거래금액'] = df['거래금액'].str.replace(',', '').astype(int)
            
        return df
        
    except Exception as e:
        print(f"Error occurred: {e}")
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