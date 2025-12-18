import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
from fpdf import FPDF
import os

# -----------------------------------------------------------------------------
# 1. 설문 구조 및 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="교육 결과 분석 리포트")

# 객관식 질문 (점수화)
category_config = {
    "교육 내용 및 구성": [
        "교육 내용이 현재 또는 향후 업무에 유용하다고 생각하십니까?",
        "제공된 정보가 정확하고 최신 내용으로 구성되어 있었습니까?",
        "교육 내용의 난이도가 적절했다고 생각하십니까?",
        "교육 자료의 구성 및 체계가 논리적이고 이해하기 쉬웠습니까?"
    ],
    "강사진 만족도": [
        "강사는 교육 주제에 대한 충분한 전문 지식을 갖추고 있었습니까?",
        "강사의 전달 방식(말투, 속도, 태도)은 이해하기 쉬웠습니까?",
        "강사는 질문에 성실하게 답변하고 학습자의 참여를 유도했습니까?"
    ],
    "교육 성과 및 효과": [
        "이번 교육을 통해 새로운 지식이나 기술을 습득할 수 있었습니까?",
        "교육 후, 관련 업무 수행에 대한 자신감이 향상되었습니까?",
        "교육에서 배운 내용이 학업/실무 역량 강화에 도움이 되었습니까?"
    ],
    "교육 운영 및 시설/환경": [
        "교육 자료(교재 등)는 충분하고 활용도가 높았습니까?",
        "실습 진행을 위한 장비, 재료 및 환경이 충분하고 만족스러웠습니까?",
        "교육 시간은 적절했다고 생각하십니까?",
        "교육 장소의 환경이 쾌적했습니까?"
    ]
}

# 주관식 질문 (서술형)
essay_questions = [
    "이번 교육을 통해 얻은 것 중 가장 만족스럽거나 도움이 되었던 부분(강의, 실습, 자료 등)은 무엇이며, 그 이유는 무엇입니까?",
    "이번 교육을 다른 동료/지인에게 추천하고 싶다면, 그 이유는 무엇입니까?",
    "교육 내용, 강의 방식, 실습 구성 등에서 추가가 필요하다고 생각하는 구체적인 부분이 있다면 무엇입니까?",
    "교육 장소, 실습 장비, 교육 자료 제공 등 교육 운영 및 환경 측면에서 불편하거나 개선이 필요했던 사항이 있다면 구체적으로 적어주십시오.",
    "향후 교육과정에 추가되기를 희망하는 주제가 있다면 무엇입니까?"
]

# -----------------------------------------------------------------------------
# 2. 기능 함수 정의 (AI 요약 & PDF)
# -----------------------------------------------------------------------------

def analyze_with_ai(api_key, text_data):
    """AI를 사용하여 서술형 응답을 요약합니다."""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        
        prompt = f"""
        당신은 교육 만족도 분석 전문가입니다. 아래는 수강생들의 서술형 피드백입니다.
        이 내용들을 분석하여 다음 3가지를 정리해주세요:
        1. 긍정적 피드백 요약 (핵심 강점)
        2. 개선 필요 사항 요약 (주요 불만)
        3. 향후 교육을 위한 제언
        
        [수강생 피드백 데이터]
        {text_data}
        """
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 분석 중 오류 발생: {str(e)}"

def create_pdf(report_data, ai_summary):
    """결과 리포트 PDF를 생성합니다."""
    pdf = FPDF()
    pdf.add_page()
    
    # 한글 폰트 설정 (같은 폴더에 폰트 파일이 있어야 함)
    font_path = 'NanumGothic.ttf'
    
    if os.path.exists(font_path):
        pdf.add_font('NanumGothic', '', font_path, uni=True)
        pdf.set_font('NanumGothic', '', 12)
    else:
        pdf.set_font('Arial', '', 12)
        pdf.cell(200, 10, txt="Warning: Korean font not found.", ln=True)

    pdf.cell(200, 10, txt="[ 교육 만족도 결과 보고서 ]", ln=True, align='C')
    pdf.ln(10)
    
    # 1. 정량적 통계
    pdf.cell(200, 10, txt=f"총 참여 인원: {report_data['count']}명", ln=True)
    pdf.cell(200, 10, txt=f"종합 만족도: {report_data['total_avg']:.2f}점", ln=True)
    pdf.ln(10)
    
    pdf.cell(200, 10, txt="< 카테고리별 평균 점수 >", ln=True)
    for cat, score in report_data['cat_scores'].items():
        pdf.cell(200, 10, txt=f"- {cat}: {score:.2f}점", ln=True)
    
    pdf.ln(10)
    
    # 2. 요약 내용
    if ai_summary:
        pdf.cell(200, 10, txt="<서술형 응답>", ln=True)
        pdf.multi_cell(0, 8, txt=ai_summary)

    return pdf.output(dest='S').encode('latin-1')

# -----------------------------------------------------------------------------
# 3. 사이드바 (설정)
# -----------------------------------------------------------------------------
st.sidebar.title("⚙️ 설정")
uploaded_file = st.sidebar.file_uploader("엑셀 파일 업로드", type=['xlsx'])

