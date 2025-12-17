import streamlit as st
import pandas as pd
import google.generativeai as genai
import pdfplumber
import pypdf # 강력한 PDF 리더 추가
import io

# ==========================================================================
# 🔐 [설정] Streamlit Secrets 또는 로컬 키 입력
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
st.set_page_config(page_title="설문 결과 통합 분석기", page_icon="📈", layout="wide")
st.title("📈 설문조사 결과 분석기")
st.markdown("다운로드 받은 파일을 업로드하세요.(xlsx 가 제일 정확합니다.)")

# --------------------------------------------------------------------------
# 2. 모델 자동 찾기
# --------------------------------------------------------------------------
def get_gemini_model_name():
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                if 'gemini' in m.name: return m.name
    except: pass
    return 'gemini-1.5-flash'

# --------------------------------------------------------------------------
# 3. 초강력 데이터 로더 (PDF 2중 엔진 적용)
# --------------------------------------------------------------------------
def extract_text_from_pdf(file):
    text = ""
    
    # [전략 1] pypdf 사용 (호환성 좋음)
    try:
        reader = pypdf.PdfReader(file)
        for page in reader.pages:
            t = page.extract_text()
            if t: text += t + "\n"
    except Exception as e:
        print(f"pypdf 실패: {e}")

    # [전략 2] 텍스트가 너무 적으면 pdfplumber로 재시도
    if len(text) < 50: 
        try:
            file.seek(0) # 파일 포인터 초기화
            with pdfplumber.open(file) as pdf:
                text = "" # 리셋
                for page in pdf.pages:
                    extract = page.extract_text()
                    if extract: text += extract + "\n"
        except Exception as e:
            print(f"pdfplumber 실패: {e}")
            
    return text

def load_data_ultimate(uploaded_file, header_row):
    filename = uploaded_file.name.lower()
    
    # [Case 1] PDF 파일
    if filename.endswith('.pdf'):
        extracted_text = extract_text_from_pdf(uploaded_file)
        if len(extracted_text.strip()) < 10:
            return "PDF_FAIL", None # 텍스트 추출 실패 (이미지일 확률 높음)
        return "PDF", extracted_text
    
    # [Case 2] 엑셀/CSV/HTML 파일
    try:
        df = pd.read_excel(uploaded_file, header=header_row)
        return "DF", df
    except: pass
    
    uploaded_file.seek(0)
    try:
        dfs = pd.read_html(uploaded_file, header=header_row)
        if dfs: return "DF", dfs[0]
    except: pass
    
    uploaded_file.seek(0)
    try:
        df = pd.read_csv(uploaded_file, header=header_row, encoding='utf-8')
        return "DF", df
    except: pass
    
    uploaded_file.seek(0)
    try:
        df = pd.read_csv(uploaded_file, header=header_row, encoding='cp949')
        return "DF", df
    except: pass

    return None, None

# --------------------------------------------------------------------------
# 4. 엑셀 분석 로직
# --------------------------------------------------------------------------
def analyze_dataframe(df):
    if len(df.columns) < 25: return None, None, None, None, None
    scores = {
        "교육 내용": pd.to_numeric(df.iloc[:, 6:10].stack(), errors='coerce').mean(),
        "강사진": pd.to_numeric(df.iloc[:, 10:13].stack(), errors='coerce').mean(),
        "성과": pd.to_numeric(df.iloc[:, 13:16].stack(), errors='coerce').mean(),
        "운영": pd.to_numeric(df.iloc[:, 16:20].stack(), errors='coerce').mean()
    }
    total_score = pd.Series(scores.values()).mean()
    txt_good = pd.concat([df.iloc[:, 20], df.iloc[:, 21]]).dropna().astype(str).tolist()
    txt_bad = pd.concat([df.iloc[:, 22], df.iloc[:, 24]]).dropna().astype(str).tolist()
    txt_hope = df.iloc[:, 23].dropna().astype(str).tolist()
    return scores, total_score, txt_good, txt_bad, txt_hope

