const dialogues = {
    2: "어서오거라! 관아에서 받아온 네놈의 자질 문서(PDF)를 보여다오!",
    3: "오호, 너의 기질을 해독해 보았느니라.\n한번 확인해 보겠느냐?",
    4: "방보를 확인하시게. 자네에게 제일 잘 맞을 것 같은 10가지의 일거리 라네.\n어떤일을 하기를 원하는가? 하나 선택해 보게나.",
    5: "호오, 그 일을 해보려는가? \n그렇다면 관련된 학문(전공)은 접해본 적이 있는가?",
    7: "이 직무가 어떤 일을 하는지 자세히 읽어보게나. 마음에 드는가?"
};

let selectedJob = null; // 선택한 직무 저장
let tempRecommendations = []; // 추천 데이터를 임시 저장

function typeWriter(text, elementId, callback) {
    let i = 0;
    const element = document.getElementById(elementId);
    element.innerHTML = "";
    function type() {
        if (i < text.length) {
            if (text.charAt(i) === '\n') {
                element.innerHTML += '<br>';
            } else {
                element.innerHTML += text.charAt(i);
            }
            i++;
            setTimeout(type, 30); // 타이핑 속도 조절
        } else if (callback) {
            callback();
        }
    }
    type();
}

function nextPhase(phaseNum) {
    document.querySelectorAll('.phase').forEach(p => p.classList.remove('active'));
    const currentPhase = document.getElementById(`phase-${getPhaseId(phaseNum)}`);
    currentPhase.classList.add('active');

    // 입력/버튼 영역 숨기기 (타이핑 끝난 후 표시)
    const actionArea = document.getElementById(`action-${phaseNum}`);
    if(actionArea) actionArea.classList.add('hidden');

    if (dialogues[phaseNum]) {
        typeWriter(dialogues[phaseNum], `typewriter-${phaseNum}`, () => {
            if(actionArea) actionArea.classList.remove('hidden');
        });
    }
}

function getPhaseId(num) {
    return ["", "intro", "upload", "scores", "results", "major", "roadmap", "job-detail"][num];
}

