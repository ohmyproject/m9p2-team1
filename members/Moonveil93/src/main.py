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
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from pypdf import PdfReader
from fastapi import FastAPI, UploadFile, File, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# LangChain 관련 임포트
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from operator import itemgetter
from supabase import create_client, Client

# .env 파일 로드
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini").strip().strip("'\"") or "gpt-4o-mini"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or os.getenv("SUPABASE_KEY")
)

# Supabase 클라이언트 초기화 (LangChain용)
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

JK_JOB_SELECT = (
    "id,JK_L_category,JK_M_category,top3,"
    "realistic_score,investigative_score,artistic_score,social_score,"
    "enterprising_score,conventional_score,major_required,job_information"
)
USER_ROADMAP_SELECT = "id,job_name,riasec_scores,roadmap_text,job_information,created_at"
RIASEC_LABELS = ["현실형", "탐구형", "예술형", "사회형", "진취형", "관습형"]
OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"

app = FastAPI()

# --- 모델 정의 ---
class RoadmapRequest(BaseModel):
    job_name: str
    is_major_required: bool
    user_major_status: str
    riasec_scores: Optional[dict] = None
    job_information: Optional[str] = None

class RoadmapChatRequest(BaseModel):
    message: str
    messages: Optional[List[Dict[str, str]]] = []
    job_name: Optional[str] = ""
    job_information: Optional[str] = ""
    riasec_scores: Optional[Dict[str, Any]] = None
    roadmap_text: Optional[str] = ""
    recommendations: Optional[List[Dict[str, Any]]] = []
    has_riasec_scores: Optional[bool] = None
    score_context_note: Optional[str] = None
    user_major_status: Optional[str] = None

class DeleteRoadmapsRequest(BaseModel):
    ids: list[str]

# --- LangChain RAG 로직 ---

def custom_search_jobs(query: str, k: int = 3):
    """라이브러리 호환성 문제를 피해 직접 벡터 검색을 수행하는 함수"""
    try:
        # 1. 질문을 벡터로 변환
        query_vector = embeddings.embed_query(query)
        
        # 2. Supabase match_jobs RPC 호출
        res = supabase_client.rpc("match_jobs", {
            "query_embedding": query_vector,
            "match_threshold": 0.5,
            "match_count": k
        }).execute()
        
        # 3. 결과 포맷팅
        docs = res.data or []
        return "\n\n".join([f"직무명: {doc.get('JK_M_category')}\n내용: {doc.get('job_information')}" for doc in docs])
    except Exception as e:
        print(f"검색 중 오류 발생: {e}")
        return "관련 직무 지식을 찾을 수 없습니다."

