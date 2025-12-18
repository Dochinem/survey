# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib as mpl
import google.generativeai as genai
import io
import os
import ssl
from matplotlib import font_manager, rc
from fpdf import FPDF

# [보안 우회] SSL 및 네트워크 설정
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['CURL_CA_BUNDLE'] = ''

# 1. 폰트 설정
st.set_page_config(page_title="설문조사 통합 분석기", layout="wide")
font_filename = "NanumGothic.ttf"

if os.path.exists(font_filename):
    font_manager.fontManager.addfont(font_filename)
    font_name = font_manager.FontProperties(fname=font_filename).get_name()
    plt.rc('font', family=font_name)
    mpl.rcParams['axes.unicode_minus'] = False

# API 키 설정
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    st.error("🚨 GEMINI_API_KEY가 secrets.toml에 없습니다.")
    st.stop()

# [함수 추가] PDF 생성
def create_pdf(fig, chart_df, ai_text):
    pdf = FPDF()
    pdf.add_page()
    pdf.add_font("Nanum", fname=font_filename)
    pdf.set_font("Nanum", size=20)
    pdf.cell(0, 15, "교육 만족도 분석 리포트", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(10)
    pdf.set_font("Nanum", size=14)
    pdf.cell(0, 10, "[영역별 만족도 점수]", new_x="LMARGIN", new_y="NEXT")
    for _, row in chart_df.iterrows():
        pdf.cell(0, 8, f"- {row['영역']}: {row['점수']:.2f}점", new_x="LMARGIN", new_y="NEXT")
    img_buffer = io.BytesIO()
    fig.savefig(img_buffer, format='png', dpi=100)
    img_buffer.seek(0)
    pdf.image(img_buffer, w=150)
    pdf.ln(10)
    pdf.set_font("Nanum", size=11)
    pdf.multi_cell(0, 7, ai_text)
    return pdf.output(dest='S')

# 2. 메인 화면
st.title("📊 교육 만족도 설문 통합 분석 리포트")
uploaded_file = st.file_uploader("엑셀 파일(Raw_data.xlsx) 업로드", type=['xlsx'])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file, sheet_name='all responses', header=1)
        df_valid = df[df['답변 적격성'].str.strip() == '적격'].copy()
        
        # 정량 분석 데이터
        categories = {
            "교육 내용 만족도": ['교육 내용이 현재 또는 향후 업무에 유용하다고 생각하십니까?', '제공된 정보가 정확하고 최신 내용으로 구성되어 있었습니까?', '교육 내용의 난이도가 적절했다고 생각하십니까?', '교육 자료의 구성 및 체계가 논리적이고 이해하기 쉬웠습니까?'],
            "강사 만족도": ['강사는 교육 주제에 대한 충분한 전문 지식을 갖추고 있었습니까?', '강사의 전달 방식(말투, 속도, 태도)은 이해하기 쉬웠습니까?', '강사는 질문에 성실하게 답변하고 학습자의 참여를 유도했습니까?'],
            "교육 효과성": ['이번 교육을 통해 새로운 지식이나 기술을 습득할 수 있었습니까?', '교육 후, 관련 업무 수행에 대한 자신감이 향상되었습니까?', '교육에서 배운 내용이 학업/실무 역량 강화에 도움이 되었습니까?'],
            "운영 및 환경": ['교육 자료(교재 등)는 충분하고 활용도가 높았습니까?', '실습 진행을 위한 장비, 재료 및 환경이 충분하고 만족스러웠습니까?', '교육 시간이 적절했다고 생각하십니까?', '교육 장소의 환경이 쾌적했습니까?']
        }
        
        category_means = {cat: round(df_valid[cols].apply(pd.to_numeric, errors='coerce').mean().mean(), 2) for cat, cols in categories.items()}
        chart_df = pd.DataFrame(list(category_means.items()), columns=['영역', '점수'])

        # 3. 차트 및 표 시각화
        st.subheader("1. 영역별 만족도 점수")
        fig, ax = plt.subplots(figsize=(6, 4))
        bars = ax.bar(chart_df['영역'], chart_df['점수'], color='#4A90E2', width=0.6)
        plt.xticks(rotation=30, ha='right', fontsize=9) # 겹침 방지
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.05, f'{height:.2f}', ha='center', va='bottom', fontsize=10, fontweight='bold')
        ax.set_ylim(0, 5.5)

        col1, col2 = st.columns([1.2, 1])
        with col1: st.pyplot(fig)
        with col2:
            html = f"""
            <div style='border:2px solid #4A90E2; padding:15px; border-radius:10px; background:#fff;'>
                <table style='width:100%; border-collapse:collapse; font-size:24px;'>
                    <tr style='background:#f1f3f9;'><th>영역</th><th>점수</th></tr>
                    {''.join([f"<tr><td style='padding:10px; border-bottom:1px solid #ddd;'>{r['영역']}</td><td style='text-align:center; color:#E91E63; font-weight:bold;'>{r['점수']:.2f}</td></tr>" for _, r in chart_df.iterrows()])}
                </table>
            </div>
            """
            st.markdown(html, unsafe_allow_html=True)

        # 4. AI 분석 (404 오류 수정 핵심 구간)
        st.subheader("2. AI 주관식 심층 분석")
        if st.button("🚀 분석 실행"):
            with st.spinner("AI 분석 중..."):
                open_cols = ['이번 교육을 통해 얻은 것 중 가장 만족스럽거나 도움이 되었던 부분(강의, 실습, 자료 등)은 무엇이며, 그 이유는 무엇입니까?', '이번 교육을 다른 동료/지인에게 추천하고 싶다면, 그 이유는 무엇입니까?', '교육 내용, 강의 방식, 실습 구성 등에서 추가가 필요하다고 생각하는 구체적인 부분이 있다면 무엇입니까?', '교육 장소, 실습 장비, 교육 자료 제공 등 교육 운영 및 환경 측면에서 불편하거나 개선이 필요했던 사항이 있다면 구체적으로 적어주십시오.', '향후 교육과정에서 추가되기를 희망하는 주제가 있다면 무엇입니까?']
                all_text = ""
                for q in open_cols:
                    if q in df_valid.columns:
                        all_text += f"\n[질문: {q}]\n" + "\n".join([f"- {a}" for a in df_valid[q].dropna()])
                
                try:
                    # [최종 전략] 모델 경로를 명시적으로 전달
                    # gemini-1.5-flash 가 404가 날 경우를 대비해 2가지 경로 시도
                    res_text = ""
                    try:
                        # 시도 1: gemini-1.5-flash
                        model = genai.GenerativeModel(model_name='gemini-1.5-flash')
                        response = model.generate_content(f"교육 전문가로서 아래 답변을 분석해줘:\n{all_text}")
                        res_text = response.text
                    except Exception:
                        # 시도 2: gemini-pro (좀 더 구형이지만 호환성이 높은 모델)
                        model = genai.GenerativeModel(model_name='gemini-pro')
                        response = model.generate_content(f"교육 전문가로서 아래 답변을 분석해줘:\n{all_text}")
                        res_text = response.text
                    
                    st.success("✅ 분석 완료")
                    st.markdown(res_text)
                    
                    # PDF 버튼
                    pdf_data = create_pdf(fig, chart_df, res_text)
                    st.download_button("📥 PDF 리포트 다운로드", data=bytes(pdf_data), file_name="report.pdf", mime="application/pdf")
                    
                except Exception as e:
                    st.error(f"AI 분석 오류: {e}")
                    st.warning("⚠️ 지속적인 404 오류 발생 시, API Key가 유효한지 또는 결제 프로필(Free tier라도)이 등록되어 있는지 확인이 필요합니다.")

    except Exception as e:
        st.error(f"오류 발생: {e}")