# --------------------------------------------------------------------------
# 5. 메인 UI
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("📂 파일 업로드")
    uploaded_file = st.file_uploader("파일", type=['xlsx', 'xls', 'csv', 'html', 'htm', 'pdf'])
    header_row = st.number_input("데이터 시작 행 (보통 5, 안되면 0)", value=5)

if uploaded_file:
    file_type, data = load_data_ultimate(uploaded_file, header_row)

    # [PDF 분석]
    if file_type == "PDF":
        pdf_text = data
        st.info("📄 PDF 텍스트 추출 성공! AI 분석을 준비합니다.")
        
        # [디버깅용] 실제로 읽힌 텍스트가 있는지 확인
        with st.expander("🔍 PDF에서 읽어온 내용 확인하기 (클릭)"):
            st.text(pdf_text[:1000] + "\n...(생략)...")

        col1, col2 = st.columns(2)
        with col1:
            st.caption("PDF 내용 (AI 입력값)")
            st.text_area("내용", pdf_text[:800]+"...", height=800)
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
            template = st.text_area("양식 수정", value=pdf_template, height=800)

        if st.button("🚀 PDF 분석 시작", type="primary"):
            with st.spinner("AI가 PDF를 읽는 중입니다..."):
                try:
                    target_model = get_gemini_model_name()
                    prompt = f"""
                    교육 결과 보고서 전문가로서 아래 PDF 텍스트를 분석해줘.
                    
                    [PDF 내용]
                    {pdf_text[:30000]}
                    
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
                    model = genai.GenerativeModel(target_model)
                    res = model.generate_content(prompt).text
                    
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
                    st.text_area("결과 복사하기", value=final, height=1000)
                except Exception as e:
                    st.error(f"AI 오류: {e}")
    
    # [PDF 실패 - 이미지 스캔본일 경우]
    elif file_type == "PDF_FAIL":
        st.error("❌ PDF를 읽을 수 없습니다.")
        st.warning("이 PDF는 텍스트가 아닌 '이미지(스캔본)'로 되어 있는 것 같습니다.")
        st.info("해결책: 엑셀 파일로 다운로드 받아서 업로드하거나, 텍스트 복사가 가능한 PDF로 변환해주세요.")

    # [엑셀 분석]
    elif file_type == "DF":
        df = data
        scores, total, t_good, t_bad, t_hope = analyze_dataframe(df)
        
        if scores is None:
            st.error("❌ 데이터를 읽었으나 형식이 맞지 않습니다.")
            st.warning(f"읽어온 데이터 컬럼({len(df.columns)}개): {list(df.columns)}")
            st.info("좌측 사이드바의 '데이터 시작 행'을 0이나 1로 바꿔보세요.")
        else:
            st.success(f"✅ 데이터 로드 성공! ({len(df)}명)")
            col1, col2 = st.columns(2)
            with col1:
                st.write("📊 **영역별 점수**")
                for k, v in scores.items():
                    val = round(v, 2) if pd.notnull(v) else 0
                    st.write(f"- {k}: {val}점")
            with col2:
                st.metric("종합 만족도", f"{round(total, 2)}점")
            
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
            template = st.text_area("보고서 양식", value=xls_template, height=800)
            
            if st.button("🚀 AI 분석 시작", type="primary"):
                with st.spinner("AI 분석 중..."):
                    try:
                        target_model = get_gemini_model_name()
                        prompt = f"""
                        주관식 데이터 분석해줘.
                        좋았던점: {str(t_good)[:10000]}
                        개선점: {str(t_bad)[:10000]}
                        희망주제: {str(t_hope)[:10000]}
                        
                        [구분자] ---GOOD---, ---BAD---, ---HOPE---, ---PLAN---
                        """
                        model = genai.GenerativeModel(target_model)
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
                        st.text_area("결과 복사하기", value=final, height=1000)
                    except Exception as e:
                        st.error(f"오류: {e}")

    else:
        st.error("파일을 읽을 수 없습니다.")