# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import io
import os
import ssl
import requests
import json
from matplotlib import font_manager
from fpdf import FPDF

# [강력 보안 우회] 모든 인증서 검사 및 보안 경고 무시
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['CURL_CA_BUNDLE'] = ''
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. 폰트 및 화면 설정
st.set_page_config(page_title="설문조사 통합 분석기", layout="wide")
font_filename = "NanumGothic.ttf"

if os.path.exists(font_filename):
    font_manager.fontManager.addfont(font_filename)
    plt.rc('font', family=font_manager.FontProperties(fname=font_filename).get_name())

# --------------------------------------------------------------------------
# [진단 기능 포함] AI 분석 함수
# --------------------------------------------------------------------------
def get_ai_analysis(prompt):
    api_key = st.secrets.get("GEMINI_API_KEY")
    # 가장 성공 확률이 높은 모델 2개만 시도
    model_list = ["gemini-1.5-flash", "gemini-pro"]
    
    last_error = ""
    for model in model_list:
        # v1 정식 API 경로 사용
        url = f"https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            # timeout을 10초로 짧게 설정하여 빠른 피드백 유도
            response = requests.post(url, headers=headers, data=json.dumps(payload), verify=False, timeout=10)
            
            if response.status_code == 200:
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            else:
                last_error = f"HTTP {response.status_code}: {response.text}"
        except Exception as e:
            last_error = f"연결 오류: {str(e)}"
            continue
            
    return f"🚨 모든 시도 실패\n사유: {last_error}"

# --------------------------------------------------------------------------
# 2. 메인 화면 로직
# --------------------------------------------------------------------------
st.title("📊 교육 만족도 통합 분석 리포트")
uploaded_file = st.file_uploader("엑셀 파일 업로드", type=['xlsx'])

if uploaded_file:
    try:
        # 시트명 고정: all responses
        df = pd.read_excel(uploaded_file, sheet_name='all responses', header=1)
        df_valid = df[df['답변 적격성'].str.strip() == '적격'].copy()
        
        # 1. 정량 분석 영역 (차트 및 표)
        st.subheader("1. 만족도 점수 결과")
        categories = {
            "교육 내용 만족도": ['교육 내용이 현재 또는 향후 업무에 유용하다고 생각하십니까?', '제공된 정보가 정확하고 최신 내용으로 구성되어 있었습니까?', '교육 내용의 난이도가 적절했다고 생각하십니까?', '교육 자료의 구성 및 체계가 논리적이고 이해하기 쉬웠습니까?'],
            "강사 만족도": ['강사는 교육 주제에 대한 충분한 전문 지식을 갖추고 있었습니까?', '강사의 전달 방식(말투, 속도, 태도)은 이해하기 쉬웠습니까?', '강사는 질문에 성실하게 답변하고 학습자의 참여를 유도했습니까?'],
            "교육 효과성": ['이번 교육을 통해 새로운 지식이나 기술을 습득할 수 있었습니까?', '교육 후, 관련 업무 수행에 대한 자신감이 향상되었습니까?', '교육에서 배운 내용이 학업/실무 역량 강화에 도움이 되었습니까?'],
            "운영 및 환경": ['교육 자료(교재 등)는 충분하고 활용도가 높았습니까?', '실습 진행을 위한 장비, 재료 및 환경이 충분하고 만족스러웠습니까?', '교육 시간이 적절했다고 생각하십니까?', '교육 장소의 환경이 쾌적했습니까?']
        }
        
        category_means = {cat: round(df_valid[cols].apply(pd.to_numeric, errors='coerce').mean().mean(), 2) for cat, cols in categories.items()}
        chart_df = pd.DataFrame(list(category_means.items()), columns=['영역', '점수'])

        # 차트 및 초대형 점수표 렌더링
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(chart_df['영역'], chart_df['점수'], color='#4A90E2')
        plt.xticks(rotation=20, ha='right')
        
        c1, c2 = st.columns([1.2, 1])
        with c1: st.pyplot(fig)
        with c2:
            html = f"<div style='border:2px solid #4A90E2; padding:15px; border-radius:10px; font-size:26px; font-weight:bold;'>"
            html += "<table style='width:100%; border-collapse:collapse;'>"
            for _, r in chart_df.iterrows():
                html += f"<tr><td style='border-bottom:1px solid #ddd;'>{r['영역']}</td><td style='text-align:center; color:#E91E63;'>{r['점수']:.2f}</td></tr>"
            html += "</table></div>"
            st.markdown(html, unsafe_allow_html=True)

        # 2. 정성 분석 영역 (AI)
        st.markdown("---")
        st.subheader("2. AI 주관식 분석")
        
        if st.button("🚀 분석 실행 (보안망 우회 시도)"):
            with st.spinner("AI 서버와 통신 중..."):
                # 데이터가 너무 크면 방화벽에서 걸리므로 최소화
                all_text = ""
                open_cols = [c for c in df.columns if '?' in c or '무엇' in c]
                for q in open_cols[-3:]: # 마지막 3개 질문만 분석
                    answers = df_valid[q].dropna()[:5] # 답변 5개씩만 샘플링
                    all_text += f"\n질문: {q}\n" + "\n".join([f"- {a}" for a in answers])
                
                res_text = get_ai_analysis(f"다음 설문을 요약해줘: {all_text}")
                
                if "🚨" in res_text:
                    st.error(res_text)
                    st.info("💡 계속 실패한다면 현재 PC의 인터넷을 휴대폰 '핫스팟(테더링)'으로 연결해서 시도해 보세요.")
                else:
                    st.success("✅ 분석 완료!")
                    st.markdown(res_text)

    except Exception as e:
        st.error(f"오류: {e}")