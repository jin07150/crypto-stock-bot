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
    외부 CSV 링크가 불안정할 경우를 대비해 주요 지역을 내장 데이터로 제공합니다.
    """
    data = [
        # 서울특별시
        {"시도": "서울특별시", "시군구": "강남구", "lawd_cd": "11680"},
        {"시도": "서울특별시", "시군구": "서초구", "lawd_cd": "11650"},
        {"시도": "서울특별시", "시군구": "송파구", "lawd_cd": "11710"},
        {"시도": "서울특별시", "시군구": "용산구", "lawd_cd": "11170"},
        {"시도": "서울특별시", "시군구": "성동구", "lawd_cd": "11200"},
        {"시도": "서울특별시", "시군구": "마포구", "lawd_cd": "11440"},
        {"시도": "서울특별시", "시군구": "영등포구", "lawd_cd": "11560"},
        {"시도": "서울특별시", "시군구": "종로구", "lawd_cd": "11110"},
        {"시도": "서울특별시", "시군구": "중구", "lawd_cd": "11140"},
        {"시도": "서울특별시", "시군구": "강동구", "lawd_cd": "11740"},
        {"시도": "서울특별시", "시군구": "양천구", "lawd_cd": "11470"},
        
        # 경기도
        {"시도": "경기도", "시군구": "성남시 분당구", "lawd_cd": "41135"},
        {"시도": "경기도", "시군구": "성남시 수정구", "lawd_cd": "41131"},
        {"시도": "경기도", "시군구": "수원시 영통구", "lawd_cd": "41117"},
        {"시도": "경기도", "시군구": "용인시 수지구", "lawd_cd": "41465"},
        {"시도": "경기도", "시군구": "고양시 일산동구", "lawd_cd": "41285"},
        {"시도": "경기도", "시군구": "화성시", "lawd_cd": "41590"},
        {"시도": "경기도", "시군구": "과천시", "lawd_cd": "41290"},
        {"시도": "경기도", "시군구": "하남시", "lawd_cd": "41450"},

        # 주요 광역시
        {"시도": "부산광역시", "시군구": "해운대구", "lawd_cd": "26350"},
        {"시도": "부산광역시", "시군구": "수영구", "lawd_cd": "26500"},
        {"시도": "대구광역시", "시군구": "수성구", "lawd_cd": "27260"},
        {"시도": "인천광역시", "시군구": "연수구", "lawd_cd": "28185"},
        {"시도": "세종특별자치시", "시군구": "세종시", "lawd_cd": "36110"},
    ]
    
    df = pd.DataFrame(data)
    return df.sort_values(by=['시도', '시군구'])