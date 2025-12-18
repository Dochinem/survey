import streamlit as st
import pandas as pd
import numpy as np
import google.generativeai as genai
from fpdf import FPDF
import os

# -----------------------------------------------------------------------------
# 1. 기본 설정 및 질문 정의
# -----------------------------------------------------------------------------
st.set_page_config(layout="wide", page_title="교육 결과 분석")

# [중요] 엑셀의 질문과 띄어쓰기 하나라도 다르면 인식을 못합니다.
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

essay_questions = [
    "이번 교육을 통해 얻은 것 중 가장 만족스럽거나 도움이 되었던 부분(강의, 실습, 자료 등)은 무엇이며, 그 이유는 무엇입니까?",
    "이번 교육을 다른 동료/지인에게 추천하고 싶다면, 그 이유는 무엇입니까?",
    "교육 내용, 강의 방식, 실습 구성 등에서 추가가 필요하다고 생각하는 구체적인 부분이 있다면 무엇입니까?",
    "교육 장소, 실습 장비, 교육 자료 제공 등 교육 운영 및 환경 측면에서 불편하거나 개선이 필요했던 사항이 있다면 구체적으로 적어주십시오.",
    "향후 교육과정에 추가되기를 희망하는 주제가 있다면 무엇입니까?"
]

# -----------------------------------------------------------------------------
# 2. 기능 함수 (AI 요약 / PDF)
# -----------------------------------------------------------------------------
def analyze_with_ai(api_key, text_data):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(f"다음 교육 설문 피드백을 요약해줘:\n{text_data}")
        return response.text
    except Exception as e:
        return f"AI 오류: {str(e)}"

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

try:
    api_key = st.secrets["GEMINI_API_KEY"]
except:
    api_key = None

uploaded_file = st.sidebar.file_uploader("엑셀 파일 업로드", type=['xlsx'])

if uploaded_file is not None:
    # 1. 데이터 읽기
    df = pd.read_excel(uploaded_file, sheet_name=0)

    # -------------------------------------------------------------------------
    # [핵심 수정 1] 컬럼명 공백 제거 (매칭률 높이기)
    # -------------------------------------------------------------------------
    # 엑셀 헤더의 앞뒤 공백을 모두 없앱니다. (" 질문 " -> "질문")
    df.columns = df.columns.astype(str).str.strip()

    # -------------------------------------------------------------------------
    # [핵심 수정 2] 유령 데이터(빈 줄) 강력 삭제
    # -------------------------------------------------------------------------
    # thresh=3: "적어도 데이터가 3개 이상 채워진 줄만 남겨라"
    # (보통 타임스탬프+ID만 있는 줄은 데이터가 2개라 삭제됩니다)
    df = df.dropna(thresh=3)
    
    # 인원수 재계산
    total_count = len(df)

    # 매칭된 컬럼 찾기
    all_targets = [q for cats in category_config.values() for q in cats]
    found_cols = [col for col in df.columns if col in all_targets]
    
    # 평균 계산
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

    # 점수가 0점이면 경고
    if total_count > 0 and total_avg == 0:
        st.error("⚠️ 여전히 점수가 0점입니다. 엑셀의 질문 이름과 코드의 질문 이름이 다릅니다.")
        st.info("👇 맨 아래 '엑셀 데이터 확인'을 열어서 컬럼 이름을 복사해 코드에 붙여넣으세요.")

    # 카테고리별 상세
    cols = st.columns(len(category_config))
    cat_scores = {}

    for i, (cat_name, questions) in enumerate(category_config.items()):
        with cols[i]:
            st.subheader(cat_name)
            st.markdown("---")
            scores = []
            for q in questions:
                # 공백 제거된 상태끼리 비교
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

    # 서술형 및 AI
    st.header("📝 서술형 응답")
    
    all_essay_text = ""
    for q in essay_questions:
        q_clean = q.strip()
        if q_clean in df.columns:
            valid_texts = df[q_clean].dropna().astype(str).tolist()
            if valid_texts:
                all_essay_text += f"\n[질문: {q}]\n" + "\n".join(valid_texts)

    ai_result_text = ""
    if api_key and st.button("🤖 AI 분석 실행"):
        if all_essay_text:
            with st.spinner("분석 중..."):
                ai_result_text = analyze_with_ai(api_key, all_essay_text)
                st.success("완료!")
                st.write(ai_result_text)
        else:
            st.warning("분석할 텍스트가 없습니다.")

    for q in essay_questions:
        q_clean = q.strip()
        with st.expander(f"Q. {q}"):
            if q_clean in df.columns:
                st.dataframe(df[[q_clean]].fillna(""), use_container_width=True)
            else:
                st.caption("데이터 없음")

    # [디버깅] 엑셀 헤더 확인
    st.markdown("---")
    with st.expander("🔍 엑셀 데이터 확인하기 (점수 0점일 때 클릭)"):
        st.write("현재 엑셀에서 인식된 컬럼명 목록입니다. 아래 이름을 복사해서 코드의 category_config를 수정하세요.")
        st.code(df.columns.tolist()) # 리스트 형태로 복사하기 쉽게 보여줌

    # PDF 다운로드
    if os.path.exists('NanumGothic.ttf') and st.button("PDF 다운로드"):
         report_data = {'count': total_count, 'total_avg': total_avg, 'cat_scores': cat_scores}
         pdf_bytes = create_pdf(report_data, ai_result_text)
         st.download_button("파일 받기", pdf_bytes, "report.pdf", "application/pdf")

else:
    st.info("왼쪽 사이드바에서 엑셀 파일을 업로드해주세요.")