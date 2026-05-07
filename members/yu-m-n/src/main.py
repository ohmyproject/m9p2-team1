import pandas as pd
import numpy as np
import re
import io
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
from pypdf import PdfReader
from openai import OpenAI
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# .env 파일 로드
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# 공유 링크용 결과 저장소 (메모리 기반, 재시작 시 초기화됨)
# 운영 환경에서는 Redis나 DB로 교체 권장
result_store: dict = {}

# 프론트엔드 정적 파일(HTML, CSS, JS) 서빙 설정
# (프로젝트 폴더 안에 'static' 폴더를 만들고 index.html, style.css, script.js를 넣으세요)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 전역 데이터 로드
try:
    df = pd.read_csv("잡코리아_Onet통합본_직무정보추가.csv")
except Exception as e:
    print(f"데이터 로드 실패: {e}")
    df = pd.DataFrame()

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

class SaveResultRequest(BaseModel):
    job_name: str
    riasec_scores: dict
    roadmap_text: str

@app.get("/", response_class=HTMLResponse)
async def read_index():
    # static 폴더 내의 index.html 반환
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/api/upload_pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """PDF 파일을 받아 점수를 추출하고 추천 직무를 반환하는 API"""
    try:
        pdf_bytes = await file.read()
        scores = extract_scores_from_pdf(pdf_bytes)
        recommendations = recommend_jobs_for_user_profile(scores, df)
        
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
    if df.empty:
        return JSONResponse(content={"status": "error", "message": "데이터베이스를 불러올 수 없습니다."}, status_code=500)
    
    results =df[
        df['JK중분류'].str.contains(query, na=False, case=False)].head(5)
    
    
    # NaN 처리를 위해 replace 사용
    results_dict = results.fillna("").to_dict(orient="records")
    return JSONResponse(content={"status": "success", "results": results_dict})

@app.post("/api/save_result")
async def save_result(req: SaveResultRequest):
    """로드맵 결과를 저장하고 공유용 UUID를 반환"""
    result_id = str(uuid.uuid4())
    result_store[result_id] = {
        "job_name": req.job_name,
        "riasec_scores": req.riasec_scores,
        "roadmap_text": req.roadmap_text,
        "created_at": datetime.now().isoformat(),
    }
    return JSONResponse(content={"status": "success", "result_id": result_id})

@app.get("/api/result/{result_id}")
async def get_result_json(result_id: str):
    """UUID로 저장된 로드맵 결과를 JSON으로 조회 (내부 API용)"""
    data = result_store.get(result_id)
    if not data:
        return JSONResponse(
            content={"status": "error", "message": "결과를 찾을 수 없사옵니다. 링크가 만료되었거나 잘못된 주소이옵니다."},
            status_code=404
        )
    return JSONResponse(content={"status": "success", **data})


@app.get("/result/{result_id}", response_class=HTMLResponse)
async def view_result_page(result_id: str):
    """공유 링크 전용 — 게임 UI 없이 결과만 보여주는 독립 페이지"""
    data = result_store.get(result_id)

    if not data:
        return HTMLResponse(content=_not_found_page(), status_code=404)

    job_name      = data["job_name"]
    scores        = data["riasec_scores"]
    roadmap_text  = data["roadmap_text"]
    created_at    = data["created_at"][:10]

    riasec_labels = {
        "현실형": "R", "탐구형": "I", "예술형": "A",
        "사회형": "S", "진취형": "E", "관습형": "C"
    }
    bar_html = ""
    if scores:
        max_std = max((v.get("표준점수", 0) if isinstance(v, dict) else v) for v in scores.values()) or 1
        for label, code in riasec_labels.items():
            raw_val = scores.get(label, {})
            std = raw_val.get("표준점수", 0) if isinstance(raw_val, dict) else int(raw_val or 0)
            pct = round(std / max_std * 100)
            bar_html += f"""
            <div class="bar-row">
                <span class="bar-label">{label}({code})</span>
                <div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>
                <span class="bar-val">{std}</span>
            </div>"""

    # 로드맵 텍스트를 단계별로 분리하여 카드 HTML로 변환
    import re as _re
    sections = _re.split(r'(?=(?:■|#|\*)*\s*\d+단계)', roadmap_text)
    sections = [s.strip() for s in sections if len(s.strip()) > 20]
    cards_html = ""
    for sec in sections:
        m = _re.search(r'(\d+)단계[:\s]*(.*)', sec)
        if m:
            title = f"제{m.group(1)}관문: {m.group(2).split(chr(10))[0].strip()}".replace("■","").replace("#","").strip()
            body  = sec[sec.index(m.group(0)) + len(m.group(0)):].strip()
        else:
            title = "📜 입신양명 비기"
            body  = sec
        body_html = body.replace("\n","<br>").replace("📌","<br>📌").replace("💡","<br>💡")
        body_html = _re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', body_html)
        cards_html += f"""
        <div class="card">
            <h3 class="card-title">{title}</h3>
            <div class="card-body">{body_html}</div>
        </div>"""

    return HTMLResponse(content=_result_page(job_name, created_at, bar_html, cards_html))


