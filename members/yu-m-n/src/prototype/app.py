"""
app.py — Streamlit 대시보드 (로컬 개발 / 빠른 프로토타입용)
프로덕션 서빙은 FastAPI(api/index.py)를 사용하세요.
"""

import os
import tempfile

import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

# core.py와 PDF 파서·키 완전 통일
from core import (
    extract_scores_from_pdf,
    recommend_jobs_for_user_profile,
    T_SCORE_KEY,
    RIASEC_LABELS,
    load_jobs_dataframe,
)

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ---------------------------------------------------------
# 데이터 로드
# ---------------------------------------------------------
@st.cache_data(show_spinner="DB에서 직무 데이터를 불러오는 중...")
def load_data() -> pd.DataFrame:
    try:
        return load_jobs_dataframe()
    except Exception as e:
        st.error(f"❌ 직무 데이터 로드 실패: {e}")
        return pd.DataFrame()


# ---------------------------------------------------------
# AI 로드맵
# ---------------------------------------------------------
def run_ai_roadmap(job_row: pd.Series, user_major_status: str) -> None:
    job_name = job_row.get("JK중분류") or job_row.get("중분류", "")
    job_info = job_row.get("통합_직무정의") or job_row.get("직무정의", "")

    if not OPENAI_API_KEY:
        st.error(".env 파일에 OPENAI_API_KEY가 설정되지 않았습니다.")
        return

    client = OpenAI(api_key=OPENAI_API_KEY)
    sys_role = "현실적인 커리어 코치입니다. 학점은행제나 내일배움카드 등을 활용하여 현실적인 조언을 해주세요."
    user_context = f"- 직무명: {job_name}\n- 직무 정의: {job_info}\n- 전공 여부: {user_major_status}"
    out_inst = "1단계(직무 친해지기), 2단계(실무 기초/행정), 3단계(실전/포트폴리오)로 나누어 각각 결과물과 Tip을 포함해 마크다운으로 작성하세요. 전체 분량 700~900자."

    with st.spinner(f"AI가 '{job_name}' 맞춤형 로드맵을 생성하고 있습니다..."):
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": f"[System Role]\n{sys_role}\n\n[User Context]\n{user_context}\n\n[Output Instructions]\n{out_inst}"},
                    {"role": "user", "content": "나를 위한 직무 전환 및 취업 로드맵을 작성해줘."},
                ],
                temperature=0.7,
            )
            st.markdown("---")
            st.markdown(f"## 🗺️ {job_name} 맞춤형 커리어 로드맵")
            st.markdown(response.choices[0].message.content)
            st.session_state.auto_generate = False
        except Exception as e:
            st.error(f"API 호출 중 오류 발생: {e}")


