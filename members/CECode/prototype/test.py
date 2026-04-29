import streamlit as st
import pandas as pd
import numpy as np
import re
import io
import os
from dotenv import load_dotenv
from pypdf import PdfReader
from openai import OpenAI

# .env 파일 로드
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

st.set_page_config(page_title="노비 JOB 아라", page_icon="🚀", layout="centered")

@st.cache_data
def load_data():
    return pd.read_csv("잡코리아_Onet_NCS_통합본_전처리_전공필수추가.csv")

def extract_scores_from_pdf(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    full_text = [page.extract_text() for page in reader.pages]
    text = "\n".join(full_text)

    m = re.search(
        r"직업 흥미 유형별 점수.*?구\s*분\s*현실형\s*탐구형\s*예술형\s*사회형\s*진취형\s*관습형\s*"
        r"원\s*점\s*수\s*([0-9\s]+)\s*"
        r"표준점수\s*([0-9\s]+)", text, re.S)
    
    if not m:
        raise ValueError("PDF에서 점수 데이터를 찾을 수 없습니다. 워크넷 결과지 형식을 다시 확인해주세요.")

    raw_scores = list(map(int, m.group(1).split()))
    std_scores = list(map(int, m.group(2).split()))
    labels = ["현실형", "탐구형", "예술형", "사회형", "진취형", "관습형"]
    return {label: {"원점수": raw, "표준점수": std} for label, raw, std in zip(labels, raw_scores, std_scores)}

def recommend_jobs_for_user_profile(user_scores, df):
    label_map_t = {"현실형": "현실형(R) T", "탐구형": "탐구형(I) T", "예술형": "예술형(A) T", "사회형": "사회형(S) T", "진취형": "진취형(E) T", "관습형": "관습형(C) T"}
    label_map_raw = {"현실형": "R", "탐구형": "I", "예술형": "A", "사회형": "S", "진취형": "E", "관습형": "C"}

    user_profile = {label_map_t[label]: scores["표준점수"] for label, scores in user_scores.items()}
    user_raw_profile = {label_map_raw[label]: scores["원점수"] for label, scores in user_scores.items()}
    score_cols = list(user_profile.keys())
    user_vec = np.array([user_profile[col] for col in score_cols], dtype=float)

    user_raw_top3 = sorted(user_raw_profile.keys(), key=lambda x: (-user_raw_profile[x], ["R", "I", "A", "S", "E", "C"].index(x)))[:3]

    work_df = df.copy()
    for col in score_cols: work_df[col] = pd.to_numeric(work_df[col], errors="coerce")
    work_df = work_df.dropna(subset=score_cols).reset_index(drop=True)
    job_matrix = work_df[score_cols].to_numpy(dtype=float)

    def cosine_similarity_matrix(X, y):
        norm = np.linalg.norm(X, axis=1) * np.linalg.norm(y)
        return np.nan_to_num((X @ y) / (norm + 1e-9))

    def euclidean_distance_matrix(X, y): return np.linalg.norm(X - y, axis=1)
    def distance_to_similarity(dist): return 1 / (1 + dist)

    def parse_top3_codes(top3_value):
        if pd.isna(top3_value): return []
        extracted = [ch for ch in str(top3_value).upper() if ch in ["R", "I", "A", "S", "E", "C"]]
        seen = set()
        return [x for x in extracted if not (x in seen or seen.add(x))][:3]

    def raw_top3_bonus(job_top3, user_top3):
        if not job_top3: return 0.0
        score = 0.0
        user_weights = {user_top3[0]: 3, user_top3[1]: 2, user_top3[2]: 1} if len(user_top3) == 3 else {}
        for i, code in enumerate(job_top3):
            if code in user_weights: score += user_weights[code] * (3 - i)
        return score / 14

    cos_sim = cosine_similarity_matrix(job_matrix, user_vec)
    dist_sim = distance_to_similarity(euclidean_distance_matrix(job_matrix, user_vec))
    t_final_sim = 0.75 * cos_sim + 0.25 * dist_sim

    top3_bonus_arr = np.array([raw_top3_bonus(parse_top3_codes(row["Top3"]), user_raw_top3) for _, row in work_df.iterrows()], dtype=float)
    final_score = (0.80 * t_final_sim) + (0.20 * top3_bonus_arr)

    result = work_df.copy()
    result["최종유사도"] = final_score
    result = result.sort_values(by=["최종유사도"], ascending=False).reset_index(drop=True)
    
    return result.head(10)

def run_ai_roadmap(job_row, user_major_status):
    """AI 로드맵을 생성하고 출력하는 공통 함수"""
    job_name = job_row['JK중분류']
    is_major_required = (job_row['전공필수'] == 'O')
    is_user_major = (user_major_status == "관련 전공")
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    if is_major_required:
        if not is_user_major:
            # 🤖 [학위 필수 비전공자용] 로드맵 프롬프트
            sys_role = "당신은 특정 직무에 진입하기 위해 반드시 학위가 필요한 경우, 현실적인 진입 경로를 안내하는 커리어 코치입니다."
            user_context = f"- 선택한 직무: {job_name}\n- 전공 여부: 비전공/타전공\n- 커리어 방향: 도전\n- 현재 상태: 관련 학위 없음"
            out_inst = (
                f"1. 도입부: \"사용자님께서 선택하신 {job_name}는 학위가 필수인 직무이기에…\"로 시작\n\n"
                f"2. 3단계 실행 구조:\n"
                f"■ 1단계: 학위 취득 경로 탐색\n- 필요한 학과/전공 명확히 제시\n- 신입학/편입/대학원 등 경로 비교\n- 📌 결과물: 지원 가능한 학교 리스트 또는 목표 설정\n\n"
                f"■ 2단계: 입시 준비 및 기초 학습\n- 입시 요소 (수능, 편입, 면접 등) 설명\n- 준비 전략 제시\n- 📌 필요 역량 2~3개 + 준비 방법\n- 📌 결과물: 학습 계획표\n\n"
                f"■ 3단계: 전문 교육 및 자격 취득\n- 졸업 후 필수 자격증/면허 설명\n- 고용24 지원 제도 안내\n- 📌 결과물: 커리어 로드맵 (입학 → 졸업 → 취업 흐름)\n\n"
                f"3. 작성 규칙:\n- 왜 학위가 필요한지 쉽게 설명\n- 각 단계마다 실행 가능한 결과물 포함\n- 각 단계 끝에 \"💡 현실적 Tip\" 포함\n- 전체 분량: 700~900자"
            )
        else:
            # 🤖 [학위 필수 전공자용] 직무 도전 로드맵 프롬프트
            sys_role = (
                "당신은 특정 직무에 진입하기 위해 반드시 필요한 학위를 이미 이수(또는 졸업 예정)했지만, "
                "본격적인 취업이나 면허 취득을 앞두고 막막함을 느끼는 초보자를 위한 전문 커리어 코치입니다. "
                "학위 취득 이후 거쳐야 하는 필수 관문(국가고시, 수습 등)부터 실제 현장 진입까지의 최단 경로를 구체적으로 안내해야 합니다."
            )
            user_context = (
                f"선택한 직무: {job_name}\n"
                f"전공 여부: 필수 전공 이수 (학위 보유)\n"
                f"커리어 방향: 도전\n"
                f"현재 상태: 관련 학위는 있으나, 최종 면허 취득 전이거나 실무 경험이 없는 상태 (Junior Ready)"
            )
            out_inst = (
                f"도입부: \"사용자님께서 선택하신 {job_name}는 필수 전공 학위를 이미 이수하셨기에, 해당 직무 도전을 위해 다음과 같이 본격적인 현장 진입 준비를 하시면 좋을 것 같습니다.\"로 시작할 것.\n\n"
                f"3단계 실행 구조:\n"
                f"■ 1단계: 필수 라이선스(면허/자격) 획득 및 현장 감각 깨우기\n"
                f"- 해당 직무 진입에 필수적인 국가고시 또는 필수 면허 취득 전략 제시\n"
                f"- 반드시 필요한 국가 자격증, 면허, 시험 명칭을 구체적으로 포함\n"
                f"- 선배 실무자의 브이로그, 현직자 인터뷰를 통해 학교와 현장의 차이점 파악\n"
                f"- 실무에서 실제로 자주 마주치는 상황(야간근무, 고객 응대, 서류 작성, 현장 변수 등)까지 함께 안내\n"
                f"📌 결과물: 자격/면허 시험 합격을 위한 ‘과목별 핵심 요약 노트’ 또는 ‘스터디 플랜’\n"
                f"💡 현실적 Tip: 시험 합격만을 목표로 하지 말고, “실제로 이 일을 하게 되면 어떤 하루를 보내는가”를 함께 파악해야 중도 포기를 줄일 수 있음\n\n"
                f"■ 2단계: 필수 수습/실습 파악 및 실무 도구 점검\n"
                f"- 직무에 따라 요구되는 법정 수습 기간, 인턴십, 실무 연수 과정 등 안내\n"
                f"- 실무에서 당장 쓰이는 전문 프로그램, 장비, 행정 서식 등의 기초 파악\n"
                f"- 채용공고에서 반복적으로 등장하는 실무 역량 2~3개를 반드시 추출하여 제시\n"
                f"- 각 역량별로 고용24 심화/특화 과정, 실습, 스터디 등 현실적인 학습 방법 연결\n"
                f"📌 결과물: 실무에 투입되었을 때 당황하지 않기 위한 나만의 ‘업무 매뉴얼(체크리스트) 초안’\n"
                f"💡 현실적 Tip: 실무는 “얼마나 많이 아는가”보다 “바로 투입 가능한가”가 중요하므로, 반복되는 업무 흐름을 먼저 익히는 것이 효과적임\n\n"
                f"■ 3단계: 실전 구직 및 전문성 증명\n"
                f"- 고용24 또는 해당 직무에 특화된 채용 플랫폼 활용법 안내\n"
                f"- 단순 전공 지식을 넘어 실습/수련 경험을 녹여내는 이력서/자기소개서 작성 가이드\n"
                f"- 채용담당자가 바로 이해할 수 있는 형태의 전문성 증명 자료 제시(임상 케이스, 실습 기록, 프로젝트 리포트 등)\n"
                f"📌 결과물: 학과 시절의 실습/프로젝트 경험이 구체적으로 담긴 ‘직무기술서(또는 포트폴리오)’ 1개 제시\n"
                f"💡 현실적 Tip: “무엇을 배웠는가”보다 “실제로 어떤 문제를 해결했는가”를 보여주는 방식이 채용에서 훨씬 강하게 작용함\n\n"
                f"작성 규칙:\n"
                f"- {job_name}에 맞는 구체적인 면허/국가 자격증 명칭 반드시 포함\n"
                f"- 이론(학교)과 실무(현장)의 차이를 좁혀주는 구체적인 팁 제공\n"
                f"- 각 단계마다 반드시 실행 가능한 결과물 포함\n"
                f"- 각 단계 끝에 반드시 “💡 현실적 Tip” 포함\n"
                f"- 답변은 초보자가 바로 행동할 수 있도록 현실적이고 구체적으로 작성\n"
                f"- 전체 분량: 700~900자 내외"
            )
    else:
        # 전공 필수가 아닌 직무 (기존 로직 유지 또는 간소화)
        if not is_user_major:
            sys_role = "당신은 비전공자로 해당 분야를 처음 접하는 초보자를 위한 전문 커리어 코치입니다."
            user_context = f"- 선택한 직무: {job_name}\n- 전공 여부: 비전공\n- 커리어 방향: 도전/전향\n- 현재 상태: 완전 초보 (Day 0)"
            out_inst = f"1. 도입부: \"사용자님께서 선택하신 {job_name}에 관해서는 비전공이시기에…\"로 시작\n2. 3단계 실행 구조(친해지기/도구 맛보기/전문 교육 진입)\n3. 초보자용 결과물 제시 및 💡 현실적 Tip 포함 (600~800자)"
        else:
            sys_role = "당신은 관련 전공을 졸업했지만 실무 경험이 없는 초보자를 위한 커리어 코치입니다."
            user_context = f"- 선택한 직무: {job_name}\n- 전공 여부: 관련 전공\n- 커리어 방향: 도전/전향\n- 현재 상태: 이론 중심, 실무 경험 없음"
            out_inst = f"1. 도입부: \"사용자님께서 선택하신 {job_name}에 관해서는 관련 전공자이시기에…\"로 시작\n2. 3단계 실행 구조(이론을 실전으로/실무 도구 점검/실전 역량 증명)\n3. 전공-실무 연결 및 💡 현실적 Tip 포함 (700~900자)"

    full_prompt = f"[System Role]\n{sys_role}\n\n[User Context]\n{user_context}\n\n[Output Instructions]\n{out_inst}"
    
    with st.spinner(f"AI가 '{job_name}' 맞춤형 로드맵을 생성하고 있습니다..."):
        try:
            response = client.chat.completions.create(
                model="gpt-5-mini",
                messages=[{"role": "system", "content": full_prompt},
                          {"role": "user", "content": "나를 위한 직무 전환 및 취업 로드맵을 작성해줘."}],
            )
            st.markdown("---")
            st.markdown(f"## 🗺️ {job_name} 맞춤형 커리어 로드맵")
            st.markdown(response.choices[0].message.content)
            # 생성 후 자동 생성 플래그 해제
            st.session_state.auto_generate = False
        except Exception as e:
            st.error(f"API 호출 중 오류 발생: {e}")

def main():
    st.title(" 노비 JOB 아라")
    st.subheader("초개인화된 직무 전환 및 취업 로드맵 제안")
    
    if "step" not in st.session_state:
        st.session_state.step = 1
        st.session_state.user_scores = None
        st.session_state.recommendations = None
        st.session_state.selected_job = None
        st.session_state.user_major = None
        st.session_state.auto_generate = False
        
    df = load_data()
    
    with st.sidebar:
        st.header("⚙️ 환경 설정")
        if st.button("처음으로 돌아가기"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    if st.session_state.step == 1:
        st.markdown("### Phase 1: 고용24 적성진단(L형) 결과 업로드")
        uploaded_file = st.file_uploader("PDF 파일을 업로드해주세요", type=["pdf"])
        if uploaded_file is not None:
            with st.spinner("PDF 분석 중..."):
                try:
                    pdf_bytes = uploaded_file.read()
                    scores = extract_scores_from_pdf(pdf_bytes)
                    st.session_state.user_scores = scores
                    st.session_state.recommendations = recommend_jobs_for_user_profile(scores, df)
                    st.success("분석 완료!")
                    st.session_state.step = 2
                    st.rerun()
                except Exception as e:
                    st.error(f"오류가 발생했습니다: {e}")

    elif st.session_state.step == 2:
        st.markdown("### Phase 2: 직무 선택 및 정보 입력")
        recom_df = st.session_state.recommendations
        
        options = []
        for idx, row in recom_df.iterrows():
            req_major = "O" if row['전공필수'] == 'O' else "X"
            options.append(f"{idx+1}. {row['JK중분류']} (전공필수: {req_major}) - 유사도 {row['최종유사도']:.1%}")
            
        selected_option = st.radio("추천 직무 Top 10", options)
        selected_idx = int(selected_option.split(".")[0]) - 1
        selected_row = recom_df.iloc[selected_idx]
        
        st.markdown("#### 직무 정의")
        st.info(selected_row['통합_직무정의'])
        
        st.markdown("#### 전공 여부 선택")
        user_major = st.radio("해당 직무와 관련된 전공을 하셨나요?", ["비전공", "관련 전공"])
        
        col1, col2 = st.columns([1, 1])
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

    elif st.session_state.step == 3:
        st.markdown("### Phase 3: 맞춤형 AI 커리어 코칭")
        job = st.session_state.selected_job
        job_name = job['JK중분류']
        
        st.write(f"**현재 선택된 직무:** {job_name}")
        st.write(f"**전공필수 여부:** {job['전공필수']}")
        st.write(f"**나의 전공상태:** {st.session_state.user_major}")
        
        if st.button("⬅️ 다시 선택하기"):
            st.session_state.step = 2
            st.rerun()
            
        if not OPENAI_API_KEY:
            st.error(".env 파일에 OPENAI_API_KEY가 설정되지 않았습니다.")
            return

        # 수동 생성 버튼 또는 자동 생성 플래그 확인
        if st.button("🚀 AI 로드맵 생성하기") or st.session_state.auto_generate:
            run_ai_roadmap(job, st.session_state.user_major)

        # --- 추가 기능: 다른 직무 검색창 ---
        st.markdown("---")
        st.markdown("### 🔍 다른 직무가 궁금하신가요?")
        search_query = st.text_input("직무명을 검색하여 정보 및 로드맵을 확인해보세요")
        
        if search_query:
            search_results = df[
                df['JK중분류'].str.contains(search_query, na=False, case=False) |
                df['매핑 O*NET 직업명'].str.contains(search_query, na=False, case=False)
            ].head(5)
            
            if not search_results.empty:
                st.write(f"**'{search_query}'** 검색 결과입니다:")
                for _, s_row in search_results.iterrows():
                    with st.expander(f"📌 {s_row['JK중분류']} (상세: {s_row['매핑 O*NET 직업명']})"):
                        st.write(f"**직무 정의:** {s_row['통합_직무정의']}")
                        st.write(f"**전공 필수 여부:** {s_row['전공필수']}")
                        if st.button("이 직무로 즉시 로드맵 생성", key=f"search_btn_{s_row.name}"):
                            st.session_state.selected_job = s_row
                            st.session_state.auto_generate = True # 자동 생성 플래그 설정
                            st.rerun()
            else:
                st.warning("검색 결과가 없습니다. 다른 키워드로 검색해보세요.")

if __name__ == "__main__":
    main()
