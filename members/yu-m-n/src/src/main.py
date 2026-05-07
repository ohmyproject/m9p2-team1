import pandas as pd
import numpy as np
import re
import io
import os
import json
import urllib.error
import urllib.parse
import urllib.request
from uuid import UUID
from typing import Optional
from dotenv import load_dotenv
from pypdf import PdfReader
from fastapi import FastAPI, UploadFile, File, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# .env 파일 로드
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("SUPABASE_KEY")
)

JK_JOB_SELECT = (
    "id,JK_L_category,JK_M_category,top3,"
    "realistic_score,investigative_score,artistic_score,social_score,"
    "enterprising_score,conventional_score,major_required,job_information"
)
USER_ROADMAP_SELECT = "id,job_name,riasec_scores,roadmap_text,created_at"
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

app = FastAPI()

def supabase_request(path, method="GET", params=None, body=None, token=None, prefer=None):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase 환경 변수가 설정되지 않았습니다.")

    base_url = SUPABASE_URL.rstrip("/")
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode(params, safe=",().:*")

    headers = {
        "apikey": SUPABASE_KEY,
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer

    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}{query}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase 요청 실패 ({e.code}): {detail}") from e


def openai_chat_completion(messages, temperature=0.7, model="gpt-4o-mini"):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    request = urllib.request.Request(
        OPENAI_CHAT_COMPLETIONS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            detail = parsed.get("error", {}).get("message", detail)
        except json.JSONDecodeError:
            pass
        raise RuntimeError(f"OpenAI 요청 실패 ({e.code}): {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"OpenAI 연결 실패: {e.reason}") from e

    try:
        return result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError("OpenAI 응답 형식이 예상과 다릅니다.") from e


def get_bearer_token(authorization: Optional[str]):
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ValueError("Authorization 헤더 형식이 올바르지 않습니다.")
    return token.strip()


def get_authenticated_user(token):
    user = supabase_request("/auth/v1/user", token=token)
    if not user or not user.get("id"):
        raise RuntimeError("인증된 사용자 정보를 확인할 수 없습니다.")
    return user


def map_jk_job_row(row):
    return {
        "id": row.get("id"),
        "JK대분류": row.get("JK_L_category") or "",
        "JK중분류": row.get("JK_M_category") or "",
        "Top3": row.get("top3") or "",
        "현실형(R) T": row.get("realistic_score"),
        "탐구형(I) T": row.get("investigative_score"),
        "예술형(A) T": row.get("artistic_score"),
        "사회형(S) T": row.get("social_score"),
        "진취형(E) T": row.get("enterprising_score"),
        "관습형(C) T": row.get("conventional_score"),
        "전공필수": row.get("major_required") or "",
        "직무정보": row.get("job_information") or "",
    }


def load_job_dataframe():
    rows = supabase_request(
        "/rest/v1/JK_job",
        params={"select": JK_JOB_SELECT, "order": "id.asc"},
    )
    return pd.DataFrame([map_jk_job_row(row) for row in rows or []])


def save_user_roadmap(token, user_id, job_name, riasec_scores, roadmap_text):
    payload = {
        "user_id": user_id,
        "job_name": job_name,
        "riasec_scores": riasec_scores,
        "roadmap_text": roadmap_text,
    }
    return supabase_request(
        "/rest/v1/user_roadmaps",
        method="POST",
        body=payload,
        token=token,
        prefer="return=representation",
    )

# --- 핵심 로직 함수들 (기존 코드 재사용) ---
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

def recommend_jobs_for_user_profile(user_scores, df_data):
    if df_data.empty:
        return []
        
    label_map_t = {"현실형": "현실형(R) T", "탐구형": "탐구형(I) T", "예술형": "예술형(A) T", "사회형": "사회형(S) T", "진취형": "진취형(E) T", "관습형": "관습형(C) T"}
    label_map_raw = {"현실형": "R", "탐구형": "I", "예술형": "A", "사회형": "S", "진취형": "E", "관습형": "C"}

    user_profile = {label_map_t[label]: scores["표준점수"] for label, scores in user_scores.items()}
    user_raw_profile = {label_map_raw[label]: scores["원점수"] for label, scores in user_scores.items()}
    score_cols = list(user_profile.keys())
    user_vec = np.array([user_profile[col] for col in score_cols], dtype=float)

    user_raw_top3 = sorted(user_raw_profile.keys(), key=lambda x: (-user_raw_profile[x], ["R", "I", "A", "S", "E", "C"].index(x)))[:3]

    work_df = df_data.copy()
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
    
    # 상위 10개 추출 후 JSON 변환 가능한 딕셔너리로 변경
    top10 = result.head(10)
    return top10[["JK중분류", "직무정보", "전공필수", "최종유사도"]].to_dict(orient="records")

# --- API 엔드포인트 ---

class RoadmapRequest(BaseModel):
    job_name: str
    is_major_required: bool
    user_major_status: str
    riasec_scores: Optional[dict] = None

@app.get("/", response_class=HTMLResponse)
async def read_index():
    # static 폴더 내의 index.html 반환
    with open(os.path.join(BASE_DIR, "static", "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/supabase_config")
async def supabase_config():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return JSONResponse(
            content={"status": "error", "message": "Supabase 설정이 없습니다."},
            status_code=500,
        )
    return {
        "status": "success",
        "url": SUPABASE_URL,
        "publishable_key": SUPABASE_KEY,
    }

@app.post("/api/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """PDF 파일을 받아 점수를 추출하고 추천 직무를 반환하는 API"""
    try:
        pdf_bytes = await file.read()
        scores = extract_scores_from_pdf(pdf_bytes)
        jobs_df = load_job_dataframe()
        recommendations = recommend_jobs_for_user_profile(scores, jobs_df)
        
        return JSONResponse(content={
            "status": "success",
            "scores": scores,
            "recommendations": recommendations
        })
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=400)

@app.get("/api/search_job")
async def search_job(query: str):
    """직무명을 검색하여 결과를 반환하는 API"""
    jobs_df = load_job_dataframe()
    if jobs_df.empty:
        return JSONResponse(content={"status": "error", "message": "데이터베이스를 불러올 수 없습니다."}, status_code=500)
    
    name_match = jobs_df["JK중분류"].str.contains(query, na=False, case=False, regex=False)
    results = jobs_df[name_match].head(5)
    
    
    # NaN 처리를 위해 replace 사용
    results_dict = results.fillna("").to_dict(orient="records")
    return JSONResponse(content={"status": "success", "results": results_dict})

@app.get("/api/my_roadmaps")
async def my_roadmaps(authorization: Optional[str] = Header(default=None)):
    try:
        token = get_bearer_token(authorization)
        if not token:
            return JSONResponse(content={"status": "error", "message": "로그인이 필요합니다."}, status_code=401)

        user = get_authenticated_user(token)
        data = supabase_request(
            "/rest/v1/user_roadmaps",
            params={
                "select": USER_ROADMAP_SELECT,
                "user_id": f"eq.{user['id']}",
                "order": "created_at.desc",
            },
            token=token,
        )
        return {"status": "success", "data": data or []}
    except ValueError as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=401)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.delete("/api/delete_roadmap/{roadmap_id}")
async def delete_roadmap(roadmap_id: str, authorization: Optional[str] = Header(default=None)):
    try:
        token = get_bearer_token(authorization)
        if not token:
            return JSONResponse(content={"status": "error", "message": "로그인이 필요합니다."}, status_code=401)

        roadmap_uuid = str(UUID(roadmap_id))
        user = get_authenticated_user(token)
        deleted = supabase_request(
            "/rest/v1/user_roadmaps",
            method="DELETE",
            params={
                "id": f"eq.{roadmap_uuid}",
                "user_id": f"eq.{user['id']}",
            },
            token=token,
            prefer="return=representation",
        )
        if not deleted:
            return JSONResponse(content={"status": "error", "message": "삭제할 기록을 찾을 수 없습니다."}, status_code=404)
        return {"status": "success"}
    except ValueError:
        return JSONResponse(content={"status": "error", "message": "로드맵 ID가 올바르지 않습니다."}, status_code=400)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

@app.post("/api/roadmap")
async def generate_roadmap(req: RoadmapRequest, authorization: Optional[str] = Header(default=None)):
    """선택한 직무와 전공 여부를 바탕으로 AI 로드맵을 생성하는 API"""
    is_user_major = (req.user_major_status == "yes")
    try:
        token = get_bearer_token(authorization)
    except ValueError as e:
        token = None
    
    # (이하 사용자님이 작성하신 프롬프트 분기 로직과 동일하게 유지)
    if req.is_major_required:
        if not is_user_major:
            sys_role = "당신은 특정 직무에 진입하기 위해 반드시 학위가 필요한 경우, 현실적인 진입 경로를 안내하는 커리어 코치입니다."
            user_context = f"- 선택한 직무: {req.job_name}\n- 전공 여부: 비전공/타전공\n- 커리어 방향: 도전"
            out_inst = f"""
1. 3단계 실행 구조:

■ 1단계: 학위 취득 경로 탐색  
- 필요한 학과/전공 명확히 제시  
- 신입학/편입/대학원 등 경로 비교  
- 📌 결과물: 지원 가능한 학교 리스트 또는 목표 설정  

■ 2단계: 입시 준비 및 기초 학습  
- 입시 요소 (수능, 편입, 면접 등) 설명  
- 준비 전략 제시  
- 📌 필요 역량 2~3개 + 준비 방법  
- 📌 결과물: 학습 계획표  

■ 3단계: 전문 교육 및 자격 취득  
- 졸업 후 필수 자격증/면허 설명  
- 고용24 지원 제도 안내  
- 📌 결과물: 커리어 로드맵 (입학 → 졸업 → 취업 흐름)

2. 작성 규칙:
- 왜 학위가 필요한지 쉽게 설명
- 각 단계마다 실행 가능한 결과물 포함
- 각 단계 끝에 “💡 현실적 Tip” 포함
- 전체 분량: 700~900자""" # (여기에 기존 프롬프트 텍스트 삽입)
        else:
            sys_role = "당신은 특정 직무에 진입하기 위해 반드시 필요한 학위를 이미 이수했지만..."
            user_context = f"- 선택한 직무: {req.job_name}\n- 전공 여부: 필수 전공 이수"
            out_inst = f"""
1. 3단계 실행 구조:

■ 1단계: 필수 라이선스(면허/자격) 획득 및 현장 감각 깨우기

해당 직무 진입에 필수적인 국가고시 또는 필수 면허 취득 전략 제시

반드시 필요한 국가 자격증, 면허, 시험 명칭을 구체적으로 포함

선배 실무자의 브이로그, 현직자 인터뷰를 통해 학교와 현장의 차이점 파악

실무에서 실제로 자주 마주치는 상황(야간근무, 고객 응대, 서류 작성, 현장 변수 등)까지 함께 안내

📌 결과물: 자격/면허 시험 합격을 위한 ‘과목별 핵심 요약 노트’ 또는 ‘스터디 플랜’

💡 현실적 Tip:
시험 합격만을 목표로 하지 말고, “실제로 이 일을 하게 되면 어떤 하루를 보내는가”를 함께 파악해야 중도 포기를 줄일 수 있음

■ 2단계: 필수 수습/실습 파악 및 실무 도구 점검

직무에 따라 요구되는 법정 수습 기간, 인턴십, 실무 연수 과정 등 안내

실무에서 당장 쓰이는 전문 프로그램, 장비, 행정 서식 등의 기초 파악

채용공고에서 반복적으로 등장하는 실무 역량 2~3개를 반드시 추출하여 제시

각 역량별로 고용24 심화/특화 과정, 실습, 스터디 등 현실적인 학습 방법 연결

📌 결과물: 실무에 투입되었을 때 당황하지 않기 위한 나만의 ‘업무 매뉴얼(체크리스트) 초안’

💡 현실적 Tip:
실무는 “얼마나 많이 아는가”보다 “바로 투입 가능한가”가 중요하므로, 반복되는 업무 흐름을 먼저 익히는 것이 효과적임

■ 3단계: 실전 구직 및 전문성 증명

고용24 또는 해당 직무에 특화된 채용 플랫폼(예: 메디잡, 건설워커 등) 활용법 안내

단순 전공 지식을 넘어 실습/수련 경험을 녹여내는 이력서/자기소개서 작성 가이드

채용담당자가 바로 이해할 수 있는 형태의 전문성 증명 자료 제시

예:

* 임상 케이스 정리
* 실습 기록 요약
* 프로젝트 리포트
* 시공 참여 내역
* 판례 분석 보고서
* 연구/실험 정리 자료

중 해당 직무에 가장 적합한 방식으로 추천

📌 결과물: 학과 시절의 실습/프로젝트 경험이 구체적으로 담긴 ‘직무기술서(또는 포트폴리오)’ 1개 제시

💡 현실적 Tip:
“무엇을 배웠는가”보다 “실제로 어떤 문제를 해결했는가”를 보여주는 방식이 채용에서 훨씬 강하게 작용함

2. 작성 규칙:

{req.job_name}에 맞는 구체적인 면허/국가 자격증 명칭 반드시 포함

이론(학교)과 실무(현장)의 차이를 좁혀주는 구체적인 팁 제공

각 단계마다 반드시 실행 가능한 결과물 포함

각 단계 끝에 반드시 “💡 현실적 Tip” 포함

답변은 초보자가 바로 행동할 수 있도록 현실적이고 구체적으로 작성

전체 분량: 700~900자 내외"""
    else:
        if not is_user_major:
            sys_role = "당신은 비전공자로 해당 분야를 처음 접하는 초보자를 위한 전문 커리어 코치입니다."
            user_context = f"- 선택한 직무: {req.job_name}\n- 전공 여부: 비전공"
            out_inst = f"""
1. 3단계 실행 구조:

■ 1단계: 직무와 친해지기  
- 해당 직무의 실제 업무 예시(하루 일과, 결과물)를 반드시 포함  
- 유튜브, 블로그, 간단한 도구 체험 등 제안  
- 📌 결과물: 초보자가 만들 수 있는 아주 간단한 결과물 1개 제시  

■ 2단계: 도구 맛보기 및 행정 준비  
- 반드시 해당 직무에 맞는 도구/기술만 제시 (일반적인 SQL, 엑셀 반복 금지)  
- 고용24(hrd.go.kr) ‘내일배움카드’ 안내 포함  
- 📌 필요 역량 2~3개 + 각각의 학습 방법(강의/훈련) 연결  
- 📌 결과물: 간단한 실습 결과물 제시  

■ 3단계: 전문 교육 환경 진입  
- 고용24에서 검색할 키워드 구체적으로 제시  
- 관련 자격증 반드시 포함 (직무 맞춤)  
- 📌 결과물: 포트폴리오 형태 제시 (ex. 보고서, 프로젝트 등)

2. 작성 규칙:
- 초등학생도 이해할 수 있는 쉬운 표현 사용
- 각 단계 끝에 반드시 “💡 현실적 Tip” 추가
- {req.job_name}에 맞는 구체적인 예시 필수 (일반화 금지)
- ‘전향’일 경우 기존 경험을 연결하는 문장 1개 포함
- 마지막 응원 문구나 맺음말(예: "이 3단계를 따라가다보면...")은 절대 작성하지 마십시오. 오직 로드맵 본문으로만 마무리하십시오.
- 전체 분량: 600~800자 내외"""
        else:
            sys_role = "당신은 관련 전공을 졸업했지만 실무 경험이 없는 초보자를 위한 커리어 코치입니다."
            user_context = f"- 선택한 직무: {req.job_name}\n- 전공 여부: 관련 전공"
            out_inst = f"""
1. 3단계 실행 구조:

■ 1단계: 이론을 실전 언어로 변환하기  
- 전공 지식 → 실무에서 어떻게 쓰이는지 연결  
- 실무 용어 vs 학술 용어 비교  
- 📌 결과물: 기존 전공 과제 → 실무형 문서로 변환  

■ 2단계: 실무 도구 점검 및 행정 준비  
- 직무 필수 도구/소프트웨어 구체적으로 제시  
- 고용24 ‘내일배움카드’ 안내  
- 📌 필요 역량 2~3개 + 학습 방법 연결  
- 📌 결과물: 실무 툴 활용 결과물  

■ 3단계: 실전 역량 증명 및 심화  
- NCS 기반 부족 역량 점검  
- 고용24 교육 검색 키워드 제시  
- 직무 맞춤 자격증 제시  
- 📌 결과물: 취업용 포트폴리오 1개 구체적으로 제시  

2. 작성 규칙:
- 반드시 {req.job_name} 맞춤 예시 사용
- 전공 용어와 실무 용어를 연결 설명
- 각 단계마다 결과물 포함
- 각 단계 끝에 “💡 현실적 Tip” 포함
- 전체 분량: 700~900자"""

    full_prompt = f"[System Role]\n{sys_role}\n\n[User Context]\n{user_context}\n\n[Output Instructions]\n{out_inst}"
    
    try:
        roadmap_text = openai_chat_completion(
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": "나를 위한 직무 전환 및 취업 로드맵을 작성해줘."}
            ],
            temperature=0.7
        )
        if token:
            user = get_authenticated_user(token)
            save_user_roadmap(token, user["id"], req.job_name, req.riasec_scores, roadmap_text)
        return {"status": "success", "roadmap": roadmap_text}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

# 모든 API 정의 후에 정적 파일 서빙 설정
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