# [수정됨] Secrets에서 API Key 가져오기
try:
    # secrets.toml 파일에 GEMINI_API_KEY = "sk-..." 형식으로 저장되어 있어야 함
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = None
    st.sidebar.error("Secrets에서 'GEMINI_API_KEY'를 찾을 수 없습니다.")

# -----------------------------------------------------------------------------
# 4. 메인 화면 로직
# -----------------------------------------------------------------------------
st.title("📊 교육 결과 대시보드")

if uploaded_file is not None:
    # 데이터 로드
    df = pd.read_excel(uploaded_file, sheet_name='all responses')
    
    # -- [통계 계산] --
    total_count = len(df)
    all_numeric_cols = [q for cats in category_config.values() for q in cats if q in df.columns]
    
    if all_numeric_cols:
        total_avg = df[all_numeric_cols].mean(numeric_only=True).mean()
    else:
        total_avg = 0

    # 상단 요약 배너
    st.markdown(f"""
        <div style='background-color:#e8f4f8; padding: 20px; border-radius: 10px; margin-bottom: 20px; display:flex; justify-content:space-around;'>
            <div><span style='font-size:1.1em; color:gray;'>총 참여</span><br><span style='font-size:1.8em; font-weight:bold;'>{total_count}명</span></div>
            <div><span style='font-size:1.1em; color:gray;'>종합 점수</span><br><span style='font-size:1.8em; font-weight:bold; color:#0068c9;'>{total_avg:.2f}점</span></div>
        </div>
        """, unsafe_allow_html=True)

    # -- [객관식 상세 (가로 배치)] --
    cols = st.columns(len(category_config))
    cat_scores = {}

    for i, (cat_name, questions) in enumerate(category_config.items()):
        with cols[i]:
            st.subheader(cat_name)
            st.markdown("---")
            scores = []
            for q in questions:
                if q in df.columns:
                    val = df[q].mean()
                    scores.append(val)
                    # 질문(작게) - 점수(크게)
                    c1, c2 = st.columns([4, 1])
                    c1.caption(q)
                    c2.markdown(f"**{val:.1f}**")
            
            # 카테고리 평균
            if scores:
                avg = np.mean(scores)
                cat_scores[cat_name] = avg
                st.markdown("---")
                st.metric(f"{cat_name} 평균", f"{avg:.2f}")

    st.markdown("---")

    # -- [AI 분석 및 서술형 데이터] --
    st.header("📝 서술형 응답")

    all_essay_text = ""
    for q in essay_questions:
        if q in df.columns:
            valid_texts = df[q].dropna().astype(str).tolist()
            if valid_texts:
                all_essay_text += f"\n[질문: {q}]\n" + "\n".join(valid_texts)

    # AI 분석 버튼
    ai_result_text = ""
    if api_key:
        if st.button("서술형 응답 요약 & 분석"):
            with st.spinner("응답을 분석 중입니다..."):
                if all_essay_text:
                    ai_result_text = analyze_with_ai(api_key, all_essay_text)
                    st.success("분석 완료!")
                    st.markdown(f"<div style='background-color:#f0f2f6; padding:15px; border-radius:5px;'>{ai_result_text}</div>", unsafe_allow_html=True)
                else:
                    st.warning("분석할 서술형 응답 데이터가 없습니다.")
    else:
        st.warning("API Key가 설정되지 않았습니다. (.streamlit/secrets.toml 확인 필요)")

    # 서술형 테이블 보여주기 (빈 값도 포함)
    st.subheader("응답 원본 데이터")
    for q in essay_questions:
        with st.expander(f"Q. {q}"):
            if q in df.columns:
                # NaN을 빈 문자열로 대체하여 빈칸으로 표시
                view_df = df[[q]].fillna("")
                st.dataframe(view_df, use_container_width=True)
            else:
                st.write("데이터 없음")

    # -- [PDF 다운로드] --
    st.markdown("---")
    st.subheader("💾 보고서 다운로드")
    
    c_down1, c_down2 = st.columns(2)
    
    # 1. 시각화 보고서 (브라우저 인쇄)
    with c_down1:
        st.info("💡 **차트가 포함된 시각화 보고서**는 브라우저의 인쇄 기능을 사용하세요.")
        st.markdown("""
            <button onclick="window.print()" style="background-color:#FF4B4B; color:white; border:none; padding:10px 20px; border-radius:5px; cursor:pointer;">
                🖨️ 현재 화면 인쇄 (PDF 저장)
            </button>
            """, unsafe_allow_html=True)

    # 2. 텍스트 보고서 (AI 요약 포함)
    with c_down2:
        if os.path.exists('NanumGothic.ttf'):
            if st.button("📄 분석 결과 PDF 다운로드"):
                report_data = {
                    'count': total_count,
                    'total_avg': total_avg,
                    'cat_scores': cat_scores
                }
                pdf_bytes = create_pdf(report_data, ai_result_text if ai_result_text else "AI 분석 내용 없음")
                
                st.download_button(
                    label="📥 PDF 파일 받기",
                    data=pdf_bytes,
                    file_name="교육결과보고서.pdf",
                    mime="application/pdf"
                )
        else:
            st.warning("⚠️ PDF 생성: 'NanumGothic.ttf' 폰트 파일이 필요합니다.")

else:
    st.info("왼쪽 사이드바에서 엑셀 파일을 업로드해주세요.")