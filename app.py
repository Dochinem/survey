import streamlit as st
import pandas as pd
import google.generativeai as genai
import pdfplumber
import pypdf
import io

# ==========================================================================
# 🔐 [설정] API 키 (여기에 입력하세요)
# ==========================================================================
try:
    MY_API_KEY = st.secrets["GEMINI_API_KEY"]
except FileNotFoundError:
    MY_API_KEY = "여기에_API_키를_입력하세요"

if MY_API_KEY and not MY_API_KEY.startswith("여기에"):
    genai.configure(api_key=MY_API_KEY)

# --------------------------------------------------------------------------
# 1. 페이지 설정
# --------------------------------------------------------------------------
st.set_page_config(page_title="설문 결과 통합 분석기", page_icon="⚡", layout="wide")
st.title("설문조사 결과 자동 분석기")
st.markdown("파일을 업로드 후 **시트 선택**하시면 **AI 분석**을 자동으로 수행합니다.")

# --------------------------------------------------------------------------
# 2. 데이터 로더 & 유틸리티
# --------------------------------------------------------------------------
def extract_text_from_pdf(file):
    text = ""
    try:
        reader = pypdf.PdfReader(file)
        for page in reader.pages:
            t = page.extract_text()
            if t: text += t + "\n"
    except: pass

    if len(text) < 50:
        try:
            file.seek(0)
            with pdfplumber.open(file) as pdf:
                text = ""
                for page in pdf.pages:
                    extract = page.extract_text()
                    if extract: text += extract + "\n"
        except: pass
    return text

def get_file_content(uploaded_file):
    filename = uploaded_file.name.lower()
    
    if filename.endswith('.pdf'):
        text = extract_text_from_pdf(uploaded_file)
        if len(text.strip()) < 10: return "PDF_FAIL", None
        return "PDF", text

    try:
        excel_file = pd.ExcelFile(uploaded_file)
        return "EXCEL_FILE", excel_file
    except: pass
    
    uploaded_file.seek(0)
    try:
        dfs = pd.read_html(uploaded_file)
        if dfs: return "HTML_LIST", dfs
    except: pass
    
    uploaded_file.seek(0)
    try:
        df = pd.read_csv(uploaded_file, encoding='utf-8')
        return "CSV", df
    except: pass
    
    uploaded_file.seek(0)
    try:
        df = pd.read_csv(uploaded_file, encoding='cp949')
        return "CSV", df
    except: pass

    return None, None

# --------------------------------------------------------------------------
# 3. AI 분석 엔진 (캐싱)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def run_ai_analysis(prompt):
    # 모델 자동 감지 로직 포함
    try:
        model_name = 'gemini-1.5-flash' # 기본값
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods and 'gemini' in m.name:
                model_name = m.name
                break
        model = genai.GenerativeModel(model_name)
        res = model.generate_content(prompt)
        return res.text
    except Exception as e:
        return f"AI 분석 오류: {e}"

FINAL_TEMPLATE = """
[교육 운영 결과 보고서]

1. 정량적 평가 (개요)
{정량_요약}

2. 정성적 평가 (상세 분석)
   □ 주요 강점 (만족 요인)
{좋았던점_요약}

   □ 개선 요청 사항
{개선점_요약}

   □ 향후 희망 교육 주제
{희망주제_요약}

3. 종합 제언 (Action Plan)
{종합제언}
"""

# --------------------------------------------------------------------------
# 4. 엑셀 점수 계산 로직
# --------------------------------------------------------------------------
def calculate_metrics(df):
    if len(df.columns) < 25: return None
    
    scores = {
        "교육 내용": pd.to_numeric(df.iloc[:, 6:10].stack(), errors='coerce').mean(),
        "강사진": pd.to_numeric(df.iloc[:, 10:13].stack(), errors='coerce').mean(),
        "성과": pd.to_numeric(df.iloc[:, 13:16].stack(), errors='coerce').mean(),
        "운영": pd.to_numeric(df.iloc[:, 16:20].stack(), errors='coerce').mean()
    }
    total = pd.Series(scores.values()).mean()
    
    t_good = pd.concat([df.iloc[:, 20], df.iloc[:, 21]]).dropna().astype(str).tolist()
    t_bad = pd.concat([df.iloc[:, 22], df.iloc[:, 24]]).dropna().astype(str).tolist()
    t_hope = df.iloc[:, 23].dropna().astype(str).tolist()
    
    return scores, total, t_good, t_bad, t_hope

