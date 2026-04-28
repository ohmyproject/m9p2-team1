from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "static"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def load_local_env() -> None:
    for filename in (".env", ".env.local"):
        path = ROOT_DIR / filename
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_local_env()

from core import (
    JobCatalogError,
    extract_scores_from_pdf,
    get_job_by_id,
    get_job_by_title,
    recommended_jobs_payload,
    search_jobs,
)

app = FastAPI(title="직무 추천 프로토타입")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


CODE_TO_STRENGTH = {
    "R": "현장 실행, 문제 대응, 도구 활용",
    "I": "분석, 리서치, 구조적 사고",
    "A": "기획, 표현, 창의적 해결",
    "S": "협업, 커뮤니케이션, 지원",
    "E": "리드, 설득, 추진력",
    "C": "정리, 운영, 문서화",
}


class RoadmapRequest(BaseModel):
    job_id: int | None = None
    job_title: str | None = None
    profile: dict | None = None


def build_profile_text(profile: dict | None) -> str:
    if not profile:
        return "사용자 프로필 정보가 아직 비어 있습니다."

    fields = [
        ("이름", profile.get("name")),
        ("전공", profile.get("major")),
        ("목표", profile.get("goal")),
        ("상태", profile.get("status")),
        ("메모", profile.get("note")),
    ]
    return "\n".join(f"- {label}: {value}" for label, value in fields if value)


def fallback_roadmap(job: dict, profile: dict | None) -> dict:
    codes = [code for code in job.get("top3", "") if code in CODE_TO_STRENGTH]
    strengths = [CODE_TO_STRENGTH[code] for code in codes[:3]]
    title = job["title"]
    category = job["category"]
    definition = job.get("job_definition") or job.get("description") or ""
    definition_summary = job.get("definition_summary") or job.get("description") or title
    goal = (profile or {}).get("goal") or "준비 방향 설정"
    status = (profile or {}).get("status") or "현재 상태 미정"

    return {
        "summary": f"{title} 로드맵입니다. 직무정의의 핵심인 '{definition_summary}'를 기준으로 현재 목표({goal})와 상태({status})에 맞춰 준비 단계를 정리했습니다.",
        "steps": [
            {
                "title": "Step 1. 직무 이해와 기준선 만들기",
                "period": "1~2주",
                "actions": [
                    f"직무정의에서 {title}의 핵심 업무, 성과 기준, 필요한 역량을 각각 3개씩 뽑기",
                    f"{job['onet_title']} 관련 공고 10개를 읽고 공통 요구사항 추리기",
                    f"내 경험을 '{definition_summary}'와 연결되는 사례 중심으로 정리하기",
                ],
                "output": "직무 요약 문서 1장, 공고 분석 메모 1개",
            },
            {
                "title": "Step 2. 실무 증거 만들기",
                "period": "3~6주",
                "actions": [
                    f"직무정의에 나온 업무 흐름을 반영한 {title} 미니 프로젝트 1~2개 만들기",
                    "이력서와 포트폴리오에 들어갈 성과 문장을 STAR 형식으로 정리하기",
                    f"{category} 분야 공고 표현에 맞춰 포트폴리오 설명을 다듬기",
                ],
                "output": "포트폴리오 1세트, 이력서 초안 1부",
            },
            {
                "title": "Step 3. 지원 전략과 면접 준비",
                "period": "2~3주",
                "actions": [
                    "지원 기업군을 3개로 나누고 공고별 자기소개 포인트 정리하기",
                    f"직무정의 기반으로 {title} 지원 동기, 문제 해결 경험, 협업 경험 답변 스크립트 작성하기",
                    "모의 면접 질문 10개로 답변 연습하기",
                ],
                "output": "지원용 이력서/자소서, 면접 답변 노트",
            },
        ],
        "certifications": [
            f"{title}와 직접 연결되는 실무형 자격증 또는 수료증 1개 조사",
            "엑셀, 데이터 정리, 문서화 같은 공통 도구 역량 보완",
            "관심 산업에 맞는 부트캠프/온라인 강의 선별",
        ],
        "resources": [
            "채용 공고 10개 분석 표 만들기",
            f"직무정의 원문 검토: {definition[:80]}..." if len(definition) > 80 else f"직무정의 원문 검토: {definition}",
            "현직자 인터뷰 또는 유튜브 직무 브이로그 3개 보기",
            "포트폴리오 또는 직무 노트 Notion 페이지 구성",
        ],
        "strengths": strengths or ["직무 관련 강점을 추후 보강"],
    }


