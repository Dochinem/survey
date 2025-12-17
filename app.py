import streamlit as st
import pandas as pd
import google.generativeai as genai
import pdfplumber
import io

# ==========================================================================
# 🔐 [설정] Streamlit Secrets 또는 로컬 키 입력
# ==========================================================================
try:
    MY_API_KEY = st.secrets["GEMINI_API_KEY"]
except FileNotFoundError:
    # 로컬 테스트용 키 입력 (보안을 위해 본인 키를 입력하세요)
    MY_API_KEY = "여기에_API_키를_입력하세요"

if MY_API_KEY and not MY_API_KEY.startswith("여기에"):
    genai.configure(api_key=MY_API_KEY)

# --------------------------------------------------------------------------
# 1. 페이지 설정
# --------------------------------------------------------------------------
st.set_page_config(page_title="설문 결과 분석기", page_icon="📈", layout="wide")
st.title("📈 설문조사 결과 분석기")
st.markdown("다운로드 받은 **'엑셀'이나 PDF를 업로드하세요.")

# --------------------------------------------------------------------------
# 2. 초강력 데이터 로더 (핵심 기능)
# --------------------------------------------------------------------------
def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            extract = page.extract_text()
            if extract: text += extract + "\n"
    return text

def load_data_ultimate(uploaded_file, header_row):
    """
    확장자 사기(HTML), 인코딩 문제, PDF까지 모두 처리하는 로더
    """
    filename = uploaded_file.name.lower()
    
    # [Case 1] PDF 파일
    if filename.endswith('.pdf'):
        return "PDF", extract_text_from_pdf(uploaded_file)
    
    # [Case 2] 엑셀/CSV/HTML 파일
    # 파일 포인터 초기화를 위해 seek(0)를 반복 사용
    
    # 시도 1: 진짜 엑셀 (.xlsx)
    try:
        df = pd.read_excel(uploaded_file, header=header_row)
        return "DF", df
    except: pass
    
    uploaded_file.seek(0)
    
    # 시도 2: 가짜 엑셀 (HTML) - ★ 질문자님 상황 해결 코드 ★
    try:
        # HTML 표를 찾아서 리스트로 반환하므로 첫 번째([0]) 표를 가져옴
        dfs = pd.read_html(uploaded_file, header=header_row)
        if dfs: return "DF", dfs[0]
    except: pass
    
    uploaded_file.seek(0)
    
    # 시도 3: CSV (UTF-8)
    try:
        df = pd.read_csv(uploaded_file, header=header_row, encoding='utf-8')
        return "DF", df
    except: pass
    
    uploaded_file.seek(0)
    
    # 시도 4: CSV (EUC-KR / CP949 - 한글 깨짐 방지)
    try:
        df = pd.read_csv(uploaded_file, header=header_row, encoding='cp949')
        return "DF", df
    except: pass

    return None, None

# --------------------------------------------------------------------------
# 3. 엑셀 데이터 분석 로직 (점수 계산)
# --------------------------------------------------------------------------
def analyze_dataframe(df):
    # 컬럼 인덱스로 접근 (G=6 ~ Y=24)
    # 에러 방지를 위해 컬럼 수 체크
    if len(df.columns) < 25:
        return None, None, None, None, None
    
    # 정량 평가 (숫자로 변환 후 평균)
    scores = {
        "교육 내용": pd.to_numeric(df.iloc[:, 6:10].stack(), errors='coerce').mean(),
        "강사진": pd.to_numeric(df.iloc[:, 10:13].stack(), errors='coerce').mean(),
        "성과": pd.to_numeric(df.iloc[:, 13:16].stack(), errors='coerce').mean(),
        "운영": pd.to_numeric(df.iloc[:, 16:20].stack(), errors='coerce').mean()
    }
    total_score = pd.Series(scores.values()).mean()
    
    # 정성 평가 (텍스트 합치기)
    txt_good = pd.concat([df.iloc[:, 20], df.iloc[:, 21]]).dropna().astype(str).tolist()
    txt_bad = pd.concat([df.iloc[:, 22], df.iloc[:, 24]]).dropna().astype(str).tolist()
    txt_hope = df.iloc[:, 23].dropna().astype(str).tolist()
    
    return scores, total_score, txt_good, txt_bad, txt_hope

# --------------------------------------------------------------------------
# 4. 메인 UI
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("📂 파일 업로드")
    uploaded_file = st.file_uploader("파일 (형식 상관없음)", type=['xlsx', 'xls', 'csv', 'html', 'pdf'])
    
    # 헤더 위치 조정 (HTML 엑셀은 헤더가 0번일 수도, 5번일 수도 있음)
    header_row = st.number_input("데이터 시작 행 (보통 5, 안되면 0)", value=5)

