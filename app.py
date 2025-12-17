import streamlit as st
import pandas as pd
import google.generativeai as genai
import pdfplumber
import pypdf
import io

# ==========================================================================
# 🔐 [설정] API 키
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
st.set_page_config(page_title="설문 결과 분석기", page_icon="", layout="wide")
st.title("설문조사 결과 자동 분석기(모아폼 최적화)")
st.markdown("모아폼 **'all responses'** 데이터를 올리면 자동으로 처리합니다.")

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
# 3. AI 분석 엔진
# --------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def run_ai_analysis(prompt):
    try:
        model_name = 'gemini-1.5-flash'
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
# 4. 엑셀 점수 계산 로직 (인덱스 보정 완료)
# --------------------------------------------------------------------------
def clean_moaform_data(df):
    """
    모아폼 데이터 정제: 응답자ID(첫번째 열)가 없는 행 제거
    """
    if len(df) > 0:
        # 첫 번째 컬럼(응답자ID)이 NaN이거나 비어있으면 제거 (메타데이터 행 삭제)
        df = df.dropna(subset=[df.columns[0]])
        # 혹시 '응답자ID'라는 글자가 들어간 헤더 반복 행이 있다면 제거
        df = df[pd.to_numeric(df.iloc[:, 0], errors='coerce').notnull()]
    return df

def calculate_metrics(df):
    # 전처리
    df = clean_moaform_data(df)
    
    if len(df) == 0: return None
    if len(df.columns) < 27: return None # 최소 열 개수 확인
    
    try:
        # [수정된 매핑: 8번 열이 비어있어서 1칸씩 밀림]
        # 교육 내용: 9~12열 (4개)
        # 강사진: 13~15열 (3개)
        # 성과: 16~18열 (3개)
        # 운영 환경: 19~22열 (4개)
        
        scores = {
            "교육 내용 및 구성": pd.to_numeric(df.iloc[:, 9:13].stack(), errors='coerce').mean(),
            "강사진 만족도": pd.to_numeric(df.iloc[:, 13:16].stack(), errors='coerce').mean(),
            "교육 성과": pd.to_numeric(df.iloc[:, 16:19].stack(), errors='coerce').mean(),
            "교육 환경 및 운영": pd.to_numeric(df.iloc[:, 19:23].stack(), errors='coerce').mean()
        }
        total = pd.Series(scores.values()).mean()
        
        # [수정된 주관식 매핑]
        # 23: 만족 (가장 만족스럽거나...)
        # 24: 추천 이유
        # 25: 개선 필요 사항
        # 26: 희망 주제
        # 27: 운영 불편 사항
        
        t_good = pd.concat([df.iloc[:, 23], df.iloc[:, 24]]).dropna().astype(str).tolist()
        t_bad = pd.concat([df.iloc[:, 25], df.iloc[:, 27]]).dropna().astype(str).tolist()
        t_hope = df.iloc[:, 26].dropna().astype(str).tolist()
        
        return scores, total, t_good, t_bad, t_hope, len(df)
    except Exception:
        return None

# --------------------------------------------------------------------------
# 5. 메인 UI 구성
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("📂 설정 및 실행")
    uploaded_file = st.file_uploader("파일 업로드", type=['xlsx', 'xls', 'csv', 'html', 'pdf'])
    
    st.markdown("---")
    # [설정] 모아폼 헤더 위치: 1 (두 번째 줄)
    header_row = st.number_input("데이터 시작 행 (Header)", value=1, help="모아폼은 보통 '1'입니다.")
    
    if st.button("🔄 설정 적용 및 재분석", type="primary"):
        st.cache_data.clear()

if uploaded_file:
    type_tag, content = get_file_content(uploaded_file)
    
    final_df = None
    pdf_text = None
    status_msg = st.empty()

    try:
        if type_tag == "EXCEL_FILE":
            sheet_names = content.sheet_names
            # 'all responses' 우선 선택
            default_idx = 0
            for i, name in enumerate(sheet_names):
                if "all response" in name.lower():
                    default_idx = i
                    break
            
            if len(sheet_names) > 1:
                st.sidebar.markdown("---")
                selected_sheet = st.sidebar.selectbox("📑 시트 선택", sheet_names, index=default_idx)
                status_msg.info(f"⏳ 엑셀 시트: '{selected_sheet}' 데이터 분석 중...")
                final_df = content.parse(selected_sheet, header=header_row)
            else:
                status_msg.info(f"⏳ 엑셀 시트: '{sheet_names[0]}' 데이터 분석 중...")
                final_df = content.parse(sheet_names[0], header=header_row)

        elif type_tag == "HTML_LIST":
            status_msg.info("⏳ HTML 변환 중...")
            final_df = content[0]
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
            status_msg.info("⏳ PDF 텍스트 추출 중...")
            pdf_text = content

    except Exception as e:
        status_msg.error(f"❌ 읽기 오류: {e}")
        final_df = None

    if final_df is not None:
        result = calculate_metrics(final_df)
        
        if result is None:
            status_msg.error("❌ 데이터 형식이 맞지 않습니다.")
            st.warning("⚠️ 'all responses' 시트인지, 주관식 열이 포함되어 있는지 확인해주세요.")
            st.dataframe(final_df.head(3))
        else:
            scores, total, t_good, t_bad, t_hope, count = result
            
            score_summary = f"   - 전체 평균 만족도: {round(total, 2)}점\n   - 참여 인원: {count}명\n   - 세부 점수:\n"
            for k, v in scores.items():
                val = round(v, 2) if pd.notnull(v) else 0
                score_summary += f"     · {k}: {val}점\n"

            with st.spinner("AI가 작성하고 있습니다..."):
                prompt = f"""
                교육 결과 보고서 전문가로서 아래 주관식 데이터를 분석해줘.
                데이터가 없거나 부족하면 '특이사항 없음'으로 처리해.
                
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
                    
                    status_msg.empty()
                    st.success("✅ 분석 완료!")
                    st.text_area("📋 최종 보고서", value=final_report, height=1000)
                else:
                    status_msg.warning("API 키가 없습니다.")

    elif pdf_text:
        # PDF 로직 (기존 유지)
        with st.spinner("📄PDF를 분석 중입니다..."):
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
                
                status_msg.empty()
                st.success("✅ PDF 분석 완료!")
                st.text_area("📋 최종 보고서", value=final_report, height=1000)
            else:
                status_msg.warning("API 키가 없습니다.")