# ---------------------------------------------------------
# 메인
# ---------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="노비 JOB 아라", page_icon="🚀", layout="centered")
    st.title("노비 JOB 아라 대시보드")
    st.subheader("초개인화된 직무 전환 및 취업 로드맵 제안")

    defaults = {
        "step": 1,
        "user_scores": None,
        "recommendations": None,
        "selected_job": None,
        "user_major": None,
        "auto_generate": False,
    }
    for key, val in defaults.items():
        st.session_state.setdefault(key, val)

    df = load_data()

    with st.sidebar:
        st.header("⚙️ 설정")
        if st.button("처음으로 돌아가기"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # ── Phase 1: PDF 업로드 ──
    if st.session_state.step == 1:
        st.markdown("### Phase 1: 고용24 적성진단(L형) 결과 업로드")
        uploaded_file = st.file_uploader("PDF 파일을 업로드해주세요", type=["pdf"])

        if uploaded_file is not None:
            with st.spinner("PDF 분석 중..."):
                try:
                    # core.py는 파일 경로를 받으므로 임시 파일 사용
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(uploaded_file.read())
                        tmp_path = tmp.name

                    scores = extract_scores_from_pdf(tmp_path)
                    os.unlink(tmp_path)

                    result_df, _ = recommend_jobs_for_user_profile(scores, top_n=10)
                    st.session_state.user_scores = scores
                    st.session_state.recommendations = result_df
                    st.success("분석 완료!")
                    st.session_state.step = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")

    # ── Phase 2: 직무 선택 ──
    elif st.session_state.step == 2:
        st.markdown("### Phase 2: 직무 선택 및 정보 입력")

        scores = st.session_state.user_scores
        if scores:
            with st.expander("📊 내 흥미 유형 점수 보기"):
                cols = st.columns(6)
                for i, label in enumerate(RIASEC_LABELS):
                    cols[i].metric(label, scores[label][T_SCORE_KEY])

        recom_df = st.session_state.recommendations
        options = [
            f"{i+1}. {row['JK중분류']}  (전공필수: {'O' if row['전공필수'] == 'O' else 'X'}) — 유사도 {row['최종유사도']:.1%}"
            for i, (_, row) in enumerate(recom_df.iterrows())
        ]

        selected_option = st.radio("추천 직무 Top 10", options)
        selected_idx = int(selected_option.split(".")[0]) - 1
        selected_row = recom_df.iloc[selected_idx]

        st.markdown("#### 직무 정의")
        job_info = selected_row.get("통합_직무정의") or selected_row.get("직무정의", "")
        st.info(job_info or "직무 정보가 없습니다.")

        st.markdown("#### 전공 여부")
        user_major = st.radio("해당 직무와 관련된 전공을 하셨나요?", ["비전공", "관련 전공"])

        col1, col2 = st.columns(2)
        with col1:
            if st.button("⬅️ 이전 단계"):
                st.session_state.step = 1
                st.rerun()
        with col2:
            if st.button("다음 단계로 (AI 로드맵 생성) ➡️"):
                st.session_state.selected_job = selected_row
                st.session_state.user_major = user_major
                st.session_state.step = 3
                st.rerun()

    # ── Phase 3: AI 로드맵 ──
    elif st.session_state.step == 3:
        st.markdown("### Phase 3: 맞춤형 AI 커리어 코칭")

        job = st.session_state.selected_job
        job_name = job.get("JK중분류") or job.get("중분류", "")

        st.write(f"**선택된 직무:** {job_name}")
        st.write(f"**전공필수 여부:** {job['전공필수']}")
        st.write(f"**나의 전공 상태:** {st.session_state.user_major}")

        if st.button("⬅️ 다시 선택하기"):
            st.session_state.step = 2
            st.rerun()

        if st.button("🚀 AI 로드맵 생성하기") or st.session_state.auto_generate:
            run_ai_roadmap(job, st.session_state.user_major)

        st.markdown("---")
        st.markdown("### 🔍 다른 직무가 궁금하신가요?")
        search_query = st.text_input("직무명을 검색해보세요")

        if search_query and not df.empty:
            mask = (
                df["JK중분류"].str.contains(search_query, na=False, case=False)
                | df["매핑 O*NET 직업명"].str.contains(search_query, na=False, case=False)
            )
            search_results = df[mask].head(5)

            if not search_results.empty:
                st.write(f"**'{search_query}'** 검색 결과:")
                for _, s_row in search_results.iterrows():
                    with st.expander(f"📌 {s_row['JK중분류']}"):
                        info = s_row.get("통합_직무정의") or s_row.get("직무정의", "")
                        st.write(f"**직무 정의:** {info}")
                        st.write(f"**전공 필수 여부:** {s_row['전공필수']}")
                        if st.button("이 직무로 즉시 로드맵 생성", key=f"search_btn_{s_row.name}"):
                            st.session_state.selected_job = s_row
                            st.session_state.auto_generate = True
                            st.rerun()
            else:
                st.warning("검색 결과가 없습니다. 다른 키워드로 검색해보세요.")


if __name__ == "__main__":
    main()