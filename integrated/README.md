# 노비 Job아라

직업선호도검사 결과와 직무 데이터를 기반으로 사용자에게 적합한 직무를 추천하고, AI 로드맵과 RAG 챗봇 상담을 제공하는 진로/취업 로드맵 웹 서비스입니다.

조선시대 관아 콘셉트의 픽셀아트 UI를 사용하며, 사용자는 PDF 업로드 또는 직무 직접 검색을 통해 직무 정보, 추천 결과, 맞춤형 로드맵, 상담 기록을 확인할 수 있습니다.

## 팀 정보

- 팀명: 노비 Job아라

| 이름 | GitHub ID | 역할 | 디렉토리 |
|------|-----------|------|----------|
| 유시연 | sini1325 | 팀장 | 'members/sini1325/' |
| 김명균 | Moonveil93 | 팀원 | 'members/Moonveil93/' |
| 권유민 | yu-m-n | 팀원 | 'members/yu-m-n/' |
| 안성민 | CECode | 팀원 | 'members/CECode/' |

## 주요 기능

1. **신분 인증 (Google 소셜 로그인)**: 
   - Supabase Auth를 연동하여 Google 계정으로 간편하게 로그인하고 본인의 데이터를 관리할 수 있습니다.
2. **📜 나만의 비기 저장 (데이터 영구 보존)**: 
   - 생성된 AI 로드맵과 RIASEC 점수를 Supabase DB에 자동으로 저장합니다.
   - '나의 기록' 메뉴를 통해 과거에 생성했던 로드맵을 언제든 다시 꺼내 볼 수 있습니다.
3. **🗑️ 기록 관리 (삭제 기능)**: 
   - 불필요하거나 잘못 생성된 로드맵 기록을 직접 삭제하여 목록을 정리할 수 있습니다.
4. **🏠 원클릭 귀환 (처음으로 돌아가기)**: 
   - 로드맵 확인 후 첫 화면으로 즉시 돌아갈 수 있는 내비게이션 기능을 추가하여 사용성을 개선했습니다.
5. **문서 바치기 (PDF 분석 및 가이드)**: 
   - 워크넷 직업선호도검사(L형) 결과지를 업로드하면 흥미 유형(RIASEC) 점수를 자동으로 추출합니다.
   - 처음 방문하는 사용자를 위해 고용24 검사 방법 및 PDF 다운로드 안내 가이드를 대화창에 추가했습니다.
6. **⚖️ RIASEC 시각적 분석 UI**: 
   - 사용자의 상대적 강점을 한눈에 보여주는 **게이지 바(Bar Chart)** 형태의 UI를 적용했습니다.
   - 상위 3개 흥미 코드 조합과 대표 유형을 '인장(Seal)' 스타일의 박스로 강조했습니다.
7. **관아의 방보 (직무 추천)**: 추출된 점수와 직무 데이터베이스를 비교하여 상위 10개 직무를 추천합니다.
8. **📜 직무 상세 정보 확인**: 추천 목록에서 직무를 클릭하면 해당 직무의 상세 정의와 정보를 먼저 읽어볼 수 있습니다.
9. **🔍 하이브리드 직무 접근 시스템**: 
   - **PDF 기반 추천**: 자질 문서를 바치면 기질에 맞는 직무를 추천받습니다.
   - **직접 검색**: 대화창 우측의 검색창을 통해 원하는 직무를 직접 검색하여 정보와 로드맵을 즉시 확인할 수 있습니다. (플로팅 팝업창 UI 적용)
10. **🗺️ 지능형 로드맵 UI & 강력한 파싱**: 
   - **가로 슬라이드 방식**: % 기반 이동 로직을 적용하여 화면 크기에 관계없이 1px의 오차 없는 정밀한 슬라이딩을 구현했습니다.
   - **3단 정보 구획화**: AI가 생성한 로드맵을 '본문', '결과물(아이템)', '현실적 Tip(비법)'으로 자동 분류하여 가독성을 극대화했습니다.
   - **마크다운 호환 파싱**: AI가 사용하는 볼드(`**`), 특수 기호, 아이콘 등이 다른 구역으로 새어나가지 않도록 탐욕적 정규식과 청소 로직을 적용하여 완벽한 데이터 분리를 실현했습니다.
   - **구조적 안정성**: `div` 기반의 유연한 컨테이너 구조를 채택하여 스크롤 발생 시에도 레이아웃이 붕괴되지 않습니다.
