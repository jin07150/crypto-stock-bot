import streamlit as st
import google.generativeai as genai

@st.cache_data(ttl=3600)
def get_available_gemini_models(api_key):
    try:
        genai.configure(api_key=api_key)
        models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                models.append(m.name)
        return models
    except Exception:
        return []

def generate_investment_report(api_key, model_name, context_text):
    """Gemini를 사용하여 투자 분석 리포트를 생성합니다."""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name)
        
        prompt = f"""
        당신은 금융 및 부동산 투자 전문가입니다. 아래 제공된 자산 데이터를 바탕으로 투자 분석 리포트를 작성해주세요.
        
        [분석 대상 데이터]
        {context_text}
        
        [요청 사항]
        1. 현재 시장 상황 분석 (가격 흐름 및 변동성)
        2. 주요 긍정적/부정적 요인 분석
        3. 향후 전망 및 투자 전략 (매수/매도/관망 의견 포함)
        4. 리스크 요인
        5. (부동산인 경우) 전용면적별 가격 적정성 및 주변 시세 대비 저평가/고평가 여부 분석
        
        마크다운 형식으로 가독성 있게 작성해주세요.
        """
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"리포트 생성 중 오류가 발생했습니다: {e}"
