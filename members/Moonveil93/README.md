# 개인 프로젝트: Moonveil93

> 이 디렉토리는 **Moonveil93** 의 개인 작업 공간입니다.

## 프로젝트 설명

### 📜 노비 JOB 아라 (Nobi JOB Ara)
조선시대를 배경으로 한 초개인화 직무 전환 및 취업 로드맵 제안 서비스입니다. 사용자의 직업선호도검사(L형) 결과 PDF를 분석하여 가장 적합한 직무를 추천하고, AI 대감이 개인별 맞춤형 커리어 로드맵을 작성해 줍니다.

### 🚀 주요 기능
1. **문서 바치기 (PDF 분석)**: 워크넷 직업선호도검사(L형) 결과지를 업로드하면 흥미 유형(RIASEC) 점수를 자동으로 추출합니다.
2. **⚖️ RIASEC 시각적 분석 UI**: 
   - 사용자의 상대적 강점을 한눈에 보여주는 **게이지 바(Bar Chart)** 형태의 UI를 적용했습니다.
   - 상위 3개 흥미 코드 조합과 대표 유형을 '인장(Seal)' 스타일의 박스로 강조했습니다.
3. **관아의 방보 (직무 추천)**: 추출된 점수와 직무 데이터베이스를 비교하여 상위 10개 직무를 추천합니다.
4. **📜 직무 상세 정보 확인**: 추천 목록에서 직무를 클릭하면 해당 직무의 상세 정의와 정보를 먼저 읽어볼 수 있습니다.
5. **🔍 직무 검색 시스템**: 사용자가 직접 원하는 직무를 검색하여 정보와 AI 로드맵을 확인할 수 있습니다.
6. **🗺️ 지능형 로드맵 UI**: 
   - 가로 슬라이드 방식으로 시각적 편의성을 높였습니다.
   - 로직 개선을 통해 타이틀 자동 보정 및 출력 최적화를 수행합니다.
7. **신분 상승의 길 (AI 로드맵)**: 선택한 직무와 사용자의 전공 여부를 바탕으로 OpenAI GPT-4o-mini 모델이 3단계 맞춤형 취업 로드맵을 생성합니다.

### 🛠 기술 스택
- **Backend**: FastAPI (Python 3.10+)
- **Frontend**: HTML5, Vanilla JS, CSS3 (NES.css 라이브러리 활용)
- **AI**: OpenAI API (GPT-4o-mini)
- **Data Analysis**: Pandas, NumPy, Scikit-learn
- **PDF Processing**: PyPDF

## 디렉토리 구조

```
.
├── .env                       ← API 키 설정 파일
├── main.py                    ← 메인 서버 코드 (FastAPI)
├── app.py                     ← 백엔드 로직
├── 잡코리아_Onet통합본_직무정보추가.csv ← 직무 데이터베이스
├── NCS_All_Job_Descriptions.csv ← NCS 직무 정보
├── DEVLOG.md                  ← 변경사항 기록
├── README.md                  ← 이 파일
├── static/                    ← 프론트엔드 정적 파일
└── 직무 데이터/               ← 데이터 분석 및 크롤링 스크립트
```

## 실행 방법

```bash
# 필요한 라이브러리 설치
pip install fastapi uvicorn pandas numpy python-dotenv pypdf openai

# 서버 실행
python main.py
```

## 변경 이력

[DEVLOG.md](DEVLOG.md) 참조