if uploaded_file:
    file_type, data = load_data_ultimate(uploaded_file, header_row)

    # ----------------------------------------------------------------------
    # [모드 1] PDF 분석
    # ----------------------------------------------------------------------
    if file_type == "PDF":
        st.info("📄 PDF 파일이 감지되었습니다. 텍스트를 분석하여 요약 보고서를 작성합니다.")
        pdf_text = data
        
        col1, col2 = st.columns(2)
        with col1:
            st.caption("PDF 내용 미리보기")
            st.text_area("내용", pdf_text[:800]+"...", height=300)
        with col2:
            st.caption("보고서 템플릿")
            pdf_template = """
[교육 결과 요약 (PDF 기반)]

1. 총평 및 분위기
{총평}

2. 주요 통계 (텍스트 추출)
{통계요약}

3. 주관식 답변 분석
  - 만족 포인트:
{만족_요약}
  - 개선 요청:
{개선_요약}

4. 종합 제언
{제언}
"""
            template = st.text_area("양식 수정", value=pdf_template, height=300)

        if st.button("🚀 PDF 분석 시작", type="primary"):
            with st.spinner("AI가 PDF를 읽는 중입니다..."):
                try:
                    prompt = f"""
                    교육 결과 보고서 전문가로서 아래 PDF 텍스트를 분석해줘.
                    
                    [PDF 내용]
                    {pdf_text[:20000]}
                    
                    [요청사항]
                    1. 내용에 포함된 숫자나 통계가 있다면 '통계요약'에 정리해줘.
                    2. 주관식 의견을 분석해서 만족/개선 포인트로 요약해줘.
                    
                    [구분자]
                    ---MOOD--- (총평)
                    ---STAT--- (통계요약)
                    ---GOOD--- (만족)
                    ---BAD--- (개선)
                    ---PLAN--- (제언)
                    """
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    res = model.generate_content(prompt).text
                    
                    # 파싱
                    parsed = {"MOOD":"", "STAT":"", "GOOD":"", "BAD":"", "PLAN":""}
                    parts = res.split("---")
                    for p in parts:
                        for key in parsed.keys():
                            if p.startswith(key): parsed[key] = p.replace(key, "").strip()
                    
                    final = template.format(
                        총평=parsed["MOOD"], 통계요약=parsed["STAT"],
                        만족_요약=parsed["GOOD"], 개선_요약=parsed["BAD"], 제언=parsed["PLAN"]
                    )
                    st.subheader("✅ PDF 분석 결과")
                    st.text_area("결과 복사하기", value=final, height=500)
                    
                except Exception as e:
                    st.error(f"AI 오류: {e}")

    # ----------------------------------------------------------------------
    # [모드 2] 엑셀/CSV/HTML 분석
    # ----------------------------------------------------------------------
    elif file_type == "DF":
        df = data
        scores, total, t_good, t_bad, t_hope = analyze_dataframe(df)
        
        if scores is None:
            st.error("❌ 데이터를 읽었으나 형식이 맞지 않습니다.")
            st.warning(f"읽어온 데이터 컬럼({len(df.columns)}개): {list(df.columns)}")
            st.info("좌측 사이드바의 '데이터 시작 행'을 0이나 1로 바꿔보세요.")
        else:
            st.success(f"✅ 데이터 로드 성공! ({len(df)}명)")
            
            # 정량 결과 표시
            col1, col2 = st.columns(2)
            with col1:
                st.write("📊 **영역별 점수**")
                for k, v in scores.items():
                    st.write(f"- {k}: {round(v, 2)}점")
            with col2:
                st.metric("종합 만족도", f"{round(total, 2)}점")

            # 정성 분석 (AI)
            st.divider()
            xls_template = """
[교육 결과 보고]
1. 정량 평가 ({인원}명)
   - 종합: {종합}점
{점수상세}

2. 정성 평가
   - 강점: {강점}
   - 개선: {개선}
   - 희망주제: {희망}

3. 제언
{제언}
""" 
            template = st.text_area("보고서 양식", value=xls_template, height=300)
            
            if st.button("🚀 AI 분석 시작", type="primary"):
                with st.spinner("AI 분석 중..."):
                    try:
                        prompt = f"""
                        주관식 데이터 분석해줘.
                        좋았던점: {str(t_good)[:10000]}
                        개선점: {str(t_bad)[:10000]}
                        희망주제: {str(t_hope)[:10000]}
                        
                        [구분자] ---GOOD---, ---BAD---, ---HOPE---, ---PLAN---
                        """
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        res = model.generate_content(prompt).text
                        
                        parsed = {"GOOD":"", "BAD":"", "HOPE":"", "PLAN":""}
                        for p in res.split("---"):
                            for k in parsed.keys():
                                if p.startswith(k): parsed[k] = p.replace(k, "").strip()
                        
                        score_txt = "\n".join([f"   - {k}: {round(v,2)}점" for k,v in scores.items()])
                        
                        final = template.format(
                            인원=len(df), 종합=round(total, 2), 점수상세=score_txt,
                            강점=parsed["GOOD"], 개선=parsed["BAD"], 희망=parsed["HOPE"], 제언=parsed["PLAN"]
                        )
                        st.subheader("✅ 분석 결과")
                        st.text_area("결과 복사하기", value=final, height=500)
                    except Exception as e:
                        st.error(f"오류: {e}")

    else:
        st.error("파일을 읽을 수 없습니다.")