def _not_found_page() -> str:
    return """<!DOCTYPE html><html lang="ko"><head>
<meta charset="UTF-8"><title>없는 로드맵</title>
<link href="https://unpkg.com/nes.css@latest/css/nes.min.css" rel="stylesheet">
<style>body{background:#212529;color:#f7d51d;font-family:'DungGeunMo',sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;flex-direction:column;gap:20px;}</style>
</head><body>
<p style="font-size:24px">📜 이 로드맵은 존재하지 않사옵니다.</p>
<p style="color:#aaa;font-size:14px">링크가 만료되었거나 잘못된 주소이옵니다.</p>
<a href="/" class="nes-btn is-warning">처음으로 돌아가기</a>
</body></html>"""


def _result_page(job_name: str, created_at: str, bar_html: str, cards_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="{job_name} 취업 로드맵 | 노비 JOB아라!">
<meta property="og:description" content="AI가 분석한 {job_name} 맞춤형 취업 로드맵을 확인하세요.">
<title>{job_name} 로드맵 | 노비 JOB아라!</title>
<link href="https://unpkg.com/nes.css@latest/css/nes.min.css" rel="stylesheet">
<style>
@font-face {{
    font-family:'DungGeunMo';
    src:url('https://fastly.jsdelivr.net/gh/projectnoonnu/noonfonts_six@1.2/DungGeunMo.woff') format('woff');
}}
:root {{
    --gold:#f7d51d; --gold-dk:#d4a017; --ink:#212529;
    --parchment:#f8e5c0; --green:#4aa52e;
}}
*{{ box-sizing:border-box; margin:0; padding:0; }}
body {{
    background:#1a1a2e;
    font-family:'DungGeunMo',monospace;
    color:#e0e0e0;
    min-height:100vh;
    padding: 0 0 60px;
}}

/* ── 헤더 ── */
.header {{
    background:#0f0f1a;
    border-bottom:3px solid var(--gold);
    padding:18px 24px;
    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;
}}
.header-title {{
    font-size:22px; color:var(--gold);
    text-shadow:2px 2px #000;
}}
.header-sub {{
    font-size:13px; color:#aaa;
}}

/* ── 히어로 배너 ── */
.hero {{
    background:linear-gradient(135deg,#16213e 0%,#0f3460 100%);
    border-bottom:3px solid var(--gold);
    padding:36px 24px;
    text-align:center;
}}
.hero h1 {{
    font-size:32px; color:var(--gold);
    text-shadow:3px 3px #000;
    margin-bottom:10px;
}}
.hero .meta {{
    color:#aab; font-size:14px;
}}

/* ── 컨테이너 ── */
.container {{
    max-width:860px; margin:0 auto; padding:0 20px;
}}

/* ── RIASEC 섹션 ── */
.section {{
    background:#0f0f1a;
    border:3px solid #3a3a5a;
    margin-top:28px;
    padding:24px;
}}
.section-title {{
    font-size:18px; color:var(--gold);
    border-bottom:2px solid var(--gold-dk);
    padding-bottom:8px; margin-bottom:18px;
}}
.bar-row {{ display:flex; align-items:center; gap:10px; margin-bottom:10px; }}
.bar-label {{ width:90px; font-size:13px; color:#ccc; flex-shrink:0; }}
.bar-track {{
    flex:1; height:14px; background:#2a2a3a;
    border:1px solid #4a4a6a; overflow:hidden;
}}
.bar-fill {{
    height:100%;
    background:linear-gradient(90deg,var(--gold-dk),var(--gold));
}}
.bar-val {{ font-size:13px; color:var(--gold); width:36px; text-align:right; }}

/* ── 로드맵 카드 ── */
.card {{
    background:#0f0f1a;
    border:3px solid #3a3a5a;
    margin-top:20px;
    overflow:hidden;
}}
.card-title {{
    background:#16213e;
    border-bottom:3px solid var(--gold-dk);
    padding:14px 20px;
    font-size:17px; color:var(--gold);
}}
.card-body {{
    padding:20px;
    font-size:15px; line-height:2;
    color:#ccc;
}}
.card-body br + br {{ display:block; content:""; margin-top:4px; }}

/* ── CTAバー ── */
.cta-bar {{
    position:fixed; bottom:0; left:0; right:0;
    background:#0f0f1a;
    border-top:3px solid var(--gold);
    padding:12px 20px;
    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:10px;
    z-index:100;
}}
.cta-bar p {{ font-size:14px; color:#aaa; }}
.btn-gold {{
    background:var(--gold); color:#000;
    border:3px solid #a07800;
    padding:10px 22px;
    font-family:'DungGeunMo',monospace;
    font-size:15px; font-weight:bold;
    cursor:pointer;
    box-shadow:4px 4px 0 #000;
    text-decoration:none;
    display:inline-block;
}}
.btn-gold:hover {{ background:#e0c000; }}
.btn-copy {{
    background:#2563eb; color:#fff;
    border:3px solid #1040a0;
    padding:10px 22px;
    font-family:'DungGeunMo',monospace;
    font-size:15px;
    cursor:pointer;
    box-shadow:4px 4px 0 #000;
}}
.btn-copy:hover {{ background:#1d4ed8; }}

/* ── 토스트 ── */
#toast {{
    position:fixed; bottom:80px; left:50%; transform:translateX(-50%);
    background:#212529; color:var(--gold); border:3px solid var(--gold);
    padding:12px 24px; font-size:14px; z-index:200;
    display:none; white-space:nowrap;
    box-shadow:6px 6px 0 #000;
    animation:toastIn .3s ease;
}}
@keyframes toastIn{{
    from{{opacity:0;transform:translate(-50%,16px)}}
    to{{opacity:1;transform:translate(-50%,0)}}
}}
</style>
</head>
<body>

<div class="header">
    <div>
        <div class="header-title">⚔️ 노비 JOB아라!</div>
        <div class="header-sub">AI 취업 로드맵 생성기</div>
    </div>
    <a href="/" class="btn-gold" style="font-size:13px;padding:8px 16px;">나도 만들어보기 →</a>
</div>

<div class="hero">
    <h1>📜 {job_name}</h1>
    <p class="meta">AI 대감이 {created_at}에 점지한 취업 로드맵</p>
</div>

<div class="container">
    {"" if not bar_html else f'''
    <div class="section">
        <div class="section-title">🎯 직업흥미 유형 분석 (RIASEC)</div>
        {bar_html}
    </div>
    '''}

    <div class="section">
        <div class="section-title">🗺️ 취업 로드맵</div>
        <p style="color:#888;font-size:13px;margin-bottom:4px;">아래 단계를 순서대로 따라가시게.</p>
    </div>
    {cards_html}
</div>

<div id="toast">✅ 링크가 복사되었사옵니다!</div>

<div class="cta-bar">
    <p>이 로드맵이 도움이 되었다면 친구에게도 공유하시게!</p>
    <div style="display:flex;gap:10px;flex-wrap:wrap;">
        <button class="btn-copy" onclick="copyLink()">🔗 링크 복사</button>
        <a href="/" class="btn-gold">나도 로드맵 만들기 →</a>
    </div>
</div>

<script>
function copyLink() {{
    navigator.clipboard.writeText(window.location.href).then(() => {{
        const t = document.getElementById('toast');
        t.style.display = 'block';
        setTimeout(() => {{ t.style.display = 'none'; }}, 2500);
    }}).catch(() => prompt('링크를 복사하시게:', window.location.href));
}}
</script>
</body>
</html>"""

@app.post("/api/roadmap")
async def generate_roadmap(req: RoadmapRequest):
    """선택한 직무와 전공 여부를 바탕으로 AI 로드맵을 생성하는 API"""
    client = OpenAI(api_key=OPENAI_API_KEY)
    is_user_major = (req.user_major_status == "yes")
    
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
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": "나를 위한 직무 전환 및 취업 로드맵을 작성해줘."}
            ],
            temperature=0.7
        )
        return {"status": "success", "roadmap": response.choices[0].message.content}
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)