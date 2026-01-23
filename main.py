import requests
import time
from typing import List, Dict

def get_crypto_prices(session: requests.Session, tickers: List[str]) -> Dict[str, float]:
    """업비트 API를 이용해 여러 코인 가격을 리스트로 가져옵니다."""
    try:
        # 여러 티커를 콤마로 구분하여 하나의 문자열로 만듭니다.
        ticker_string = ",".join(tickers)
        url = f"https://api.upbit.com/v1/ticker?markets={ticker_string}"
        
        response = session.get(url)
        response.raise_for_status()  # HTTP 에러 발생 시 예외를 발생시킵니다.
        
        data = response.json()
        
        # {티커: 가격} 형태의 딕셔너리로 변환하여 반환합니다.
        prices = {item['market']: item['trade_price'] for item in data}
        return prices
        
    except requests.RequestException as e:
        print(f"\n에러 발생: {e}")
        return {} # 에러 발생 시 빈 딕셔너리 반환

if __name__ == "__main__":
    TICKERS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]  # 모니터링할 코인 목록
    TARGET_PRICE_BTC = 100000000  # 비트코인 목표 가격 설정 (예: 1억 원)
    print("🚀 실시간 코인 모니터링 시작 (종료: Ctrl+C)")
    
    # 세션을 사용하여 TCP 연결 재사용 (성능 최적화)
    with requests.Session() as session:
        while True:
            prices = get_crypto_prices(session, TICKERS)
            
            if prices:
                for ticker, price in prices.items():
                    print(f"💰 {ticker}: {price:,.0f} KRW")

                # 비트코인 목표가 달성 확인
                btc_price = prices.get("KRW-BTC")
                if btc_price and btc_price >= TARGET_PRICE_BTC:
                    print("\n🎉 비트코인 목표가 달성!")
                
                print("-" * 30) # 구분선
                
            time.sleep(2)