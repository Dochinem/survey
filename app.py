import streamlit as st
import pandas as pd
import google.generativeai as genai
import pdfplumber
import pypdf
import io

# ==========================================================================
# 🔐 [설정] API 키 (여기에 입력하세요)
# ==========================================================================
# 로컬 테스트용 키 입력 (배포 시에는 Streamlit Secrets 사용 권장)
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
st.title("⚡ 설문조사 결과 자동 분석기")
st.markdown("파일을 업로드하면 **시트 선택**부터 **AI 분석**까지 자동으로 수행합니다.")

# --------------------------------------------------------------------------
# 2. 데이터 로더 (시트 분할 지원)
# --------------------------------------------------------------------------
def extract_text_from_pdf(file):
    text = ""
    # 1차 시도: pypdf
    try:
        reader = pypdf.PdfReader(file)
        for page in reader.pages:
            t = page.extract_text()
            if t: text += t + "\n"
    except: pass

    # 2차 시도: pdfplumber (텍스트가 적을 경우)
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
    """파일 형식을 분석하여 적절한 객체를 반환"""
    filename = uploaded_file.name.lower()
    
    # [Case 1] PDF
    if filename.endswith('.pdf'):
        text = extract_text_from_pdf(uploaded_file)
        if len(text.strip()) < 10: return "PDF_FAIL", None
        return "PDF", text

    # [Case 2] 진짜 엑셀 (시트 여러 개일 수 있음)
    try:
        excel_file = pd.ExcelFile(uploaded_file)
        return "EXCEL_FILE", excel_file
    except: pass
    
    uploaded_file.seek(0)
    
    # [Case 3] 가짜 엑셀 (HTML - 표가 여러 개일 수 있음)
    try:
        dfs = pd.read_html(uploaded_file)
        if dfs: return "HTML_LIST", dfs
    except: pass
    
    uploaded_file.seek(0)
    
    # [Case 4] CSV (UTF-8)
    try:
        df = pd.read_csv(uploaded_file, encoding='utf-8')
        return "CSV", df
    except: pass
    
    uploaded_file.seek(0)
    
    # [Case 5] CSV (CP949)
    try:
        df = pd.read_csv(uploaded_file, encoding='cp949')
        return "CSV", df
    except: pass

    return None, None

# --------------------------------------------------------------------------
# 3. AI 분석 엔진 (캐싱 적용으로 속도 최적화)
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def run_ai_analysis(prompt):
    """AI 분석 실행 (결과 캐싱)"""
    model = genai.GenerativeModel('gemini-1.5-flash') # 가성비 좋은 모델
    try:
        res = model.generate_content(prompt)
        return res.text
    except Exception as e:
        return f"AI 분석 오류: {e}"

# 보고서 템플릿 (내부 고정)
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
    
    # 정량 데이터 (G~T열)
    scores = {
        "교육 내용": pd.to_numeric(df.iloc[:, 6:10].stack(), errors='coerce').mean(),
        "강사진": pd.to_numeric(df.iloc[:, 10:13].stack(), errors='coerce').mean(),
        "성과": pd.to_numeric(df.iloc[:, 13:16].stack(), errors='coerce').mean(),
        "운영": pd.to_numeric(df.iloc[:, 16:20].stack(), errors='coerce').mean()
    }
    total = pd.Series(scores.values()).mean()
    
    # 정성 데이터 (U~Y열)
    t_good = pd.concat([df.iloc[:, 20], df.iloc[:, 21]]).dropna().astype(str).tolist()
    t_bad = pd.concat([df.iloc[:, 22], df.iloc[:, 24]]).dropna().astype(str).tolist()
    t_hope = df.iloc[:, 23].dropna().astype(str).tolist()
    
    return scores, total, t_good, t_bad, t_hope

# --------------------------------------------------------------------------
# 5. 메인 UI 구성
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("📂 파일 설정")
    uploaded_file = st.file_uploader("파일 업로드", type=['xlsx', 'xls', 'csv', 'html', 'pdf'])
    header_row = st.number_input("데이터 시작 행 (보통 5)", value=5, help="표의 헤더(제목)가 있는 행 번호")

if uploaded_file:
    # 1. 파일 읽기
    type_tag, content = get_file_content(uploaded_file)
    
    final_df = None
    pdf_text = None
    
    # 2. 시트/테이블 선택 로직 (사이드바)
    if type_tag == "EXCEL_FILE":
        sheet_names = content.sheet_names
        if len(sheet_names) > 1:
            st.sidebar.markdown("---")
            selected_sheet = st.sidebar.selectbox("📑 시트 선택", sheet_names)
            final_df = content.parse(selected_sheet, header=header_row)
            st.info(f"엑셀 시트: '{selected_sheet}' 분석 중")
        else:
            final_df = content.parse(sheet_names[0], header=header_row)

    elif type_tag == "HTML_LIST":
        if len(content) > 1:
            st.sidebar.markdown("---")
            table_idx = st.sidebar.selectbox("📑 테이블(표) 선택", range(len(content)), format_func=lambda x: f"표 {x+1}")
            final_df = content[table_idx]
            # HTML 읽을 때 헤더 처리가 안 되었을 수 있어 다시 정리
            if header_row > 0:
                new_header = final_df.iloc[header_row]
                final_df = final_df[header_row+1:]
                final_df.columns = new_header
        else:
            final_df = content[0]
            if header_row > 0:
                new_header = final_df.iloc[header_row]
                final_df = final_df[header_row+1:]
                final_df.columns = new_header
                
    elif type_tag == "CSV":
        final_df = pd.read_csv(uploaded_file, header=header_row) # Re-read with correct header for simplicity
        
    elif type_tag == "PDF":
        pdf_text = content
        
    # 3. 분석 및 결과 출력
    if final_df is not None:
        # [엑셀/CSV 분석 모드]
        scores, total, t_good, t_bad, t_hope = calculate_metrics(final_df)
        
        if scores is None:
            st.error("❌ 데이터 형식이 맞지 않습니다. (열 개수 부족)")
            st.warning("사이드바의 '데이터 시작 행'을 조절하거나, 올바른 시트를 선택했는지 확인해주세요.")
        else:
            # 정량 요약 텍스트 생성
            score_summary = f"   - 전체 평균 만족도: {round(total, 2)}점\n   - 참여 인원: {len(final_df)}명\n   - 세부 점수:\n"
            for k, v in scores.items():
                val = round(v, 2) if pd.notnull(v) else 0
                score_summary += f"     · {k}: {val}점\n"

            # AI 분석 (자동 실행)
            with st.spinner("🤖 AI가 주관식 답변을 분석하고 보고서를 작성 중입니다..."):
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
                    
                    # 결과 파싱
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
                    
                    st.success("✅ 분석 완료!")
                    st.text_area("📋 최종 보고서 (복사해서 사용하세요)", value=final_report, height=800)
                else:
                    st.warning("API 키가 없습니다. 코드에 키를 입력해주세요.")

    elif pdf_text:
        # [PDF 분석 모드]
        with st.spinner("📄 AI가 PDF 문서를 독해 중입니다..."):
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
                
                st.success("✅ PDF 분석 완료!")
                st.text_area("📋 최종 보고서 (복사해서 사용하세요)", value=final_report, height=800)
            else:
                st.warning("API 키가 없습니다.")
                
    elif uploaded_file and final_df is None and pdf_text is None:
        st.error("파일을 읽지 못했습니다.")

elif not uploaded_file:
    st.info("👈 왼쪽 사이드바에서 파일을 업로드해주세요.")