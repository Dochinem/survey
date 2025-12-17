import streamlit as st
import pandas as pd
import google.generativeai as genai
import io

# ==========================================================================
# 🔐 [보안 설정] Streamlit Secrets에서 키 가져오기
# ==========================================================================
# 배포 후에는 Streamlit Cloud 대시보드의 'Secrets' 란에 키를 등록해야 합니다.
# 로컬에서 테스트할 때는 .streamlit/secrets.toml 파일을 만들어야 합니다.
try:
    MY_API_KEY = st.secrets["GEMINI_API_KEY"]
except FileNotFoundError:
    # 로컬에서 secrets 파일 없이 돌릴 때를 위한 임시 방편 (배포 전 테스트용)
    MY_API_KEY = st.text_input("API 키를 입력하세요 (로컬 테스트용)", type="password")

if MY_API_KEY:
    genai.configure(api_key=MY_API_KEY)

# --------------------------------------------------------------------------
# 1. 페이지 설정
# --------------------------------------------------------------------------
st.set_page_config(page_title="설문 결과 분석기", page_icon="📊", layout="wide")
st.title("📊 설문조사 결과 통합 분석기 (Cloud Ver.)")

# --------------------------------------------------------------------------
# 2. 초강력 데이터 로더 (HTML/CSV/Excel 모두 지원)
# --------------------------------------------------------------------------
def load_data_super_robust(uploaded_file, header_row):
    """
    Fake Excel(HTML)까지 읽어내는 최종병기 로더
    """
    # 1. 진짜 엑셀(.xlsx) 시도
    try:
        df = pd.read_excel(uploaded_file, header=header_row)
        return df
    except Exception:
        pass

    uploaded_file.seek(0)
    
    # 2. HTML (가짜 엑셀) 시도 - 이게 질문자님 파일일 확률 높음!
    try:
        # read_html은 리스트를 반환하므로 첫 번째 표([0])를 가져옴
        dfs = pd.read_html(uploaded_file, header=header_row)
        if dfs:
            return dfs[0]
    except Exception:
        pass

    uploaded_file.seek(0)

    # 3. CSV (UTF-8) 시도
    try:
        df = pd.read_csv(uploaded_file, header=header_row, encoding='utf-8')
        return df
    except Exception:
        pass

    uploaded_file.seek(0)

    # 4. CSV (EUC-KR) 시도
    try:
        df = pd.read_csv(uploaded_file, header=header_row, encoding='cp949')
        return df
    except Exception:
        pass

    return None

# --------------------------------------------------------------------------
# 3. 분석 로직 (고정 양식)
# --------------------------------------------------------------------------
def process_survey_data(df):
    # 정량 평가
    col_content = df.iloc[:, 6:10]      # G~J
    col_instructor = df.iloc[:, 10:13]  # K~M
    col_outcome = df.iloc[:, 13:16]     # N~P
    col_env = df.iloc[:, 16:20]         # Q~T

    scores = {
        "교육 내용 및 구성": pd.to_numeric(col_content.stack(), errors='coerce').mean(),
        "강사진 만족도": pd.to_numeric(col_instructor.stack(), errors='coerce').mean(),
        "교육 성과": pd.to_numeric(col_outcome.stack(), errors='coerce').mean(),
        "교육 환경 및 운영": pd.to_numeric(col_env.stack(), errors='coerce').mean()
    }
    total_score = pd.Series(scores.values()).mean()

    # 정성 평가
    text_good = pd.concat([df.iloc[:, 20], df.iloc[:, 21]]).dropna().astype(str).tolist()
    text_bad = pd.concat([df.iloc[:, 22], df.iloc[:, 24]]).dropna().astype(str).tolist()
    text_hope = df.iloc[:, 23].dropna().astype(str).tolist()

    return scores, total_score, text_good, text_bad, text_hope