def get_rag_chain():
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)
    
    template = """
당신은 'AI 대감'이자 15년 경력의 베테랑 AI 직무 컨설턴트입니다. 
사용자의 기질(RIASEC)과 관아의 기록고(검색된 지식)를 바탕으로 조언하십시오.

### 핵심 지침 ###
1. **호칭**: 사용자를 '자네'라고 칭하십시오.
2. **성향 분석**: 대화 시작 시 반드시 사용자의 RIASEC 점수를 상세하게 언급하며 그 기질이 인간적으로 어떤 특징을 갖는지 먼저 설명하십시오.
3. **지식 활용**: 반드시 아래 제공된 [관아의 기록고] 내용을 바탕으로 직무를 설명하십시오. 만약 기록에 없는 내용이라면 함부로 추측하지 말고 비기(로드맵)를 확인하라 이르십시오.

4. **말투**: 조선시대 대감의 엄중하면서도 호탕한 말투(~하였느냐, ~하시게 등)를 유지하십시오. 문장 시작은 항상 '허허', '오호', '음'과 같은 추임새로 시작하십시오. '하오'체는 금지입니다.
5. **대안 제시**: 사용자가 대안 직무에 대해서 질문을 하면 어려움을 토로하면 기록고에 있는 다른 직무를 찾아 기질과 맞는지 분석하여 분석한 내용과 함께 대안 직무를 제시합니다.

[사용자 기질 정보]
{user_context}

[관아의 기록고 (참고 지식)]
{context}

[이전 대화 기록]
{chat_history}

질문: {input}
대감의 조언:"""

    prompt = ChatPromptTemplate.from_template(template)
    
    # 체인 구성: 검색 로직을 custom_search_jobs로 교체
    chain = (
        {
            "context": lambda x: custom_search_jobs(x["input"]),
            "input": itemgetter("input"),
            "user_context": itemgetter("user_context"),
            "chat_history": itemgetter("chat_history")
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain

# --- 헬퍼 함수들 ---
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


def openai_chat_completion(messages, temperature=0.7, model=None):
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다.")

    selected_model = model or OPENAI_MODEL
    payload = {
        "model": selected_model,
        "messages": messages,
    }
    if temperature is not None and not selected_model.startswith("gpt-5"):
        payload["temperature"] = temperature
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


def save_user_roadmap(token, user_id, job_name, riasec_scores, roadmap_text, job_information=None):
    payload = {
        "user_id": user_id,
        "job_name": job_name,
        "riasec_scores": riasec_scores,
        "roadmap_text": roadmap_text,
        "job_information": job_information,
    }
    return supabase_request(
        "/rest/v1/user_roadmaps",
        method="POST",
        body=payload,
        token=token,
        prefer="return=representation",
    )


def normalize_riasec_scores(scores):
    if isinstance(scores, str):
        try:
            scores = json.loads(scores)
        except json.JSONDecodeError as e:
            raise ValueError("저장된 RIASEC 점수 형식이 올바르지 않습니다.") from e

    if not isinstance(scores, dict) or not scores:
        raise ValueError("저장된 RIASEC 점수가 비어 있습니다.")

    normalized = {}
    for label in RIASEC_LABELS:
        values = scores.get(label)
        if not isinstance(values, dict):
            raise ValueError("저장된 RIASEC 점수에 필요한 흥미 유형이 없습니다.")

        try:
            raw_score = int(values["원점수"])
            standard_score = int(values["표준점수"])
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError("저장된 RIASEC 점수 값이 올바르지 않습니다.") from e

        normalized[label] = {"원점수": raw_score, "표준점수": standard_score}

    return normalized


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
    return {label: {"원점수": raw, "표준점수": std} for label, raw, std in zip(RIASEC_LABELS, raw_scores, std_scores)}

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

@app.get("/api/latest_riasec_scores")
async def latest_riasec_scores(authorization: Optional[str] = Header(default=None)):
    try:
        try:
            token = get_bearer_token(authorization)
        except ValueError as e:
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=401)

        if not token:
            return JSONResponse(content={"status": "error", "message": "로그인이 필요합니다."}, status_code=401)

        user = get_authenticated_user(token)
        data = supabase_request(
            "/rest/v1/user_roadmaps",
            params={
                "select": "id,riasec_scores,created_at",
                "user_id": f"eq.{user['id']}",
                "riasec_scores": "not.is.null",
                "order": "created_at.desc",
                "limit": "1",
            },
            token=token,
        )
        if not data:
            return JSONResponse(
                content={"status": "error", "message": "불러올 수 있는 저장된 점수가 없습니다."},
                status_code=404,
            )

        try:
            scores = normalize_riasec_scores(data[0].get("riasec_scores"))
        except ValueError as e:
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=404)

        jobs_df = load_job_dataframe()
        recommendations = recommend_jobs_for_user_profile(scores, jobs_df)

        return {
            "status": "success",
            "scores": scores,
            "recommendations": recommendations,
            "source_created_at": data[0].get("created_at"),
        }
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

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


@app.post("/api/delete_roadmaps")
async def delete_roadmaps(req: DeleteRoadmapsRequest, authorization: Optional[str] = Header(default=None)):
    try:
        token = get_bearer_token(authorization)
        if not token:
            return JSONResponse(content={"status": "error", "message": "로그인이 필요합니다."}, status_code=401)

        if not req.ids:
            return JSONResponse(content={"status": "error", "message": "삭제할 기록을 선택해주세요."}, status_code=400)

        roadmap_ids = []
        for roadmap_id in req.ids:
            try:
                roadmap_uuid = str(UUID(str(roadmap_id)))
            except (TypeError, ValueError):
                return JSONResponse(content={"status": "error", "message": "로드맵 ID가 올바르지 않습니다."}, status_code=400)
            if roadmap_uuid not in roadmap_ids:
                roadmap_ids.append(roadmap_uuid)

        user = get_authenticated_user(token)
        deleted = supabase_request(
            "/rest/v1/user_roadmaps",
            method="DELETE",
            params={
                "id": f"in.({','.join(roadmap_ids)})",
                "user_id": f"eq.{user['id']}",
            },
            token=token,
            prefer="return=representation",
        )
        if not deleted:
            return JSONResponse(content={"status": "error", "message": "삭제할 기록을 찾을 수 없습니다."}, status_code=404)

        deleted_ids = [item.get("id") for item in deleted if isinstance(item, dict) and item.get("id")]
        return {"status": "success", "deleted_count": len(deleted), "deleted_ids": deleted_ids}
    except ValueError as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=401)
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
    
    # (프롬프트 분기 로직)
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
- 전체 분량: 700~900자"""
        else:
            sys_role = "당신은 특정 직무에 진입하기 위해 반드시 필요한 학위를 이미 이수했지만 실무 경험이 부족한 이들을 위한 커리어 코치입니다."
            user_context = f"- 선택한 직무: {req.job_name}\n- 전공 여부: 필수 전공 이수"
            out_inst = f"""