11. **신분 상승의 길 (AI 로드맵)**: OpenAI GPT-4o-mini 모델이 사용자의 직무와 전공 상태를 분석하여 초개인화된 3단계 취업 성공 비기를 하사합니다.
12. **💬 LangChain RAG 지능형 AI 대감 챗봇 (상담 고도화)**: 
   - **Vector DB 기반 지식 검색**: 수천 개의 직무 데이터를 벡터화하여 질문에 가장 적합한 정보를 실시간으로 추출하여 답변의 전문성을 극대화했습니다.
   - **데이터 기반 적합성 분석**: 사용자의 실제 RIASEC 점수와 직무 요구 역량을 수치적으로 정밀하게 대조하여 날카로운 분석을 하사합니다.
   - **맞춤형 대안 제시**: 현재 직무가 맞지 않을 경우, 사용자의 기질 강점을 극대화할 수 있는 최적의 다른 일거리를 DB에서 찾아 실시간으로 역제안합니다.
   - **조선시대 페르소나**: 15년 경력의 베테랑 컨설턴트 'AI 대감' 페르소나를 적용하여, 엄중하고 호탕한 말투로 고품격 상담을 제공합니다.
13. **🔥 기록 일괄 소각 (전체 삭제)**: 
   - '나의 기록' 메뉴에서 쌓인 모든 비기를 한 번에 삭제할 수 있는 기능을 추가하여 데이터 관리 편의성을 극대화했습니다.
   - 실수 방지를 위한 이중 확인 시스템을 적용했습니다.
15. **실시간 스트리밍 답변 (Streaming Response)**: 
   - 챗봇의 응답을 한 번에 보여주지 않고, 생성되는 즉시 한 글자씩 출력하는 스트리밍 방식을 적용했습니다.
   - 사용자에게 실제 대화하는 듯한 생동감을 제공하며 대기 시간을 시각적으로 단축시켰습니다.
16. **안정적인 하이브리드 통신**: 기본 기능은 `urllib` 기반 REST 통신을, 고도화된 AI 상담은 `LangChain` 프레임워크를 활용하여 안정성과 기능성을 동시에 확보했습니다.


## 기술 스택

<details>
<summary>🛠 사용 기술 스택 펼쳐보기</summary>

<br>

<div align="center">

### Backend
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#E8F5F2; color:#009688; font-weight:700; border:1px solid #B2DFDB;">FastAPI</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EAF2FF; color:#3776AB; font-weight:700; border:1px solid #BBD7FF;">Python</span>

### Frontend
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#FFF0E8; color:#E34F26; font-weight:700; border:1px solid #FFD0BD;">HTML5</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EAF2FF; color:#1572B6; font-weight:700; border:1px solid #BBD7FF;">CSS3</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#FFF9D7; color:#9A7B00; font-weight:700; border:1px solid #F7DF1E;">Vanilla JavaScript</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#FFF6D8; color:#8A6D00; font-weight:700; border:1px solid #FFD966;">NES.css</span>

### Database / Auth
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#E9FFF4; color:#2E9F6E; font-weight:700; border:1px solid #B7F3D2;">Supabase PostgreSQL</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#E9FFF4; color:#2E9F6E; font-weight:700; border:1px solid #B7F3D2;">Supabase Auth</span>

### Vector Search
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EEF4FF; color:#336791; font-weight:700; border:1px solid #C8D8F0;">pgvector</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#E9FFF4; color:#2E9F6E; font-weight:700; border:1px solid #B7F3D2;">Supabase RPC</span>

### AI / LLM
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#F0ECFF; color:#412991; font-weight:700; border:1px solid #D5C9FF;">OpenAI API</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EAF7F4; color:#1C3C3C; font-weight:700; border:1px solid #BFE4DD;">LangChain</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#F0ECFF; color:#412991; font-weight:700; border:1px solid #D5C9FF;">OpenAI Embeddings</span>

### PDF / Data
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EAF2FF; color:#3776AB; font-weight:700; border:1px solid #BBD7FF;">pypdf</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#F0EEFF; color:#150458; font-weight:700; border:1px solid #D5D0FF;">pandas</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EAF5FF; color:#013243; font-weight:700; border:1px solid #B8DFFF;">NumPy</span>

### Deploy / Runtime
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EAF2FF; color:#4285F4; font-weight:700; border:1px solid #C7D9FF;">Google Cloud Run</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EAF6FF; color:#2496ED; font-weight:700; border:1px solid #B9E0FF;">Docker</span>
<span style="display:inline-block; padding:8px 14px; margin:4px; border-radius:999px; background:#EEF9EA; color:#499848; font-weight:700; border:1px solid #C9EBC4;">Uvicorn</span>

