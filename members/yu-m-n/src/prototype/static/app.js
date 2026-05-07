// ==========================================
// 🔑 Supabase 인증 로직
// ==========================================

// ⚠️ Supabase 대시보드에서 Project URL과 anon public 키를 복사해서 아래에 넣으세요!
const SUPABASE_URL = 'https://당신의-프로젝트-고유주소.supabase.co';
const SUPABASE_ANON_KEY = '당신의-엄청나게-긴-anon-public-키';

const supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// 페이지 로드 시 현재 로그인 상태 확인
window.onload = async () => {
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (session) {
        nextPhase(1); // 로그인 되어있으면 인트로 화면으로
    } else {
        nextPhase(0); // 안되어있으면 로그인 화면으로
    }
};

function showAuthMsg(msg) {
    document.getElementById('auth-msg').innerText = msg;
}

// 회원가입
async function handleSignup() {
    const email = document.getElementById('email-input').value;
    const password = document.getElementById('password-input').value;
    if (!email || !password) return showAuthMsg("이메일과 비밀번호를 입력해주세요.");

    showAuthMsg("호패 발급 중...");
    const { data, error } = await supabaseClient.auth.signUp({ email, password });
    if (error) {
        showAuthMsg("발급 실패: " + error.message);
    } else {
        showAuthMsg("성공! 이메일을 확인하거나 바로 출입(로그인)을 누르세요.");
    }
}

// 로그인
async function handleLogin() {
    const email = document.getElementById('email-input').value;
    const password = document.getElementById('password-input').value;
    if (!email || !password) return showAuthMsg("이메일과 비밀번호를 입력해주세요.");

    showAuthMsg("신분 확인 중...");
    const { data, error } = await supabaseClient.auth.signInWithPassword({ email, password });
    if (error) {
        showAuthMsg("출입 불가: " + error.message);
    } else {
        showAuthMsg("");
        nextPhase(1); // 로그인 성공 시 인트로 화면으로
    }
}

// 로그아웃
async function handleLogout() {
    await supabaseClient.auth.signOut();
    document.getElementById('email-input').value = '';
    document.getElementById('password-input').value = '';
    nextPhase(0);
}

// ==========================================
// 🎮 기존 게임 로직 
// ==========================================

const dialogues = {
    2: "어서오거라! 관아에서 받아온 네놈의 자질 문서(PDF)를 보여다오!\n(고용24 직업선호도검사 L형 설문을 완료 후 PDF 결과지를 다운 받아 첨부해주세요.)",
    3: "오호, 너의 기질을 해독해 보았느니라.\n한번 확인해 보겠느냐?",
    4: "방보를 확인하시게. 자네에게 제일 잘 맞을 것 같은 10가지의 일거리 라네.\n어떤일을 하기를 원하는가? 하나 선택해 보게나.",
    5: "호오, 그 일을 해보려는가? \n그렇다면 관련된 학문(전공)은 접해본 적이 있는가?",
    7: "이 직무가 어떤 일을 하는지 자세히 읽어보게나. 마음에 드는가?"
};

let selectedJob = null; 
let tempRecommendations = []; 

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
            setTimeout(type, 30); 
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

    const actionArea = document.getElementById(`action-${phaseNum}`);
    if(actionArea) actionArea.classList.add('hidden');

    if (dialogues[phaseNum]) {
        typeWriter(dialogues[phaseNum], `typewriter-${phaseNum}`, () => {
            if(actionArea) actionArea.classList.remove('hidden');
        });
    }
}

// 0번(login)을 추가하여 phase ID 반환
function getPhaseId(num) {
    return ["login", "intro", "upload", "scores", "results", "major", "roadmap", "job-detail"][num];
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
            tempRecommendations = data.recommendations; 
            renderScores(data.scores);                 
            nextPhase(3);                             
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
    
    const stdScores = {
        "R": scores["현실형"]?.표준점수 || 0,
        "I": scores["탐구형"]?.표준점수 || 0,
        "A": scores["예술형"]?.표준점수 || 0,
        "S": scores["사회형"]?.표준점수 || 0,
        "E": scores["진취형"]?.표준점수 || 0,
        "C": scores["관습형"]?.표준점수 || 0
    };

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

    const sorted = [...RL].sort((a, b) => (stdScores[b.k] || 0) - (stdScores[a.k] || 0));
    const t3 = sorted.slice(0, 3).map(l => l.k).join('');
    const repCode = sorted[0].k; 

    document.getElementById('top3Div').innerHTML = `
        <div class="seal-box">
            흥미 코드 ${t3} — <strong>${sorted[0].name}</strong> 성향 (대표코드: ${repCode})
        </div>`;
}

