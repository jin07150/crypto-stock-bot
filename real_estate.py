import requests
import pandas as pd
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
import os

load_dotenv()

def get_apartment_sales(lawd_cd, deal_ymd):
    api_key = os.getenv("DATA_GO_KR_API_KEY")
    url = "http://openapi.molit.go.kr:8081/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSObjSvcAptTradeDev"
    
    params = {
        'serviceKey': api_key,
        'LAWD_CD': lawd_cd,   # 행정구역코드 (예: 11110 종로구)
        'DEAL_YMD': deal_ymd  # 계약년월 (예: 202312)
    }

    response = requests.get(url, params=params)
    
    # XML 데이터 파싱
    root = ET.fromstring(response.text)
    items = root.findall('.//item')
    
    data = []
    for item in items:
        data.append({
            '아파트': item.findtext('아파트'),
            '금액': item.findtext('거래금액').strip(),
            '전용면적': item.findtext('전용면적'),
            '층': item.findtext('층'),
            '년': item.findtext('년'),
            '월': item.findtext('월'),
            '일': item.findtext('일')
        })
    
    return pd.DataFrame(data)

# 테스트 실행 (종로구 2023년 12월 데이터)
# df = get_apartment_sales('11110', '202312')
# print(df.head())