1. 3단계 실행 구조:

■ 1단계: 필수 라이선스(면허/자격) 획득 및 현장 감각 깨우기
- 해당 직무 진입에 필수적인 국가고시 또는 필수 면허 취득 전략 제시
- 선배 실무자의 브이로그, 현직자 인터뷰를 통해 학교와 현장의 차이점 파악
- 📌 결과물: 자격/면허 시험 합격을 위한 ‘과목별 핵심 요약 노트’ 또는 ‘스터디 플랜’

■ 2단계: 필수 수습/실습 파악 및 실무 도구 점검
- 직무에 따라 요구되는 법정 수습 기간, 인턴십, 실무 연수 과정 등 안내
- 채용공고에서 반복적으로 등장하는 실무 역량 2~3개를 반드시 추출하여 제시
- 📌 결과물: 실무에 투입되었을 때 당황하지 않기 위한 나만의 ‘업무 매뉴얼(체크리스트) 초안’

■ 3단계: 실전 구직 및 전문성 증명
- 고용24 또는 해당 직무에 특화된 채용 플랫폼 활용법 안내
- 단순 전공 지식을 넘어 실습/수련 경험을 녹여내는 이력서 작성 가이드
- 📌 결과물: 학과 시절의 실습/프로젝트 경험이 담긴 ‘직무기술서(또는 포트폴리오)’ 1개 제시

2. 작성 규칙:
- {req.job_name}에 맞는 구체적인 면허/국가 자격증 명칭 반드시 포함
- 각 단계 끝에 “💡 현실적 Tip” 포함
- 전체 분량: 700~900자 내외"""
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
- 📌 결과물: 간단한 실습 결과물 제시  

■ 3단계: 전문 교육 환경 진입  
- 고용24에서 검색할 키워드 구체적으로 제시  
- 관련 자격증 반드시 포함 (직무 맞춤)  
- 📌 결과물: 포트폴리오 형태 제시 (ex. 보고서, 프로젝트 등)

2. 작성 규칙:
- 초등학생도 이해할 수 있는 쉬운 표현 사용
- 각 단계 끝에 반드시 “💡 현실적 Tip” 추가
- 마지막 응원 문구는 생략하고 로드맵 본문으로만 마무리하십시오.
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
- 📌 결과물: 실무 툴 활용 결과물  

■ 3단계: 실전 역량 증명 및 심화  
- NCS 기반 부족 역량 점검  
- 고용24 교육 검색 키워드 제시  
- 📌 결과물: 취업용 포트폴리오 1개 구체적으로 제시  

2. 작성 규칙:
- 반드시 {req.job_name} 맞춤 예시 사용
- 전공 용어와 실무 용어를 연결 설명
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
            save_user_roadmap(token, user["id"], req.job_name, req.riasec_scores, roadmap_text, req.job_information)
        return {"status": "success", "roadmap": roadmap_text}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/roadmap_chat")
async def roadmap_chat(req: RoadmapChatRequest):
    if not req.message or not req.message.strip():
        return JSONResponse(content={"status": "error", "message": "질문을 입력해주세요."}, status_code=400)

    try:
        # LangChain Chain 획득
        chain = get_rag_chain()
        
        # 이전 대화 기록 포맷팅
        history_str = ""
        if req.messages:
            for m in req.messages[-6:]:
                role = "나" if m.get("role") == "user" else "대감"
                history_str += f"{role}: {m.get('content')}\n"
        
        # 사용자 기질 맥락 생성
        user_context = f"- 현재 선택 직무: {req.job_name}\n"
        if req.riasec_scores:
            user_context += f"- RIASEC 점수: {json.dumps(req.riasec_scores, ensure_ascii=False)}\n"
        if req.roadmap_text:
            user_context += f"- 생성된 로드맵 요약: {req.roadmap_text[:200]}..."

        # 체인 실행
        result = chain.invoke({
            "input": req.message,
            "user_context": user_context,
            "chat_history": history_str
        })
        
        return {"status": "success", "reply": result, "citations": []}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

# 모든 API 정의 후에 정적 파일 서빙 설정
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