function goToRecommendations() {
    renderJobList(tempRecommendations); 
    nextPhase(4);                      
}

function showJobDetail(job, fromPhase) {
    selectedJob = job;
    document.getElementById('detail-title').innerText = `📜 ${job.JK중분류} 상세 정보`;
    
    const infoText = job.직무정보 ? job.직무정보.replace(/\n/g, '<br>') : "상세 정보가 없사옵니다.";
    document.getElementById('detail-content').innerHTML = infoText;
    
    const backBtn = document.getElementById('back-to-list-btn');
    backBtn.onclick = () => nextPhase(fromPhase);
    
    nextPhase(7);
}

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
            showJobDetail(job, 4); 
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

    document.getElementById('typewriter-5').innerText = "AI 대감이 맞춤형 신분 상승의 길을 점치고 있사옵니다...\n잠시만 기다려 주시옵소서.";
    document.getElementById('action-5').classList.add('hidden');

    const requestData = {
        job_name: selectedJob.JK중분류,
        is_major_required: selectedJob.전공필수 === 'O',
        user_major_status: answer 
    };

    try {
        const response = await fetch('/api/roadmap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        });

        const data = await response.json();

        if (data.status === 'success') {
            nextPhase(6); 
            const container = document.getElementById('roadmap-content');
            container.innerHTML = ""; 
            container.style.transform = "translateX(0)"; 
            currentSlide = 0;

            const rawText = data.roadmap;

            const sections = rawText.split(/(?=(?:■|#|\*)*\s*\d+단계)/g)
                                     .map(s => s.trim())
                                     .filter(s => s.length > 20); 
            
             if (sections.length > 1 && !sections[0].includes("1단계") && sections[0].length < 100) {
                 sections[1] = sections[0] + "\n\n" + sections[1];
                 sections.shift();
            }
            totalSlides = sections.length;
            updateSlideButtons(); 

            sections.forEach(section => {
                let titleText = "";
                let bodyContent = "";

                const stepMatch = section.match(/(\d+)단계[:\s]*(.*)/);

                if (stepMatch) {
                    titleText = `제${stepMatch[1]}관문: ${stepMatch[2].split('\n')[0].trim()}`;
                    titleText = titleText.replace(/^[■#*]+\s*/, ''); 
                    
                    const firstLineIndex = section.indexOf(stepMatch[0]);
                    let remainingText = section.substring(firstLineIndex + stepMatch[0].length).trim();
                    
                    let descText = remainingText;
                    let resultText = "";
                    let tipText = "";

                    const tipRegex = /(?:[\s\n*#■-]*💡)?[\s\n*#■-]*현실적\s*[Tt]ip[\s\n:*#■-]*/i;
                    const tipMatch = descText.match(tipRegex);
                    if (tipMatch) {
                        const splitIdx = descText.indexOf(tipMatch[0]);
                        tipText = descText.substring(splitIdx + tipMatch[0].length).trim();
                        descText = descText.substring(0, splitIdx).trim();
                    }

                    const resultRegex = /(?:[\s\n*#■-]*📌)?[\s\n*#■-]*결과물[\s\n:*#■-]*/i;
                    const resultMatch = descText.match(resultRegex);
                    if (resultMatch) {
                        const splitIdx = descText.indexOf(resultMatch[0]);
                        resultText = descText.substring(splitIdx + resultMatch[0].length).trim();
                        descText = descText.substring(0, splitIdx).trim();
                    }

                    resultText = resultText.replace(/^[*#■\-\s:]+|[*#■\-\s:]+$/g, "").trim();
                    tipText = tipText.replace(/^[*#■\-\s:]+|[*#■\-\s:]+$/g, "").trim();
                    descText = descText.replace(/[*#■\-\s:]+$/g, "").trim(); 

                    let finalBodyHTML = "";
                    if (descText) {
                        finalBodyHTML += `<div class="roadmap-desc">${descText.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>`;
                    }
                    if (resultText) {
                        finalBodyHTML += `<div class="result-box"><strong style="color:var(--green-jade);">📌 결과물</strong><br>${resultText.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>`;
                    }
                    if (tipText) {
                        finalBodyHTML += `<div class="tip-box"><strong style="color:#B36B00;">💡 현실적 Tip</strong><br>${tipText.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>`;
                    }
                    bodyContent = finalBodyHTML;

                } else {
                    titleText = "📜 입신양명 비기";
                    bodyContent = section.replace(/^[■#*]+\s*/g, '')
                                         .replace(/\n/g, '<br>')
                                         .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                }

                const stageDiv = document.createElement('div');
                stageDiv.className = "nes-container with-title roadmap-stage-card";
                
                const titleP = document.createElement('p');
                titleP.className = "title";
                titleP.innerText = titleText;
                
                const contentP = document.createElement('p');
                contentP.innerHTML = bodyContent;

                stageDiv.appendChild(titleP);
                stageDiv.appendChild(contentP);
                container.appendChild(stageDiv);
            });

            totalSlides++; 

            const searchStage = document.createElement('div');
            searchStage.className = "nes-container with-title roadmap-stage-card";
            searchStage.style.overflow = "hidden";
            
            searchStage.innerHTML = `
                <p class="title">🔍 다른 길 찾기</p>
                <p>혹시 다른 직무의 로드맵이 궁금하신가?</p>
                <div class="nes-field is-inline" style="margin-top: 20px;">
                    <input type="text" id="search-input" class="nes-input" placeholder="직무명을 입력하게...">
                    <button type="button" class="nes-btn" onclick="handleSearch()">검색</button>
                </div>
                <div id="search-results" class="job-list-container" style="margin-top: 15px; max-height: 250px; overflow-y: auto; width: 95%; margin-left: auto; margin-right: auto;">
                </div>
            `;

            container.appendChild(searchStage);
            updateSlideButtons(); 
        } else {
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
    currentSlide += direction;
    if (currentSlide < 0) currentSlide = 0;
    if (currentSlide >= totalSlides) currentSlide = totalSlides - 1;

    container.style.transform = `translateX(-${currentSlide * 100}%)`;
    updateSlideButtons();
}

function updateSlideButtons() {
    const prevBtn = document.querySelector('.slide-prev');
    const nextBtn = document.querySelector('.slide-next');
    if (prevBtn) prevBtn.disabled = (currentSlide === 0);
    if (nextBtn) nextBtn.disabled = (currentSlide >= totalSlides - 1 || totalSlides === 0);
}

// 📌 API 호출: 직무 검색 (Phase 2 전용)
async function handlePhase2Search() {
    const query = document.getElementById('phase2-search-input').value;
    const resultsContainer = document.getElementById('phase2-search-results');
    const resultsWindow = document.getElementById('phase2-search-results-window');
    
    if (!query) {
        alert("검색어를 입력하시게!");
        return;
    }

    try {
        const response = await fetch(`/api/search_job?query=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (data.status === 'success') {
            resultsContainer.innerHTML = "";
            
            if (data.results.length === 0) {
                resultsContainer.innerHTML = "<p>그런 직무는 없사옵니다...</p>";
            } else {
                data.results.forEach(job => {
                    const btn = document.createElement('button');
                    btn.className = "nes-btn is-success"; 
                    btn.style.display = "block";
                    btn.style.width = "96%"; 
                    btn.style.padding = "4px 8px";
                    btn.style.margin = "0 auto 10px auto"; 
                    btn.style.textAlign = "left";
                    btn.innerText = job.JK중분류;
                    
                    btn.onclick = () => {
                        resultsWindow.classList.add('hidden'); 
                        showJobDetail(job, 2); 
                    };
                    resultsContainer.appendChild(btn);
                });
            }
            resultsWindow.classList.remove('hidden'); 
        }
    } catch (error) {
        alert("검색 중 오류가 발생했사옵니다.");
    }
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
                btn.className = "nes-btn";
                btn.style.display = "block";
                btn.style.width = "90%";
                btn.style.marginBottom = "10px";
                btn.innerText = job.JK중분류;
                btn.onclick = () => {
                    showJobDetail(job, 6); 
                };
                container.appendChild(btn);
            });
        }
    } catch (error) {
        alert("검색 중 오류가 발생했사옵니다.");
    }
}