# --------------------------------------------------------------------------
# 5. 메인 UI 구성
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("📂 설정 및 실행")
    uploaded_file = st.file_uploader("파일 업로드", type=['xlsx', 'xls', 'csv', 'html', 'pdf'])
    
    st.markdown("---")
    header_row = st.number_input("데이터 시작 행 (Header)", value=5, help="표의 제목(No, 접수일...)이 있는 행 번호")
    
    # [변경점 1] 재분석 버튼 추가
    # 스트림릿은 입력값이 바뀌면 자동 실행되지만, 명시적인 버튼을 원하실 경우 사용
    if st.button("🔄 설정 적용 및 재분석", type="primary"):
        st.cache_data.clear() # 캐시를 비워서 강제로 다시 실행하게 함

if uploaded_file:
    # 1. 파일 읽기
    type_tag, content = get_file_content(uploaded_file)
    
    final_df = None
    pdf_text = None
    
    # 상태 메시지를 표시할 빈 공간(Placeholder) 생성
    # 나중에 status_msg.empty()를 호출하면 이 공간의 내용이 사라집니다.
    status_msg = st.empty()

    # 2. 시트/테이블 선택 및 데이터 준비
    if type_tag == "EXCEL_FILE":
        sheet_names = content.sheet_names
        if len(sheet_names) > 1:
            st.sidebar.markdown("---")
            selected_sheet = st.sidebar.selectbox("📑 시트 선택", sheet_names)
            status_msg.info(f"⏳ 엑셀 시트: '{selected_sheet}' 데이터 로드 및 분석 중...")
            final_df = content.parse(selected_sheet, header=header_row)
        else:
            status_msg.info(f"⏳ 엑셀 시트: '{sheet_names[0]}' 데이터 로드 및 분석 중...")
            final_df = content.parse(sheet_names[0], header=header_row)

    elif type_tag == "HTML_LIST":
        status_msg.info("⏳ HTML(가짜 엑셀) 데이터 변환 중...")
        if len(content) > 1:
            st.sidebar.markdown("---")
            table_idx = st.sidebar.selectbox("📑 테이블 선택", range(len(content)), format_func=lambda x: f"표 {x+1}")
            final_df = content[table_idx]
        else:
            final_df = content[0]
        
        # HTML 헤더 보정
        if header_row > 0 and final_df is not None:
            try:
                new_header = final_df.iloc[header_row]
                final_df = final_df[header_row+1:]
                final_df.columns = new_header
            except: pass
                
    elif type_tag == "CSV":
        status_msg.info("⏳ CSV 데이터 분석 중...")
        final_df = pd.read_csv(uploaded_file, header=header_row)
        
    elif type_tag == "PDF":
        status_msg.info("⏳ PDF 텍스트 추출 및 AI 독해 중...")
        pdf_text = content
        
    # 3. 분석 및 결과 출력
    if final_df is not None:
        # [엑셀/CSV 분석]
        scores, total, t_good, t_bad, t_hope = calculate_metrics(final_df)
        
        if scores is None:
            status_msg.error("❌ 데이터 형식이 맞지 않습니다. (열 개수 부족)")
            st.warning("사이드바의 '데이터 시작 행'을 조절하거나, 올바른 시트를 선택했는지 확인해주세요.")
        else:
            score_summary = f"   - 전체 평균 만족도: {round(total, 2)}점\n   - 참여 인원: {len(final_df)}명\n   - 세부 점수:\n"
            for k, v in scores.items():
                val = round(v, 2) if pd.notnull(v) else 0
                score_summary += f"     · {k}: {val}점\n"

            with st.spinner("🤖 AI가 보고서를 작성하고 있습니다..."):
                prompt = f"""
                교육 결과 보고서 전문가로서 아래 주관식 데이터를 분석해줘.
                
                [데이터]
                좋았던점: {str(t_good)[:15000]}
                개선점: {str(t_bad)[:15000]}
                희망주제: {str(t_hope)[:15000]}
                
                [지침]
                1. 좋았던 점은 강사, 내용, 환경 등으로 분류하여 핵심 강점 3가지를 요약.
                2. 개선할 점은 빈도가 높은 순으로 3가지 요약.
                3. 희망 주제는 3~4개 카테고리로 묶어서 나열.
                4. 종합 제언은 개선점을 해결할 구체적 대안 2~3가지 제시.
                5. 말투는 '~함', '~임' 등의 개조식 보고서체.
                
                [구분자]
                ---GOOD--- (좋았던점)
                ---BAD--- (개선점)
                ---HOPE--- (희망주제)
                ---PLAN--- (종합제언)
                """
                
                if MY_API_KEY:
                    ai_res = run_ai_analysis(prompt)
                    
                    parsed = {"GOOD":"", "BAD":"", "HOPE":"", "PLAN":""}
                    parts = ai_res.split("---")
                    for p in parts:
                        for k in parsed.keys():
                            if p.strip().startswith(k): parsed[k] = p.replace(k, "").strip()
                    
                    final_report = FINAL_TEMPLATE.format(
                        정량_요약=score_summary,
                        좋았던점_요약=parsed["GOOD"] if parsed["GOOD"] else "(내용 없음)",
                        개선점_요약=parsed["BAD"] if parsed["BAD"] else "(내용 없음)",
                        희망주제_요약=parsed["HOPE"] if parsed["HOPE"] else "(내용 없음)",
                        종합제언=parsed["PLAN"] if parsed["PLAN"] else "(내용 없음)"
                    )
                    
                    # [변경점 2] 분석 완료 시 상태 메시지 삭제
                    status_msg.empty()
                    
                    st.success("✅ 분석 완료!")
                    st.text_area("📋 최종 보고서", value=final_report, height=1000)
                else:
                    status_msg.warning("API 키가 없습니다.")

    elif pdf_text:
        # [PDF 분석]
        with st.spinner("📄 AI가 PDF를 분석 중입니다..."):
            prompt = f"""
            교육 결과 보고서 전문가로서 아래 PDF 내용을 요약해줘.
            
            [PDF 텍스트]
            {pdf_text[:30000]}
            
            [지침]
            1. 텍스트에 포함된 수치나 통계가 있다면 '정량_요약'에 정리.
            2. 주관식 의견을 분석하여 강점/개선점/희망주제로 요약.
            3. 종합 제언 작성.
            
            [구분자]
            ---STAT--- (통계/정량)
            ---GOOD--- (강점)
            ---BAD--- (개선점)
            ---HOPE--- (희망주제)
            ---PLAN--- (제언)
            """
            
            if MY_API_KEY:
                ai_res = run_ai_analysis(prompt)
                
                parsed = {"STAT":"", "GOOD":"", "BAD":"", "HOPE":"", "PLAN":""}
                parts = ai_res.split("---")
                for p in parts:
                    for k in parsed.keys():
                        if p.strip().startswith(k): parsed[k] = p.replace(k, "").strip()
                
                final_report = FINAL_TEMPLATE.format(
                    정량_요약=parsed["STAT"],
                    좋았던점_요약=parsed["GOOD"],
                    개선점_요약=parsed["BAD"],
                    희망주제_요약=parsed["HOPE"],
                    종합제언=parsed["PLAN"]
                )
                
                # [변경점 2] 분석 완료 시 상태 메시지 삭제
                status_msg.empty()
                
                st.success("✅ PDF 분석 완료!")
                st.text_area("📋 최종 보고서", value=final_report, height=1000)
            else:
                status_msg.warning("API 키가 없습니다.")
                
    elif uploaded_file and final_df is None and pdf_text is None:
        status_msg.error("파일을 읽지 못했습니다.")

elif not uploaded_file:
    st.info("👈 왼쪽 사이드바에서 파일을 업로드해주세요.")