def generate_openai_roadmap(job: dict, profile: dict | None) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    if not api_key:
        return None
    job_definition = job.get("job_definition") or job.get("description") or ""

    prompt = f"""
당신은 한국 취업 준비용 직무 코치입니다.
반드시 JSON 객체만 반환하세요.

직무 정보:
- 직무명: {job["title"]}
- 대분류: {job["category"]}
- 연관 O*NET 직무: {job["onet_title"]}
- 화면 표시용 한 줄 요약: {job["description"]}
- 로드맵 기준 직무정의 원문: {job_definition}
- 흥미 코드: {job.get("top3", "")}
- 태그: {", ".join(job.get("tags", []))}

사용자 프로필:
{build_profile_text(profile)}

반환 형식:
{{
  "summary": "한 문단 요약",
  "steps": [
    {{
      "title": "Step 1 제목",
      "period": "기간",
      "actions": ["행동1", "행동2", "행동3"],
      "output": "이 단계 결과물"
    }}
  ],
  "certifications": ["추천 자격/학습 항목1", "항목2", "항목3"],
  "resources": ["참고 자료 유형1", "자료 유형2", "자료 유형3"],
  "strengths": ["이 직무에 중요한 역량1", "역량2", "역량3"]
}}

조건:
- steps는 정확히 3개
- 한국어로 작성
- 로드맵은 반드시 직무정의 원문의 업무 내용과 역량을 기준으로 구성
- 각 action은 짧고 실행 가능하게 작성
- 자격증이 꼭 없으면 학습 주제나 도구 역량으로 대체 가능
""".strip()

    payload = {"model": model, "input": prompt}
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    text = raw.get("output_text", "").strip()
    if not text:
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1:
            return None
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None


def generate_roadmap(job: dict, profile: dict | None) -> dict:
    return generate_openai_roadmap(job, profile) or fallback_roadmap(job, profile)


HOME_HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>노비Job아라 Prototype</title>
  <link rel="stylesheet" href="/static/app.css?v=dashboard-20260428-2">
</head>
<body>
  <div class="app-shell">
    <aside class="upload-sidebar">
      <div class="brand">노비Job아라 Prototype</div>
      <p class="sidebar-copy">직업선호도검사 PDF를 넣으면 RIASEC 점수를 추출하고, 현재 유사도 기반 추천직무 10개를 보여줍니다.</p>

      <label class="dropzone" id="dropzone" for="file-input" tabindex="0">
        <input id="file-input" class="visually-hidden" name="file" type="file" accept="application/pdf,.pdf">
        <span class="dropzone-mark">PDF</span>
        <span class="dropzone-title">파일 선택 또는 드래그</span>
        <span class="dropzone-copy">직업선호도검사 결과 PDF만 업로드할 수 있습니다.</span>
      </label>

      <div id="file-name" class="file-name">선택된 파일 없음</div>
      <button class="primary-btn" id="analyze-btn" type="button">분석</button>
      <div id="status-text" class="status">PDF를 선택하면 분석을 시작할 수 있습니다.</div>
    </aside>

    <main class="workspace">
      <section class="analysis-view" id="analysis-view">
        <div class="top-grid">
          <section class="panel score-panel">
            <div class="section-head">
              <div>
                <p class="eyebrow">PDF 추출 결과</p>
                <h1>RIASEC 점수</h1>
              </div>
              <span class="top3-chip" id="top3-chip">TOP3 -</span>
            </div>
            <div class="scores-grid" id="scores-grid">
              <div class="empty">분석 후 표준점수와 원점수가 여기에 표시됩니다.</div>
            </div>
          </section>

          <section class="panel radar-panel">
            <div class="section-head">
              <div>
                <p class="eyebrow">육각형 그래프</p>
                <h2>흥미 유형 분포</h2>
              </div>
            </div>
            <div class="radar-chart" id="radar-chart">
              <div class="empty">점수가 추출되면 6축 그래프가 나타납니다.</div>
            </div>
          </section>
        </div>

        <section class="panel recommendations-panel">
          <div class="section-head">
            <div>
              <p class="eyebrow">추천 결과</p>
              <h2>추천직무 Top 10</h2>
            </div>
          </div>
          <div id="recommendations" class="recommend-grid">
            <div class="empty">분석 버튼을 누르면 현재 유사도 기반 추천직무가 표시됩니다.</div>
          </div>
        </section>
      </section>

      <section class="chat-view is-hidden" id="chat-view">
        <button class="ghost-btn" id="back-btn" type="button">추천 결과로 돌아가기</button>
        <div class="panel selected-job-panel" id="selected-job-panel"></div>
        <div class="panel chat-panel">
          <div id="chat-thread" class="chat-thread"></div>
          <div id="choice-row" class="choice-row"></div>
          <div id="roadmap-shell" class="roadmap-shell"></div>
        </div>
      </section>
    </main>
  </div>
  <script src="/static/app.js?v=dashboard-20260428-2"></script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def root():
    return HOME_HTML


@app.get("/health")
def health():
    return {"message": "FastAPI server is running"}


@app.post("/recommend")
async def recommend_from_pdf(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            temp_path = tmp.name

        user_scores = extract_scores_from_pdf(temp_path)
        recommendations = recommended_jobs_payload(user_scores, top_n=10)
        return {"extracted_scores": user_scores, "recommendations": recommendations}
    except JobCatalogError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"처리 중 오류가 발생했습니다: {exc}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/catalog/search")
def catalog_search(query: str = Query(default="", max_length=100)):
    try:
        return {"jobs": search_jobs(query)}
    except JobCatalogError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/roadmap")
def roadmap(request: RoadmapRequest):
    try:
        if request.job_id is not None:
            job = get_job_by_id(request.job_id)
        elif request.job_title:
            job = get_job_by_title(request.job_title)
        else:
            raise HTTPException(status_code=400, detail="job_id 또는 job_title이 필요합니다.")
    except JobCatalogError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    if not job:
        raise HTTPException(status_code=404, detail="해당 직무를 찾을 수 없습니다.")
    return {"job": job, "roadmap": generate_roadmap(job, request.profile)}