# --------------------------------------------------------------------------
# 4. 메인 화면
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("📂 파일 업로드")
    uploaded_file = st.file_uploader("설문 파일 (형식 무관)", type=['xlsx', 'xls', 'csv', 'html'])
    header_row = st.number_input("데이터 시작 행 (보통 5)", value=5)

if uploaded_file:
    df = load_data_super_robust(uploaded_file, header_row)

    if df is None:
        st.error("❌ 파일을 읽을 수 없습니다. (HTML, CSV, Excel 모두 실패)")
    elif len(df.columns) < 25:
        st.error(f"❌ 열 개수 부족 ({len(df.columns)}개). G~Y열이 필요합니다.")
        st.warning(f"읽힌 컬럼: {list(df.columns)}")
    else:
        st.success(f"✅ 데이터 로드 성공! ({len(df)}건)")
        
        scores, total_score, txt_good, txt_bad, txt_hope = process_survey_data(df)

        col1, col2 = st.columns([1, 1])
        with col1:
            st.subheader("📊 정량 평가")
            score_str = ""
            for k, v in scores.items():
                val = round(v, 2)
                st.write(f"- {k}: **{val}점**")
                score_str += f"   - {k}: {val}점\n"
            st.metric("종합 평균", f"{round(total_score, 2)}점")

        with col2:
            st.subheader("📝 보고서 양식")
            default_template = """
[교육 운영 결과 보고]

1. 정량적 평가 (총 {참여인원}명)
   - 전체 평균 만족도: {전체평균}점
   - 세부 영역별 점수:
{세부점수}

2. 정성적 평가 (주관식 AI 분석)
   □ 주요 강점 (Best)
{좋았던점_요약}

   □ 개선 요청 (Needs)
{개선점_요약}

   □ 향후 희망 교육 주제
{희망주제_요약}

3. 종합 제언 (Action Plan)
{종합제언}
"""
            template = st.text_area("템플릿 수정", value=default_template, height=350)

        st.divider()
        if st.button("🚀 AI 분석 시작", type="primary"):
            if not MY_API_KEY:
                st.error("API 키가 설정되지 않았습니다.")
            else:
                with st.spinner("AI 분석 중..."):
                    try:
                        limit = 15000
                        prompt = f"""
                        교육 보고서 전문가로서 분석해줘.
                        [데이터]
                        1. 좋았던 점: {str(txt_good)[:limit]}
                        2. 개선할 점: {str(txt_bad)[:limit]}
                        3. 희망 주제: {str(txt_hope)[:limit]}
                        
                        [지침]
                        말투: 개조식(~함). 
                        좋았던점/개선할점/종합제언 각각 3가지 요약.
                        
                        [구분자]
                        ---GOOD---
                        ---BAD---
                        ---HOPE---
                        ---PLAN---
                        """
                        
                        model = genai.GenerativeModel('gemini-1.5-flash')
                        res = model.generate_content(prompt).text
                        
                        r_good, r_bad, r_hope, r_plan = "", "", "", ""
                        parts = res.split("---")
                        for p in parts:
                            if p.startswith("GOOD"): r_good = p.replace("GOOD", "").strip()
                            elif p.startswith("BAD"): r_bad = p.replace("BAD", "").strip()
                            elif p.startswith("HOPE"): r_hope = p.replace("HOPE", "").strip()
                            elif p.startswith("PLAN"): r_plan = p.replace("PLAN", "").strip()
                            
                        final = template.format(
                            참여인원=len(df), 전체평균=round(total_score, 2), 세부점수=score_str,
                            좋았던점_요약=r_good, 개선점_요약=r_bad, 희망주제_요약=r_hope, 종합제언=r_plan
                        )
                        st.subheader("✅ 최종 결과물")
                        st.text_area("결과 복사하기", value=final, height=600)
                    except Exception as e:
                        st.error(f"오류: {e}")

elif not uploaded_file:
    st.info("👈 파일을 업로드해주세요.")