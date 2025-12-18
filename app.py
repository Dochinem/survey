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

# [보안 우회] 방화벽 인증서 무시 설정
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['CURL_CA_BUNDLE'] = ''
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 1. 기본 설정
st.set_page_config(page_title="설문조사 통합 분석기", layout="wide")
font_filename = "NanumGothic.ttf"

if os.path.exists(font_filename):
    font_manager.fontManager.addfont(font_filename)
    plt.rc('font', family=font_manager.FontProperties(fname=font_filename).get_name())

# --------------------------------------------------------------------------
# [핵심] 404 에러를 피하기 위한 모델 자동 탐색 함수
# --------------------------------------------------------------------------
def get_ai_analysis(prompt):
    api_key = st.secrets.get("GEMINI_API_KEY")
    # 시도할 모델 우선순위 목록
    model_candidates = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
    
    for model_name in model_candidates:
        url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={api_key}"
        headers = {'Content-Type': 'application/json'}
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        
        try:
            # verify=False로 방화벽 우회
            response = requests.post(url, headers=headers, data=json.dumps(data), verify=False, timeout=30)
            if response.status_code == 200:
                return response.json()['candidates'][0]['content']['parts'][0]['text']
        except:
            continue
            
    return "🚨 모든 모델 호출에 실패했습니다. API 키 권한 또는 네트워크 상태를 확인하세요."

# --------------------------------------------------------------------------
# 2. 메인 화면 구성
# --------------------------------------------------------------------------
st.title("📊 설문 데이터 통합 분석 리포트")
uploaded_file = st.file_uploader("Raw_data.xlsx 업로드 (all responses 시트)", type=['xlsx'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file, sheet_name='all responses', header=1)
        df_valid = df[df['답변 적격성'].str.strip() == '적격'].copy()
        
        # 영역 설정 (사용자 정의 문항 기준)
        categories = {
            "교육 내용 만족도": ['교육 내용이 현재 또는 향후 업무에 유용하다고 생각하십니까?', '제공된 정보가 정확하고 최신 내용으로 구성되어 있었습니까?', '교육 내용의 난이도가 적절했다고 생각하십니까?', '교육 자료의 구성 및 체계가 논리적이고 이해하기 쉬웠습니까?'],
            "강사 만족도": ['강사는 교육 주제에 대한 충분한 전문 지식을 갖추고 있었습니까?', '강사의 전달 방식(말투, 속도, 태도)은 이해하기 쉬웠습니까?', '강사는 질문에 성실하게 답변하고 학습자의 참여를 유도했습니까?'],
            "교육 효과성": ['이번 교육을 통해 새로운 지식이나 기술을 습득할 수 있었습니까?', '교육 후, 관련 업무 수행에 대한 자신감이 향상되었습니까?', '교육에서 배운 내용이 학업/실무 역량 강화에 도움이 되었습니까?'],
            "운영 및 환경": ['교육 자료(교재 등)는 충분하고 활용도가 높았습니까?', '실습 진행을 위한 장비, 재료 및 환경이 충분하고 만족스러웠습니까?', '교육 시간이 적절했다고 생각하십니까?', '교육 장소의 환경이 쾌적했습니까?']
        }
        
        st.subheader("1. 영역별 만족도 결과")
        category_means = {cat: round(df_valid[cols].apply(pd.to_numeric, errors='coerce').mean().mean(), 2) for cat, cols in categories.items()}
        chart_df = pd.DataFrame(list(category_means.items()), columns=['영역', '점수'])

        # 차트 가독성 최적화
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(chart_df['영역'], chart_df['점수'], color='#4A90E2', width=0.5)
        plt.xticks(rotation=20, ha='right', fontsize=10)
        ax.set_ylim(0, 5.5)

        col1, col2 = st.columns([1.2, 1])
        with col1: st.pyplot(fig)
        with col2:
            # 초대형 표 (시인성 극대화)
            html = f"""
            <div style='border:2px solid #4A90E2; padding:15px; border-radius:10px; background:#fff;'>
                <table style='width:100%; border-collapse:collapse; font-size:26px;'>
                    <tr style='background:#f1f3f9;'><th>영역</th><th>점수</th></tr>
                    {''.join([f"<tr><td style='padding:10px; border-bottom:1px solid #ddd; font-weight:bold;'>{r['영역']}</td><td style='text-align:center; color:#E91E63; font-weight:bold;'>{r['점수']:.2f}</td></tr>" for _, r in chart_df.iterrows()])}
                </table>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

        st.markdown("---")
        st.subheader("2. AI 주관식 분석 결과")
        
        if st.button("🚀 AI 분석 시작 (방화벽 우회 모드)"):
            with st.spinner("AI가 데이터를 분석하고 있습니다..."):
                # 주관식 질문 열 자동 수집
                open_cols = [c for c in df.columns if '?' in c or '무엇입니까' in c]
                all_text = ""
                for q in open_cols[-5:]:
                    all_text += f"\n[질문: {q}]\n" + "\n".join([f"- {a}" for a in df_valid[q].dropna()[:10]])
                
                res_text = get_ai_analysis(f"교육 설문 분석 전문가로서 다음 답변을 요약해줘: {all_text}")
                
                if "🚨" in res_text:
                    st.error(res_text)
                else:
                    st.success("✅ 분석 성공")
                    st.markdown(res_text)

    except Exception as e:
        st.error(f"데이터 처리 오류: {e}")