// 📌 API 호출: PDF 업로드
async function handleUpload() {
    const fileInput = document.getElementById('pdf-input');
    if (!fileInput.files.length) {
        alert("문서를 선택해 주시게!");
        return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    document.getElementById('typewriter-2').innerText = "열심히 문서를 해독 중이옵니다... 잠시만 기다려 주시옵소서.";
    document.getElementById('action-2').classList.add('hidden');

    try {
        const response = await fetch('/api/upload_pdf', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            tempRecommendations = data.recommendations; // 추천 데이터 보관
            renderScores(data.scores);                 // 점수 화면 그리기
            nextPhase(3);                             // 점수 확인 단계(scores)로 이동
        } else {
            alert("오류 발생: " + data.message);
            document.getElementById('action-2').classList.remove('hidden');
        }
    } catch (error) {
        alert("서버 연결 실패!");
    }
}

// 점수를 화면에 그리는 함수
function renderScores(scores) {
    const RL = [
        { name: "현실형", k: "R" },
        { name: "탐구형", k: "I" },
        { name: "예술형", k: "A" },
        { name: "사회형", k: "S" },
        { name: "진취형", k: "E" },
        { name: "관습형", k: "C" }
    ];
    
    // API 데이터에서 표준점수 추출 및 매핑
    const stdScores = {
        "R": scores["현실형"]?.표준점수 || 0,
        "I": scores["탐구형"]?.표준점수 || 0,
        "A": scores["예술형"]?.표준점수 || 0,
        "S": scores["사회형"]?.표준점수 || 0,
        "E": scores["진취형"]?.표준점수 || 0,
        "C": scores["관습형"]?.표준점수 || 0
    };

    /* --- 막대 그래프(게이지 바) 생성 부분 --- */
    const maxStd = Math.max(...RL.map(l => stdScores[l.k] || 0), 1);
    document.getElementById('barsDiv').innerHTML = RL.map(l => {
      const v = stdScores[l.k] || 0;
      const pct = Math.round((v / maxStd) * 100);
      return `<div class="bar-row">
        <div class="bar-label">${l.name}(${l.k})</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        <div class="bar-val">${v}</div>
      </div>`;
    }).join('');

    /* --- 하단 흥미 코드 및 성향 텍스트 생성 부분 --- */
    const sorted = [...RL].sort((a, b) => (stdScores[b.k] || 0) - (stdScores[a.k] || 0));
    const t3 = sorted.slice(0, 3).map(l => l.k).join('');
    const repCode = sorted[0].k; // 가장 높은 점수의 코드를 대표코드로 설정

    document.getElementById('top3Div').innerHTML = `
        <div class="seal-box">
            흥미 코드 ${t3} — <strong>${sorted[0].name}</strong> 성향 (대표코드: ${repCode})
        </div>`;
}

// 점수 확인 후 추천 페이지로 넘어가는 함수
function goToRecommendations() {
    renderJobList(tempRecommendations); // 보관해둔 데이터로 목록 생성
    nextPhase(4);                      // 결과 확인 단계(results)로 이동
}

// 직무 상세 정보를 화면에 그리는 함수
function showJobDetail(job, fromPhase) {
    selectedJob = job;
    
    // 제목 및 내용 설정
    document.getElementById('detail-title').innerText = `📜 ${job.JK중분류} 상세 정보`;
    
    // 직무정보 텍스트 가공 (줄바꿈 등)
    const infoText = job.직무정보 ? job.직무정보.replace(/\n/g, '<br>') : "상세 정보가 없사옵니다.";
    document.getElementById('detail-content').innerHTML = infoText;
    
    // '다시 목록으로' 버튼 동작 설정
    const backBtn = document.getElementById('back-to-list-btn');
    backBtn.onclick = () => nextPhase(fromPhase);
    
    // 상세 페이지(Phase 7)로 이동
    nextPhase(7);
}

// 방보(결과) 리스트 그리기
function renderJobList(jobs) {
    const container = document.getElementById('job-list');
    container.innerHTML = "";
    
    jobs.forEach((job, index) => {
        const btn = document.createElement('button');
        btn.className = "nes-btn";
        btn.style.display = "block";
        btn.style.width = "100%";
        btn.style.marginBottom = "10px";
        btn.style.textAlign = "left";
        btn.innerText = `${index + 1}. ${job.JK중분류} (일치율: ${Math.round(job.최종유사도 * 100)}%)`;
        
        btn.onclick = () => {
            showJobDetail(job, 4); // 상세 페이지로 이동
        };
        container.appendChild(btn);
    });
}

// 📌 API 호출: AI 로드맵 생성
async function showRoadmap(answer) {
    if (!selectedJob) {
        alert("선택된 직무가 없사옵니다!");
        return;
    }

    // 1. 대화창 텍스트 변경 및 버튼 숨기기
    document.getElementById('typewriter-5').innerText = "AI 대감이 맞춤형 신분 상승의 길을 점치고 있사옵니다...\n잠시만 기다려 주시옵소서.";
    document.getElementById('action-5').classList.add('hidden');

    // 2. 백엔드로 보낼 데이터 준비
    const requestData = {
        job_name: selectedJob.JK중분류,
        is_major_required: selectedJob.전공필수 === 'O',
        user_major_status: answer 
    };

    try {
        // 3. FastAPI 백엔드 호출
        const response = await fetch('/api/roadmap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const data = await response.json();

        // --- 4. 성공 시 로직 교체 시작 ---
if (data.status === 'success') {
    nextPhase(6); // roadmap 단계로 이동
    const container = document.getElementById('roadmap-content');
    container.innerHTML = ""; // 기존 내용 초기화
    container.style.transform = "translateX(0)"; // 슬라이드 위치 초기화
    currentSlide = 0;

    const rawText = data.roadmap;

    // 🌟 1. 더 강력한 정규식으로 텍스트 분리 ('■', '###', '1단계' 등 어떤 형식이든 잘라냄)
    const sections = rawText.split(/(?=(?:■|#|\*)*\s*\d+단계)/g)
                             .map(s => s.trim())
                             .filter(s => s.length > 20); // 20자 미만의 짧은 기호나 빈 줄은 버림
    
     // 2. 만약 첫 번째 조각(도입부)이 너무 짧으면 두 번째 조각(1단계)과 합치기
     if (sections.length > 1 && !sections[0].includes("1단계") && sections[0].length < 100) {
         sections[1] = sections[0] + "\n\n" + sections[1];
         sections.shift();
    }
    // 전체 슬라이드 개수 설정
    totalSlides = sections.length;
    updateSlideButtons(); // 화살표 버튼 상태 갱신

    sections.forEach(section => {
        const lines = section.trim().split('\n');
        
        // 2. 제목과 본문 분리 (N단계 패턴을 최우선으로 확인)
        let titleText = "";
        let bodyContent = "";

        // '숫자단계' 패턴 찾기 (문장 중간에 있어도 찾을 수 있도록 g 옵션 없이 match)
        const stepMatch = section.match(/(\d+)단계[:\s]*(.*)/);

        if (stepMatch) {
            // 단계 정보가 발견되면 '제N관문' 타이틀 부여
            titleText = `제${stepMatch[1]}관문: ${stepMatch[2].split('\n')[0].trim()}`;
            // 특수기호 제거
            titleText = titleText.replace(/^[■#*]+\s*/, ''); 
            
            // 본문에서 제목으로 쓰인 첫 줄(단계 선언부) 제거 후 가공
            const firstLineIndex = section.indexOf(stepMatch[0]);
            const remainingText = section.substring(firstLineIndex + stepMatch[0].length).trim();
            
            bodyContent = remainingText.replace(/\n/g, '<br>')
                                       .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        } else {
            // 단계 정보가 없는 경우에만 도입부 타이틀 부여
            titleText = "📜 입신양명 비기";
            bodyContent = section.replace(/^[■#*]+\s*/g, '')
                                 .replace(/\n/g, '<br>')
                                 .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        }

        // 3. NES.css 컨테이너(카드) 동적 생성
        const stageDiv = document.createElement('div');
        stageDiv.className = "nes-container with-title is-dark roadmap-stage-card";
        
        const titleP = document.createElement('p');
        titleP.className = "title";
        titleP.innerText = titleText;
        
        const contentP = document.createElement('p');
        contentP.innerHTML = bodyContent;

        stageDiv.appendChild(titleP);
        stageDiv.appendChild(contentP);
        container.appendChild(stageDiv);
    });

    // 1. 전체 페이지 수 1 증가 (검색 슬라이드 포함)
    totalSlides++; 

    // 2. 검색용 마지막 슬라이드 생성
    const searchStage = document.createElement('div');
    searchStage.className = "nes-container with-title is-dark roadmap-stage-card";

    searchStage.innerHTML = `
        <p class="title">🔍 다른 길 찾기</p>
        <p>혹시 다른 직무의 로드맵이 궁금하신가?</p>
        <div class="nes-field is-inline" style="margin-top: 20px;">
            <input type="text" id="search-input" class="nes-input" placeholder="직무명을 입력하게...">
            <button type="button" class="nes-btn is-primary" onclick="handleSearch()">검색</button>
        </div>
        <div id="search-results" class="job-list-container" style="margin-top: 15px; max-height: 300px; overflow-y: auto;">
            <!-- 검색 결과 버튼들이 여기에 표시됨 -->
        </div>
    `;

    container.appendChild(searchStage);
    updateSlideButtons(); // 버튼 상태 최종 갱신
} 
// --- 성공 시 로직 교체 끝 ---
        
        else {
            alert("오류 발생: " + data.message);
            document.getElementById('action-5').classList.remove('hidden');
            document.getElementById('typewriter-5').innerText = "호오, 그 길을 가려무나?\n그렇다면 네 이놈, 이 직무와 관련된 학문(전공)을 닦았느냐?";
        }
    } catch (error) {
        console.error(error);
        alert("서버 연결 실패! AI 대감이 응답하지 않습니다.");
        document.getElementById('action-5').classList.remove('hidden');
    }
}

// 📌 슬라이더 제어 로직
let currentSlide = 0;
let totalSlides = 0;

function moveSlide(direction) {
    const container = document.getElementById('roadmap-content');
    const slideWidth = document.querySelector('.roadmap-stage-card').offsetWidth + 20; // 카드 너비 + 간격

    currentSlide += direction;
    if (currentSlide < 0) currentSlide = 0;
    if (currentSlide >= totalSlides) currentSlide = totalSlides - 1;

    container.style.transform = `translateX(-${currentSlide * slideWidth}px)`;
    updateSlideButtons();
}

function updateSlideButtons() {
    const prevBtn = document.querySelector('.slide-prev');
    const nextBtn = document.querySelector('.slide-next');

    if (prevBtn) prevBtn.disabled = (currentSlide === 0);
    if (nextBtn) nextBtn.disabled = (currentSlide >= totalSlides - 1 || totalSlides === 0);
}

// 📌 API 호출: 직무 검색
async function handleSearch() {
    const query = document.getElementById('search-input').value;
    if (!query) {
        alert("검색어를 입력하시게!");
        return;
    }

    try {
        const response = await fetch(`/api/search_job?query=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (data.status === 'success') {
            const container = document.getElementById('search-results');
            container.innerHTML = "";
            
            if (data.results.length === 0) {
                container.innerHTML = "<p>그런 직무는 없사옵니다...</p>";
                return;
            }

            data.results.forEach(job => {
                const btn = document.createElement('button');
                btn.className = "nes-btn is-primary";
                btn.style.display = "block";
                btn.style.width = "100%";
                btn.style.marginBottom = "10px";
                btn.innerText = job.JK중분류;
                btn.onclick = () => {
                    showJobDetail(job, 6); // 상세 페이지로 이동
                };
                container.appendChild(btn);
            });
        }
    } catch (error) {
        alert("검색 중 오류가 발생했사옵니다.");
    }
}
