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

# 객관식 질문 (점수화) - 띄어쓰기 등 정확해야 함
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
# 2. 기능 함수 정의
# -----------------------------------------------------------------------------

def analyze_with_ai(api_key, text_data):
    """AI를 사용하여 서술형 응답을 요약합니다."""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"다음 교육 피드백을 분석해줘:\n{text_data}"
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"AI 분석 오류: {str(e)}"

def create_pdf(report_data, ai_summary):
    pdf = FPDF()
    pdf.add_page()
    font_path = 'NanumGothic.ttf'
    if os.path.exists(font_path):
        pdf.add_font('NanumGothic', '', font_path, uni=True)
        pdf.set_font('NanumGothic', '', 12)
    else:
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, txt="Korean font not found.", ln=True)

    pdf.cell(0, 10, txt="[ 교육 결과 보고서 ]", ln=True, align='C')
    pdf.ln(10)
    pdf.cell(0, 10, txt=f"참여 인원: {report_data['count']}명", ln=True)
    pdf.cell(0, 10, txt=f"종합 점수: {report_data['total_avg']:.2f}점", ln=True)
    pdf.ln(10)
    for cat, score in report_data['cat_scores'].items():
        pdf.cell(0, 10, txt=f"- {cat}: {score:.2f}점", ln=True)
    
    if ai_summary:
        pdf.ln(10)
        pdf.multi_cell(0, 8, txt=ai_summary)
    return pdf.output(dest='S').encode('latin-1')

# -----------------------------------------------------------------------------
# 3. 메인 로직
# -----------------------------------------------------------------------------
st.title("📊 교육 결과 대시보드")

# Secrets에서 API Key 가져오기
try:
    api_key = st.secrets["GEMINI_API_KEY"]
except:
    api_key = None

uploaded_file = st.sidebar.file_uploader("엑셀 파일 업로드", type=['xlsx'])

if uploaded_file is not None:
    # 1. 시트 이름 상관없이 첫 번째 시트 읽기
    df = pd.read_excel(uploaded_file, sheet_name=0)
    
    # [수정 1] 빈 줄(모든 값이 비어있는 행) 제거 -> 인원수 오류 해결
    df = df.dropna(how='all')
    
    # [수정 2] 컬럼명 앞뒤 공백 제거 -> 매칭 오류 완화
    df.columns = df.columns.str.strip()

    # -- [통계 계산] --
    total_count = len(df)
    
    # 실제로 매칭된 컬럼만 찾기
    found_cols = []
    for cats in category_config.values():
        for q in cats:
            if q in df.columns:
                found_cols.append(q)
    
    if found_cols:
        total_avg = df[found_cols].mean(numeric_only=True).mean()
    else:
        total_avg = 0.0

    # 상단 요약
    st.markdown(f"""
        <div style='background-color:#e8f4f8; padding: 20px; border-radius: 10px; margin-bottom: 20px; display:flex; justify-content:space-around;'>
            <div><span style='font-size:1.1em; color:gray;'>총 참여</span><br><span style='font-size:1.8em; font-weight:bold;'>{total_count}명</span></div>
            <div><span style='font-size:1.1em; color:gray;'>종합 점수</span><br><span style='font-size:1.8em; font-weight:bold; color:#0068c9;'>{total_avg:.2f}점</span></div>
        </div>
        """, unsafe_allow_html=True)

    # 매칭된 컬럼이 하나도 없으면 경고 표시
    if total_count > 0 and len(found_cols) == 0:
        st.error("⚠️ 점수가 0점으로 나옵니다. 엑셀의 질문(헤더) 이름이 코드와 일치하지 않습니다.")
        st.info("👇 화면 맨 아래 '엑셀 데이터 확인하기'를 눌러 실제 컬럼명을 확인해보세요.")

    # -- [객관식 상세] --
    cols = st.columns(len(category_config))
    cat_scores = {}

    for i, (cat_name, questions) in enumerate(category_config.items()):
        with cols[i]:
            st.subheader(cat_name)
            st.markdown("---")
            scores = []
            for q in questions:
                # 공백 제거된 상태로 비교
                if q.strip() in df.columns:
                    val = df[q.strip()].mean()
                    scores.append(val)
                    c1, c2 = st.columns([4, 1])
                    c1.caption(q)
                    c2.markdown(f"**{val:.1f}**")
            
            if scores:
                avg = np.mean(scores)
                cat_scores[cat_name] = avg
                st.markdown("---")
                st.metric(f"{cat_name} 평균", f"{avg:.2f}")

    st.markdown("---")

    # -- [서술형 및 AI] --
    st.header("📝 서술형 응답")
    
    all_essay_text = ""
    for q in essay_questions:
        q_clean = q.strip()
        if q_clean in df.columns:
            valid_texts = df[q_clean].dropna().astype(str).tolist()
            if valid_texts:
                all_essay_text += f"\n[질문: {q}]\n" + "\n".join(valid_texts)

    ai_result_text = ""
    if api_key and st.button("분석 실행"):
        if all_essay_text:
            with st.spinner("분석 중..."):
                ai_result_text = analyze_with_ai(api_key, all_essay_text)
                st.success("완료!")
                st.write(ai_result_text)
        else:
            st.warning("분석할 텍스트가 없습니다.")

    # 서술형 원본 보기
    for q in essay_questions:
        q_clean = q.strip()
        with st.expander(f"Q. {q}"):
            if q_clean in df.columns:
                st.dataframe(df[[q_clean]].fillna(""), use_container_width=True)
            else:
                st.caption("데이터 없음 (컬럼명 불일치)")

    # -- [디버깅 도구: 엑셀 헤더 확인용] --
    st.markdown("---")
    with st.expander("🔍 엑셀 데이터 확인하기 (점수가 안 나올 때 클릭)"):
        st.write("엑셀 파일이 인식한 헤더 이름 목록입니다. 코드의 질문 내용과 똑같은지 비교해보세요.")
        st.write(df.columns.tolist())
        st.write("---")
        st.write("엑셀 데이터 미리보기:")
        st.dataframe(df.head())

    # PDF 다운로드
    if os.path.exists('NanumGothic.ttf') and st.button("PDF 다운로드"):
         report_data = {'count': total_count, 'total_avg': total_avg, 'cat_scores': cat_scores}
         pdf_bytes = create_pdf(report_data, ai_result_text)
         st.download_button("파일 받기", pdf_bytes, "report.pdf", "application/pdf")

else:
    st.info("왼쪽 사이드바에서 엑셀 파일을 업로드해주세요.")