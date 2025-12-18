# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import google.generativeai as genai
import platform
import io
import os
from matplotlib import font_manager, rc
from fpdf import FPDF

# --------------------------------------------------------------------------
# 1. 기본 설정 (폰트 & API 키)
# --------------------------------------------------------------------------
st.set_page_config(page_title="설문조사 통합 분석기", layout="wide")

# [중요] 한글 폰트 경로 설정 (윈도우 기준)
font_path = "C:/Windows/Fonts/malgun.ttf"

# 폰트 파일이 진짜 있는지 확인
if not os.path.exists(font_path):
    st.error(f"🚨 폰트 파일을 찾을 수 없습니다: {font_path}")
    st.info("다른 폰트 경로를 확인하거나, 폰트 파일이 있는지 확인해주세요.")
    st.stop()
else:
    # 1) Matplotlib(차트) 한글 설정
    font_name = font_manager.FontProperties(fname=font_path).get_name()
    rc('font', family=font_name)
    mpl.rcParams['axes.unicode_minus'] = False # 마이너스 깨짐 방지

# API 키 설정
if "GEMINI_API_KEY" in st.secrets:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
else:
    st.error("🚨 secrets.toml 파일에서 'GEMINI_API_KEY'를 찾지 못했습니다.")
    st.stop()

