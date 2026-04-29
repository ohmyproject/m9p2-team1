from __future__ import annotations

import json
import os
import re
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


class RoadmapRequest(BaseModel):
    job_id: int | None = None
    job_title: str | None = None
    profile: dict | None = None


def is_user_major_profile(profile: dict | None) -> bool:
    major = str((profile or {}).get("major") or "")
    return "비전공" not in major and "타전공" not in major


def build_test_roadmap_prompt(job: dict, profile: dict | None) -> str:
    job_name = job["title"]
    is_major_required = job.get("major_required") == "O"
    is_user_major = is_user_major_profile(profile)

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

    return f"[System Role]\n{sys_role}\n\n[User Context]\n{user_context}\n\n[Output Instructions]\n{out_inst}"


def summarize_roadmap_text(text: str, max_length: int = 170) -> str:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    summary = paragraphs[0] if paragraphs else text.strip()
    summary = re.sub(r"\s+", " ", summary)
    if len(summary) <= max_length:
        return summary
    return summary[: max_length - 1].rstrip() + "…"


def parse_roadmap_steps(raw_text: str) -> list[dict]:
    pattern = re.compile(
        r"(?:^|\n)\s*(?:■\s*)?([123])단계\s*[:：]\s*([^\n]+)\n?(.*?)(?=\n\s*(?:■\s*)?[123]단계\s*[:：]|\Z)",
        re.S,
    )
    steps = []
    for match in pattern.finditer(raw_text):
        number, heading, body = match.groups()
        actions = []
        output = ""
        for line in body.splitlines():
            cleaned = line.strip().lstrip("-• ").strip()
            if not cleaned:
                continue
            if "결과물" in cleaned and not output:
                output = cleaned.split(":", 1)[-1].strip() if ":" in cleaned else cleaned
                continue
            if cleaned.startswith("💡"):
                if len(actions) < 3:
                    actions.append(cleaned)
                continue
            if len(actions) < 3:
                actions.append(cleaned)
        steps.append(
            {
                "title": f"Step {number}. {heading.strip()}",
                "period": "AI 생성",
                "actions": actions[:3] or [summarize_roadmap_text(body, 90)],
                "output": output or "전체 내용 보기에서 세부 결과물을 확인하세요.",
            }
        )
    return steps[:3]


def build_openai_roadmap_payload(raw_text: str) -> dict:
    return {
        "summary": summarize_roadmap_text(raw_text),
        "steps": parse_roadmap_steps(raw_text),
        "certifications": [],
        "resources": [],
        "strengths": [],
        "raw_text": raw_text,
        "source": "openai",
    }


def extract_chat_completion_text(raw: dict) -> str:
    choices = raw.get("choices") or []
    if not choices:
        return ""
    content = (choices[0].get("message") or {}).get("content") or ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def generate_openai_roadmap(job: dict, profile: dict | None) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되어 있지 않아 로드맵을 생성할 수 없습니다.")

    full_prompt = build_test_roadmap_prompt(job, profile)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": full_prompt},
            {"role": "user", "content": "나를 위한 직무 전환 및 취업 로드맵을 작성해줘."},
        ],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
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
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        message = error_body or getattr(exc, "reason", "") or str(exc)
        raise HTTPException(status_code=502, detail=f"OpenAI 로드맵 생성 요청에 실패했습니다: {message[:300]}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI 로드맵 생성 요청에 실패했습니다: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="OpenAI 응답을 해석하지 못했습니다.") from exc

    text = extract_chat_completion_text(raw)
    if not text:
        raise HTTPException(status_code=502, detail="OpenAI 응답에서 로드맵 텍스트를 찾지 못했습니다.")
    return build_openai_roadmap_payload(text)


def generate_roadmap(job: dict, profile: dict | None) -> dict:
    return generate_openai_roadmap(job, profile)


HOME_HTML = """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>노비Job아라 Prototype</title>
  <link rel="stylesheet" href="/static/app.css?v=dashboard-20260429-drawer">
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
  <div class="roadmap-drawer-backdrop is-hidden" id="roadmap-drawer-backdrop"></div>
  <aside class="roadmap-drawer is-hidden" id="roadmap-drawer" aria-hidden="true" aria-labelledby="roadmap-drawer-title">
    <div class="roadmap-drawer-head">
      <div>
        <p class="eyebrow">전체 로드맵</p>
        <h2 id="roadmap-drawer-title">선택 직무 로드맵</h2>
        <div class="drawer-meta" id="roadmap-drawer-meta"></div>
      </div>
      <button class="drawer-close-btn" id="roadmap-drawer-close" type="button" aria-label="전체 로드맵 닫기">닫기</button>
    </div>
    <pre class="roadmap-full-text" id="roadmap-drawer-body"></pre>
  </aside>
  <script src="/static/app.js?v=dashboard-20260429-drawer"></script>
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
