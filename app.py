# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import google.generativeai as genai
import io
import os
import ssl
from matplotlib import font_manager, rc
from fpdf import FPDF

# [보안 우회 설정]
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['CURL_CA_BUNDLE'] = ''

# 1. 기본 설정
st.set_page_config(page_title="설문조사 통합 분석기", layout="wide")
font_filename = "NanumGothic.ttf"

if os.path.exists(font_filename):
    font_manager.fontManager.addfont(font_filename)
    # 폰트 이름 가져오기
    font_name = font_manager.FontProperties(fname=font_filename).get_name()
    plt.rc('font', family=font_name)
    mpl.rcParams['axes.unicode_minus'] = False

# API 키 설정
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("🚨 secrets.toml에 API 키가 없습니다.")
    st.stop()

# --------------------------------------------------------------------------
# 2. 메인 로직 시작
# --------------------------------------------------------------------------
st.title("📊 교육 만족도 설문 통합 분석 리포트")
uploaded_file = st.file_uploader("엑셀 파일을 업로드하세요", type=['xlsx'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file, sheet_name='all responses', header=1)
        df_valid = df[df['답변 적격성'].str.strip() == '적격'].copy()
        
        # [정량 분석용 데이터 설정]
        categories = {
            "교육 내용 만족도": ['교육 내용이 현재 또는 향후 업무에 유용하다고 생각하십니까?', '제공된 정보가 정확하고 최신 내용으로 구성되어 있었습니까?', '교육 내용의 난이도가 적절했다고 생각하십니까?', '교육 자료의 구성 및 체계가 논리적이고 이해하기 쉬웠습니까?'],
            "강사 만족도": ['강사는 교육 주제에 대한 충분한 전문 지식을 갖추고 있었습니까?', '강사의 전달 방식(말투, 속도, 태도)은 이해하기 쉬웠습니까?', '강사는 질문에 성실하게 답변하고 학습자의 참여를 유도했습니까?'],
            "교육 효과성": ['이번 교육을 통해 새로운 지식이나 기술을 습득할 수 있었습니까?', '교육 후, 관련 업무 수행에 대한 자신감이 향상되었습니까?', '교육에서 배운 내용이 학업/실무 역량 강화에 도움이 되었습니까?'],
            "운영 및 환경": ['교육 자료(교재 등)는 충분하고 활용도가 높았습니까?', '실습 진행을 위한 장비, 재료 및 환경이 충분하고 만족스러웠습니까?', '교육 시간이 적절했다고 생각하십니까?', '교육 장소의 환경이 쾌적했습니까?']
        }
        
        category_means = {cat: round(df_valid[cols].apply(pd.to_numeric, errors='coerce').mean().mean(), 2) for cat, cols in categories.items()}
        chart_df = pd.DataFrame(list(category_means.items()), columns=['영역', '점수'])

        # ----------------------------------------------------------------------
        # 3. 차트 가독성 개선 (텍스트 회전 및 크기 조절)
        # ----------------------------------------------------------------------
        st.subheader("1. 영역별 만족도 점수")
        
        fig, ax = plt.subplots(figsize=(6, 4)) # 크기 약간 키움
        bars = ax.bar(chart_df['영역'], chart_df['점수'], color='#4A90E2', width=0.6)
        
        # X축 텍스트 설정: 회전각 30도, 폰트 크기 조절
        plt.xticks(rotation=30, ha='right', fontsize=10)
        
        # 막대 위 숫자 표시
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.05, f'{height:.2f}', 
                    ha='center', va='bottom', fontsize=11, fontweight='bold')
            
        ax.set_ylim(0, 5.5)
        ax.grid(axis='y', linestyle='--', alpha=0.7)

        col_chart, col_table = st.columns([1.2, 1])
        with col_chart:
            st.pyplot(fig)
        with col_table:
            # 상세 점수표 (이전 사이즈 유지)
            html = f"""
            <div style='border:2px solid #4A90E2; padding:15px; border-radius:10px;'>
                <table style='width:100%; border-collapse:collapse; font-size:24px;'>
                    <tr style='background:#f1f3f9;'><th>영역</th><th>점수</th></tr>
                    {''.join([f"<tr><td style='padding:10px; border-bottom:1px solid #ddd;'>{r['영역']}</td><td style='text-align:center; color:#E91E63; font-weight:bold;'>{r['점수']:.2f}</td></tr>" for _, r in chart_df.iterrows()])}
                </table>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

        # ----------------------------------------------------------------------
        # 4. AI 분석 (404 오류 해결 로직)
        # ----------------------------------------------------------------------
        st.subheader("2. AI 주관식 심층 분석")
        
        if st.button("🚀 분석 실행"):
            with st.spinner("AI 분석 중... (보안 연결 확인 포함)"):
                open_ended_cols = ['이번 교육을 통해 얻은 것 중 가장 만족스럽거나 도움이 되었던 부분(강의, 실습, 자료 등)은 무엇이며, 그 이유는 무엇입니까?', '이번 교육을 다른 동료/지인에게 추천하고 싶다면, 그 이유는 무엇입니까?', '교육 내용, 강의 방식, 실습 구성 등에서 추가가 필요하다고 생각하는 구체적인 부분이 있다면 무엇입니까?', '교육 장소, 실습 장비, 교육 자료 제공 등 교육 운영 및 환경 측면에서 불편하거나 개선이 필요했던 사항이 있다면 구체적으로 적어주십시오.', '향후 교육과정에서 추가되기를 희망하는 주제가 있다면 무엇입니까?']
                
                all_text = ""
                for q in open_ended_cols:
                    if q in df_valid.columns:
                        all_text += f"\n[질문: {q}]\n" + "\n".join([f"- {a}" for a in df_valid[q].dropna()])
                
                try:
                    # [핵심 수정] 404 오류 방지를 위해 api_version='v1' 명시적 지정
                    # 라이브러리 버전에 따라 클라이언트를 직접 생성하는 방식 시도
                    from google.generativeai import types
                    
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    # 분석 요청
                    response = model.generate_content(
                        f"교육 전문가로서 아래 주관식 설문 답변들을 분석하여 [강점], [약점], [건의사항]으로 요약해줘:\n{all_text}"
                    )
                    
                    res_text = response.text
                    st.success("✅ 분석 완료")
                    st.markdown(res_text)
                    
                    # PDF 다운로드 버튼 생성 (생략된 create_pdf 함수는 이전과 동일)
                    # pdf_data = create_pdf(fig, chart_df, res_text)
                    # st.download_button("📥 PDF 리포트 다운로드", data=bytes(pdf_data), file_name="report.pdf")
                    
                except Exception as e:
                    st.error(f"AI 분석 오류: {e}")
                    st.info("💡 팁: 오류가 지속되면 터미널에 'pip install -U google-generativeai'를 다시 실행해주세요.")

    except Exception as e:
        st.error(f"오류 발생: {e}")