# --------------------------------------------------------------------------
# 2. PDF 생성 함수 (fpdf2 + 한글 폰트 강제 적용)
# --------------------------------------------------------------------------
def create_pdf_fpdf2(fig, chart_df, ai_text):
    pdf = FPDF()
    pdf.add_page()
    
    # 2) PDF 한글 폰트 등록 (필수!)
    # 'Malgun'이라는 이름으로 폰트 파일을 등록합니다.
    pdf.add_font("Malgun", fname=font_path)
    
    # 제목
    pdf.set_font("Malgun", size=20)
    pdf.cell(0, 15, "교육 만족도 분석 리포트", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(10)

    # 점수표
    pdf.set_font("Malgun", size=14)
    pdf.cell(0, 10, "[영역별 만족도 점수]", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Malgun", size=12)
    for index, row in chart_df.iterrows():
        text = f"- {row['영역']}: {row['점수']:.2f}점"
        pdf.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(10)

    # 차트 이미지
    img_buffer = io.BytesIO()
    fig.savefig(img_buffer, format='png', dpi=100, bbox_inches='tight')
    img_buffer.seek(0)
    pdf.image(img_buffer, w=150) 
    pdf.ln(10)

    # AI 분석 결과
    pdf.set_font("Malgun", size=14)
    pdf.cell(0, 10, "[AI 주관식 분석 결과]", new_x="LMARGIN", new_y="NEXT")
    
    pdf.set_font("Malgun", size=11)
    # AI 텍스트 줄바꿈 처리
    pdf.multi_cell(0, 7, ai_text)
    
    return pdf.output(dest='S')

# --------------------------------------------------------------------------
# 3. 분석 문항 정의
# --------------------------------------------------------------------------
categories = {
    "교육 내용 만족도": [
        '교육 내용이 현재 또는 향후 업무에 유용하다고 생각하십니까?',
        '제공된 정보가 정확하고 최신 내용으로 구성되어 있었습니까?',
        '교육 내용의 난이도가 적절했다고 생각하십니까?',
        '교육 자료의 구성 및 체계가 논리적이고 이해하기 쉬웠습니까?'
    ],
    "강사 만족도": [
        '강사는 교육 주제에 대한 충분한 전문 지식을 갖추고 있었습니까?',
        '강사의 전달 방식(말투, 속도, 태도)은 이해하기 쉬웠습니까?',
        '강사는 질문에 성실하게 답변하고 학습자의 참여를 유도했습니까?'
    ],
    "교육 효과성": [
        '이번 교육을 통해 새로운 지식이나 기술을 습득할 수 있었습니까?',
        '교육 후, 관련 업무 수행에 대한 자신감이 향상되었습니까?',
        '교육에서 배운 내용이 학업/실무 역량 강화에 도움이 되었습니까?'
    ],
    "운영 및 환경": [
        '교육 자료(교재 등)는 충분하고 활용도가 높았습니까?',
        '실습 진행을 위한 장비, 재료 및 환경이 충분하고 만족스러웠습니까?',
        '교육 시간이 적절했다고 생각하십니까?',
        '교육 장소의 환경이 쾌적했습니까?'
    ]
}

open_ended_cols = [
    '이번 교육을 통해 얻은 것 중 가장 만족스럽거나 도움이 되었던 부분(강의, 실습, 자료 등)은 무엇이며, 그 이유는 무엇입니까?',
    '이번 교육을 다른 동료/지인에게 추천하고 싶다면, 그 이유는 무엇입니까?',
    '교육 내용, 강의 방식, 실습 구성 등에서 추가가 필요하다고 생각하는 구체적인 부분이 있다면 무엇입니까?',
    '교육 장소, 실습 장비, 교육 자료 제공 등 교육 운영 및 환경 측면에서 불편하거나 개선이 필요했던 사항이 있다면 구체적으로 적어주십시오.',
    '향후 교육과정에서 추가되기를 희망하는 주제가 있다면 무엇입니까?'
]

# --------------------------------------------------------------------------
# 4. 화면 구성
# --------------------------------------------------------------------------
st.title("📊 교육 만족도 설문 통합 분석 리포트")
st.markdown("---")

st.markdown("### 📂 엑셀 파일 업로드 (Raw_data.xlsx)")
uploaded_file = st.file_uploader("파일 선택", type=['xlsx'], label_visibility="collapsed")

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file, sheet_name='all response', header=1)

        if '답변 적격성' not in df.columns:
            st.error("🚨 '답변 적격성' 컬럼이 없습니다.")
            st.stop()

        df_valid = df[df['답변 적격성'].str.strip() == '적격'].copy()
        valid_cnt = len(df_valid)

        st.info(f"✅ **분석 대상(적격) 응답자:** 총 {valid_cnt}명")
        st.markdown("---")

        # ----------------------------------------------------------------------
        # 정량 분석
        # ----------------------------------------------------------------------
        st.subheader("1️⃣ 영역별 만족도 점수 (5점 만점)")

        all_score_cols = [col for cat in categories.values() for col in cat]
        df_valid[all_score_cols] = df_valid[all_score_cols].apply(pd.to_numeric, errors='coerce')

        category_means = {}
        for cat_name, cols in categories.items():
            avg_score = df_valid[cols].mean().mean()
            category_means[cat_name] = round(avg_score, 2)

        chart_df = pd.DataFrame(list(category_means.items()), columns=['영역', '점수'])
        
        # 차트 그리기
        fig, ax = plt.subplots(figsize=(4, 2.5))
        bars = ax.bar(chart_df['영역'], chart_df['점수'], color='#4A90E2', width=0.5)
        
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2.0, height, f'{height:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')
            
        ax.set_ylim(0, 5.5)
        ax.set_ylabel("점수", fontsize=8)
        ax.tick_params(axis='both', labelsize=8)
        ax.grid(axis='y', linestyle='--', alpha=0.5)
        
        col_chart, col_data = st.columns([1, 1.2]) 
        with col_chart:
            st.pyplot(fig)
        with col_data:
            st.write("#### 상세 점수표")
            st.dataframe(chart_df.style.format({"점수": "{:.2f}"}), use_container_width=True, hide_index=True)

        st.markdown("---")

        # ----------------------------------------------------------------------
        # 정성 분석 (AI)
        # ----------------------------------------------------------------------
        st.subheader("2️⃣ 주관식 응답 심층 분석")
        
        if st.button("🚀 AI 분석 및 리포트 생성"):
            with st.spinner("AI가 분석 중입니다..."):
                full_text = ""
                for q in open_ended_cols:
                    if q in df_valid.columns:
                        answers = df_valid[q].dropna().tolist()
                        full_text += f"\n[질문: {q}]\n"
                        for a in answers:
                            full_text += f"- {a}\n"
                
                ai_result_text = "분석된 내용 없음"
                if full_text:
                    prompt = f"""
                    교육 전문가로서 아래 '적격' 응답자들의 주관식 답변을 분석해주세요.
                    
                    형식:
                    1. 🌟 [핵심 강점]: 만족한 점 3가지
                    2. 🔧 [개선 필요사항]: 개선 필요한 점 3가지
                    3. 💡 [희망 교육 주제]: 요청된 주제들
                    4. 📝 [종합 의견]: 한 줄 총평

                    --- 데이터 ---
                    {full_text}
                    """
                    try:
                        # 모델명 수정 (안정적인 버전)
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        response = model.generate_content(prompt)
                        ai_result_text = response.text
                        st.success("분석 완료!")
                        st.markdown(ai_result_text)
                    except Exception as e:
                        st.error(f"AI 분석 오류: {e}")
                        ai_result_text = f"AI 오류: {e}"

            # PDF 다운로드
            st.markdown("---")
            with st.spinner("PDF 생성 중..."):
                try:
                    pdf_data = create_pdf_fpdf2(fig, chart_df, ai_result_text)
                    st.download_button(
                        label="📥 PDF 리포트 다운로드",
                        data=bytes(pdf_data),
                        file_name="교육만족도_결과보고서.pdf",
                        mime="application/pdf"
                    )
                except Exception as e:
                    st.error(f"PDF 생성 오류: {e}")

    except Exception as e:
        st.error(f"오류 발생: {e}")