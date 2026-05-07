from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine
import pandas as pd
import numpy as np
import re
import io
import os
from dotenv import load_dotenv
from pypdf import PdfReader
from openai import OpenAI

# ---------------------------------------------------------
# 경로 및 환경변수 설정
# ---------------------------------------------------------
# api 폴더의 상위 폴더(prototype)를 BASE_DIR로 설정
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, '.env'))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()

# 정적 파일 서빙 (HTML, CSS, JS)
STATIC_DIR = os.path.join(BASE_DIR, "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# ---------------------------------------------------------
# SQL 데이터 로드 및 컬럼명 매핑 (FastAPI 서버용)
# ---------------------------------------------------------
try:
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL 환경 변수가 설정되지 않았습니다.")
        
    engine = create_engine(DATABASE_URL)
    query = "SELECT * FROM JK_job"
    df = pd.read_sql(query, engine)
    
    df = df.rename(columns={
        'JK_L_category': 'JK대분류',
        'JK_M_category': 'JK중분류',
        'similar_job_name': '매핑 O*NET 직업명',
        'top3': 'Top3',
        'realistic_score': '현실형(R) T',
        'investigative_score': '탐구형(I) T',
        'artistic_score': '예술형(A) T',
        'social_score': '사회형(S) T',
        'enterprising_score': '진취형(E) T',
        'conventional_score': '관습형(C) T',
        'job_definition': '통합_직무정의' 
    })
    
    if '전공필수' not in df.columns:
        df['전공필수'] = 'X'

    df_jobs = df.replace({np.nan: None})
    print("✅ [FastAPI] SQL 데이터 로드 성공!")
except Exception as e:
    print(f"❌ [FastAPI] 데이터 로드 실패: {e}")
    df_jobs = pd.DataFrame()

# --- 핵심 로직 ---
def extract_scores_from_pdf(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    full_text = []
    for page in reader.pages:
        t = page.extract_text()
        if t:
            full_text.append(t)
    text = "\n".join(full_text)

    labels = ["현실형", "탐구형", "예술형", "사회형", "진취형", "관습형"]

    # ── 전략 1: 원래 정규식 (구분 헤더 포함)
    m = re.search(
        r"직업\s*흥미\s*유형별\s*점수"
        r".*?구\s*분\s*현실형\s*탐구형\s*예술형\s*사회형\s*진취형\s*관습형"
        r"\s*원\s*점\s*수\s*([\d\s]+?)\s*표준\s*점수\s*([\d\s]+)",
        text, re.S
    )
    if m:
        raw_scores = list(map(int, m.group(1).split()))[:6]
        std_scores = list(map(int, m.group(2).split()))[:6]
        if len(raw_scores) == 6 and len(std_scores) == 6:
            return {label: {"원점수": r, "표준점수": s, "T점수": s}
                    for label, r, s in zip(labels, raw_scores, std_scores)}

    # ── 전략 2: 원점수 / 표준점수 행만 찾기 (헤더 없이)
    m2 = re.search(r"원\s*점\s*수\s*([\d\s]+?)\s*표준\s*점수\s*([\d\s]+)", text, re.S)
    if m2:
        raw_scores = list(map(int, m2.group(1).split()))[:6]
        std_scores = list(map(int, m2.group(2).split()))[:6]
        if len(raw_scores) == 6 and len(std_scores) == 6:
            return {label: {"원점수": r, "표준점수": s, "T점수": s}
                    for label, r, s in zip(labels, raw_scores, std_scores)}

    # ── 전략 3: 각 유형별로 직접 숫자 추출
    result = {}
    label_patterns = {
        "현실형": r"현실형[^\d]*(\d+)[^\d]+(\d+)",
        "탐구형": r"탐구형[^\d]*(\d+)[^\d]+(\d+)",
        "예술형": r"예술형[^\d]*(\d+)[^\d]+(\d+)",
        "사회형": r"사회형[^\d]*(\d+)[^\d]+(\d+)",
        "진취형": r"진취형[^\d]*(\d+)[^\d]+(\d+)",
        "관습형": r"관습형[^\d]*(\d+)[^\d]+(\d+)",
    }
    for label, pat in label_patterns.items():
        m3 = re.search(pat, text)
        if m3:
            result[label] = {"원점수": int(m3.group(1)), "표준점수": int(m3.group(2)), "T점수": int(m3.group(2))}

    if len(result) == 6:
        return result

    # ── 전략 4: 페이지별로 숫자 6개씩 두 줄 찾기
    for page_text in full_text:
        numbers = list(map(int, re.findall(r"\b(\d{1,3})\b", page_text)))
        # 6개씩 두 그룹 연속으로 나오는 패턴 찾기
        for i in range(len(numbers) - 11):
            group1 = numbers[i:i+6]
            group2 = numbers[i+6:i+12]
            # 점수 범위 필터 (원점수 0~40, 표준점수 20~80 정도)
            if all(0 <= v <= 50 for v in group1) and all(20 <= v <= 100 for v in group2):
                return {label: {"원점수": r, "표준점수": s, "T점수": s}
                        for label, r, s in zip(labels, group1, group2)}

    # 디버그: 추출된 텍스트 일부를 에러 메시지에 포함
    preview = text[:500].replace("\n", " ")
    raise ValueError(f"PDF에서 점수를 찾을 수 없습니다. PDF 텍스트 미리보기: {preview}")

def recommend_jobs_for_user_profile(user_scores, df_data):
    if df_data.empty: return []
    label_map_t = {"현실형": "현실형(R) T", "탐구형": "탐구형(I) T", "예술형": "예술형(A) T", "사회형": "사회형(S) T", "진취형": "진취형(E) T", "관습형": "관습형(C) T"}
    label_map_raw = {"현실형": "R", "탐구형": "I", "예술형": "A", "사회형": "S", "진취형": "E", "관습형": "C"}
    user_profile = {label_map_t[l]: s["표준점수"] for l, s in user_scores.items()}
    user_raw_profile = {label_map_raw[l]: s["원점수"] for l, s in user_scores.items()}
    score_cols = list(user_profile.keys())
    user_vec = np.array([user_profile[col] for col in score_cols], dtype=float)
    user_raw_top3 = sorted(user_raw_profile.keys(), key=lambda x: (-user_raw_profile[x], ["R", "I", "A", "S", "E", "C"].index(x)))[:3]

    work_df = df_data.copy()
    for col in score_cols: work_df[col] = pd.to_numeric(work_df[col], errors="coerce")
    work_df = work_df.dropna(subset=score_cols).reset_index(drop=True)
    job_matrix = work_df[score_cols].to_numpy(dtype=float)

    cos_sim = np.nan_to_num((job_matrix @ user_vec) / (np.linalg.norm(job_matrix, axis=1) * np.linalg.norm(user_vec) + 1e-9))
    dist_sim = 1 / (1 + np.linalg.norm(job_matrix - user_vec, axis=1))
    t_final_sim = 0.75 * cos_sim + 0.25 * dist_sim

    def parse_top3_codes(v):
        if pd.isna(v) or v is None: return []
        seen = set()
        return [x for x in [ch for ch in str(v).upper() if ch in "RIASEC"] if not (x in seen or seen.add(x))][:3]

    def raw_top3_bonus(job_t3, user_t3):
        if not job_t3: return 0.0
        score, w = 0.0, {user_t3[0]: 3, user_t3[1]: 2, user_t3[2]: 1} if len(user_t3) == 3 else {}
        for i, code in enumerate(job_t3):
            if code in w: score += w[code] * (3 - i)
        return score / 14

    top3_bonus_arr = np.array([raw_top3_bonus(parse_top3_codes(row.get("Top3")), user_raw_top3) for _, row in work_df.iterrows()], dtype=float)
    result = work_df.copy()
    result["최종유사도"] = (0.80 * t_final_sim) + (0.20 * top3_bonus_arr)
    result = result.sort_values(by=["최종유사도"], ascending=False).reset_index(drop=True)
    
    return result.head(10)[["JK중분류", "통합_직무정의", "전공필수", "최종유사도"]].to_dict(orient="records")

# --- API 라우터 ---
class RoadmapRequest(BaseModel):
    job_name: str
    is_major_required: bool
    user_major_status: str

@app.get("/", response_class=HTMLResponse)
async def read_index():
    # templates/index.html 우선, 없으면 같은 디렉터리의 index.html 시도
    candidates = [
        os.path.join(BASE_DIR, "templates", "index.html"),
        os.path.join(BASE_DIR, "index.html"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"),
    ]
    for index_path in candidates:
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                return f.read()
    return HTMLResponse("<h1>index.html을 찾을 수 없습니다.</h1>", status_code=404)

@app.post("/api/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        scores = extract_scores_from_pdf(pdf_bytes)
        recommendations = recommend_jobs_for_user_profile(scores, df_jobs)
        return JSONResponse(content={"status": "success", "scores": scores, "recommendations": recommendations})
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=400)

@app.post("/api/debug_pdf")
async def debug_pdf(file: UploadFile = File(...)):
    """PDF에서 추출된 원본 텍스트를 반환 (디버그용)"""
    try:
        pdf_bytes = await file.read()
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for i, page in enumerate(reader.pages):
            t = page.extract_text()
            pages.append({"page": i+1, "text": t or ""})
        full = "\n".join(p["text"] for p in pages)
        return JSONResponse(content={"status": "success", "pages": pages, "full_text": full})
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=400)

@app.get("/api/search_job")
async def search_job(query: str):
    if df_jobs.empty: return JSONResponse(content={"status": "error", "message": "DB 에러"}, status_code=500)
    results = df_jobs[df_jobs['JK중분류'].str.contains(query, na=False, case=False)].head(5)
    return JSONResponse(content={"status": "success", "results": results.fillna("").to_dict(orient="records")})

@app.post("/api/roadmap")
async def generate_roadmap(req: RoadmapRequest):
    if not OPENAI_API_KEY: return JSONResponse(content={"status": "error", "message": "API KEY 누락"}, status_code=500)
    client = OpenAI(api_key=OPENAI_API_KEY)
    is_user_major = req.user_major_status in ["yes", "관련 전공", "O"]
    
    # 프롬프트 로직 (공통)
    sys_role = "현실적인 커리어 코치입니다. 학점은행제나 내일배움카드 등을 활용하여 현실적인 조언을 해주세요."
    user_context = f"- 직무명: {req.job_name}\n- 전공 여부: {req.user_major_status}"
    out_inst = "1단계(직무 친해지기), 2단계(실무 기초/행정), 3단계(실전/포트폴리오)로 나누어 각각 결과물과 Tip을 포함해 마크다운으로 작성하세요. 전체 분량 700~900자."

    full_prompt = f"[System Role]\n{sys_role}\n\n[User Context]\n{user_context}\n\n[Output Instructions]\n{out_inst}"
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": full_prompt}, {"role": "user", "content": "로드맵 작성해줘"}],
            temperature=0.7
        )
        return {"status": "success", "roadmap": response.choices[0].message.content}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)