</div>

</details>

## 동작 구조

```text
사용자 로그인
  -> PDF 업로드 또는 직무 직접 검색
  -> RIASEC 점수 추출 및 직무 데이터 조회
  -> 추천 직무 / 직무 상세 정보 표시
  -> AI 로드맵 생성
  -> Supabase에 로드맵 및 채팅 세션 저장
  -> LangChain RAG 챗봇으로 추가 상담
```
```
이미지 넣을 구간
```

RAG 챗봇은 사용자의 질문을 임베딩한 뒤 Supabase의 `match_jobs` RPC를 호출해 `JK_job` 테이블의 직무 데이터를 검색합니다. 검색된 직무 정보, 사용자의 RIASEC 점수, 생성된 로드맵, 이전 대화 내용을 프롬프트에 함께 넣어 LangChain 기반 스트리밍 답변을 생성합니다.

## 디렉터리 구조

```text
.
├── src/
│   ├── main.py              # FastAPI 서버, API 라우트, AI/RAG 로직
│   └── static/
│       ├── index.html       # 메인 화면
│       ├── script.js        # 프론트엔드 동작 로직
│       ├── style.css        # 전체 스타일 및 반응형 UI
│       └── assets/          # 화면 이미지 및 버튼 이미지
├── requirements.txt         # Python 패키지 목록
├── environment.yml          # Conda 환경 설정 파일
├── Dockerfile               # 컨테이너 실행 설정
├── DEVLOG.md                # 개발 기록
└── README.md
```

## 환경 변수 설정

`src/.env` 파일을 생성하고 아래 변수명을 채워 사용합니다. README에는 실제 키 값을 넣지 않습니다.

```env
OPENAI_API_KEY=
OPENAI_MODEL=

SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

참고 사항:

- `SUPABASE_SERVICE_ROLE_KEY`는 서버에서만 사용해야 하며 프론트엔드에 노출하면 안 됩니다.
- 기존 설정에 따라 `SUPABASE_ANON_KEY`, `SUPABASE_KEY`를 사용하는 경우가 있다면 동일하게 실제 값은 `.env`에만 작성합니다.
- `.env` 파일은 Git에 커밋하지 않습니다.

## Supabase 준비 사항

프로젝트 실행 전 Supabase에 아래 구성이 필요합니다.

- `JK_job` 테이블: 직무 정보, RIASEC 점수, 직무 설명, 임베딩 저장
- `user_roadmaps` 테이블: 사용자별 생성 로드맵 저장
- `chat_threads` 테이블: 직무별 채팅 스레드 저장
- `chat_sessions` 테이블: 로드맵별 채팅 세션 저장
- `chat_messages` 테이블: 사용자와 AI의 채팅 메시지 저장
- `pgvector` 확장
- `match_jobs` RPC 함수
- 사용자 데이터 보호를 위한 RLS 정책

생성 SQL은 [supabase_schema.sql](supabase_schema.sql)에 정리되어 있습니다.

## 설치 및 실행

CECode-env 환경을 사용하는 경우:

```bash
conda activate CECode-env
pip install -r requirements.txt
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

브라우저에서 아래 주소로 접속합니다.

```text
http://127.0.0.1:8000
```

새 환경을 만드는 경우 Python 3.11 기반 환경을 권장합니다.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```

## 주요 API

- `GET /healthz`: 서버 상태 확인
- `GET /`: 메인 페이지 반환
- `GET /api/supabase_config`: 프론트엔드용 Supabase 공개 설정 반환
- `POST /api/upload_pdf`: PDF 업로드 및 RIASEC 점수 추출
- `GET /api/latest_riasec_scores`: 최근 RIASEC 점수 조회
- `GET /api/search_job`: 직무 검색
- `POST /api/roadmap`: AI 로드맵 생성 및 저장
- `POST /api/roadmap_chat`: LangChain RAG 챗봇 스트리밍 상담
- `GET /api/my_roadmaps`: 내 로드맵 기록 조회
- `DELETE /api/delete_roadmap/{roadmap_id}`: 로드맵 개별 삭제
- `POST /api/delete_roadmaps`: 로드맵 선택 삭제

## 개발 확인 명령

```bash
python -m py_compile src/main.py
node --check src/static/script.js
```

외부 API를 사용하는 기능은 OpenAI와 Supabase 환경 변수가 올바르게 설정되어 있어야 정상 동작합니다.

## 변경 기록

자세한 변경 내역은 [DEVLOG.md](DEVLOG.md)를 참고합니다.
