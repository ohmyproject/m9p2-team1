// --- Supabase 초기화 ---
let supabaseClient = null;
let currentSession = null;
let lastScores = null; // 최근 추출된 RIASEC 점수 저장

async function initSupabase() {
    try {
        const response = await fetch('/api/supabase_config');
        const config = await response.json();
        if (config.status !== 'success') throw new Error(config.message || "Supabase 설정 오류");

        supabaseClient = supabase.createClient(config.url, config.publishable_key);

        supabaseClient.auth.onAuthStateChange((event, session) => {
            currentSession = session;
            updateAuthUI(session);
        });

        const { data: { session } } = await supabaseClient.auth.getSession();
        currentSession = session;
        updateAuthUI(session);
    } catch (error) {
        console.error("Supabase 초기화 오류:", error);
        updateAuthUI(null);
    }
}

function updateAuthUI(session) {
    const userInfo = document.getElementById('user-info');
    const loginButtons = document.getElementById('login-buttons');
    const userName = document.getElementById('user-name');

    if (session) {
        userInfo.classList.remove('hidden');
        loginButtons.classList.add('hidden');
        userName.innerText = session.user.user_metadata.full_name || session.user.email;
    } else {
        userInfo.classList.add('hidden');
        loginButtons.classList.remove('hidden');
    }
}

async function handleSignIn(provider) {
    if (!supabaseClient) {
        alert("로그인 설정을 불러오지 못했사옵니다.");
        return;
    }
    const { error } = await supabaseClient.auth.signInWithOAuth({
        provider: provider,
        options: { redirectTo: window.location.origin }
    });
    if (error) alert("로그인 오류: " + error.message);
}

async function handleSignOut() {
    if (!supabaseClient) return;
    const { error } = await supabaseClient.auth.signOut();
    if (error) alert("로그아웃 오류: " + error.message);
}

// 과거 기록 조회 기능
async function showHistory() {
    if (!currentSession) return;
    
    const historyModal = document.getElementById('history-modal');
    const historyList = document.getElementById('history-list');
    historyList.innerHTML = "<p>기록을 불러오는 중이옵니다...</p>";
    historyModal.classList.remove('hidden');

    try {
        const response = await fetch('/api/my_roadmaps', {
            headers: { 'Authorization': `Bearer ${currentSession.access_token}` }
        });
        const data = await response.json();

        if (data.status === 'success') {
            historyList.innerHTML = "";
            if (data.data.length === 0) {
                historyList.innerHTML = "<p>아직 저장된 로드맵이 없사옵니다.</p>";
                return;
            }

            data.data.forEach(item => {
                const date = new Date(item.created_at).toLocaleDateString();
                const div = document.createElement('div');
                div.className = "nes-container is-rounded with-title";
                div.style.marginBottom = "20px";
                div.style.background = "#fff";
                div.style.color = "#000";
                
                div.innerHTML = `
                    <p class="title">${date} - ${item.job_name}</p>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span>기록된 로드맵을 다시 확인하시겠소?</span>
                        <div style="display: flex; gap: 10px;">
                            <button type="button" class="nes-btn is-primary" onclick='viewSavedRoadmap(${JSON.stringify(item).replace(/'/g, "&apos;")})'>보기</button>
                            <button type="button" class="nes-btn is-error" onclick="deleteSavedRoadmap('${item.id}', this)">삭제</button>
                        </div>
                    </div>
                `;
                historyList.appendChild(div);
            });
        } else {
            historyList.innerHTML = "<p>오류: " + data.message + "</p>";
        }
    } catch (error) {
        historyList.innerHTML = "<p>서버 연결 실패!</p>";
    }
}

async function deleteSavedRoadmap(roadmapId, btnElement) {
    if (!confirm("정말로 이 기록을 삭제하시겠소? 한 번 지우면 되돌릴 수 없느니라.")) return;

    try {
        const response = await fetch(`/api/delete_roadmap/${roadmapId}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${currentSession.access_token}` }
        });
        const data = await response.json();

        if (data.status === 'success') {
            alert("기록이 삭제되었느니라.");
            // 리스트에서 해당 항목 제거
            btnElement.closest('.nes-container').remove();
            
            // 만약 리스트가 비었다면 메시지 표시
            const historyList = document.getElementById('history-list');
            if (historyList.children.length === 0) {
                historyList.innerHTML = "<p>아직 저장된 로드맵이 없사옵니다.</p>";
            }
        } else {
            alert("삭제 실패: " + data.message);
        }
    } catch (error) {
        alert("서버 연결 실패!");
    }
}

function viewSavedRoadmap(item) {
    document.getElementById('history-modal').classList.add('hidden');
    selectedJob = { JK중분류: item.job_name };
    renderScores(item.riasec_scores || {});
    renderRoadmapFromText(item.roadmap_text);
    nextPhase(6);
}

document.addEventListener('DOMContentLoaded', initSupabase);

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
            if (text.charAt(i) === '\n') { element.innerHTML += '<br>'; }
            else { element.innerHTML += text.charAt(i); }
            i++;
            setTimeout(type, 30);
        } else if (callback) { callback(); }
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

function getPhaseId(num) {
    return ["", "intro", "upload", "scores", "results", "major", "roadmap", "job-detail"][num];
}

async function handleUpload() {
    const fileInput = document.getElementById('pdf-input');
    if (!fileInput.files.length) { alert("문서를 선택해 주시게!"); return; }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    document.getElementById('typewriter-2').innerText = "열심히 문서를 해독 중이옵니다... 잠시만 기다려 주시옵소서.";
    document.getElementById('action-2').classList.add('hidden');

    try {
        const response = await fetch('/api/upload_pdf', { method: 'POST', body: formData });
        const data = await response.json();
        
        if (data.status === 'success') {
            tempRecommendations = data.recommendations;
            lastScores = data.scores;
            renderScores(data.scores);
            nextPhase(3);
        } else {
            alert("오류 발생: " + data.message);
            document.getElementById('action-2').classList.remove('hidden');
        }
    } catch (error) { alert("서버 연결 실패!"); }
}

function renderScores(scores) {
    const RL = [
        { name: "현실형", k: "R" }, { name: "탐구형", k: "I" }, { name: "예술형", k: "A" },
        { name: "사회형", k: "S" }, { name: "진취형", k: "E" }, { name: "관습형", k: "C" }
    ];
    
    const stdScores = {
        "R": scores["현실형"]?.표준점수 || 0, "I": scores["탐구형"]?.표준점수 || 0,
        "A": scores["예술형"]?.표준점수 || 0, "S": scores["사회형"]?.표준점수 || 0,
        "E": scores["진취형"]?.표준점수 || 0, "C": scores["관습형"]?.표준점수 || 0
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
        btn.onclick = () => { showJobDetail(job, 4); };
        container.appendChild(btn);
    });
}

async function showRoadmap(answer) {
    if (!selectedJob) { alert("선택된 직무가 없사옵니다!"); return; }

    document.getElementById('typewriter-5').innerText = "AI 대감이 맞춤형 신분 상승의 길을 점치고 있사옵니다...\n잠시만 기다려 주시옵소서.";
    document.getElementById('action-5').classList.add('hidden');

    const requestData = {
        job_name: selectedJob.JK중분류,
        is_major_required: selectedJob.전공필수 === 'O',
        user_major_status: answer,
        riasec_scores: lastScores
    };

    try {
        const headers = { 'Content-Type': 'application/json' };
        if (currentSession) { headers['Authorization'] = `Bearer ${currentSession.access_token}`; }

        const response = await fetch('/api/roadmap', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(requestData)
        });

        const data = await response.json();

        if (data.status === 'success') {
            renderRoadmapFromText(data.roadmap);
            nextPhase(6);
        } else {
            alert("오류 발생: " + data.message);
            document.getElementById('action-5').classList.remove('hidden');
        }
    } catch (error) {
        alert("서버 연결 실패!");
        document.getElementById('action-5').classList.remove('hidden');
    }
}

function renderRoadmapFromText(rawText) {
    const container = document.getElementById('roadmap-content');
    container.innerHTML = "";
    container.style.transform = "translateX(0)";
    currentSlide = 0;

    const sections = rawText.split(/(?=(?:■|#|\*)*\s*\d+단계)/g).map(s => s.trim()).filter(s => s.length > 20);
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
            titleText = `제${stepMatch[1]}관문: ${stepMatch[2].split('\n')[0].trim()}`.replace(/^[■#*]+\s*/, '');
            const firstLineIndex = section.indexOf(stepMatch[0]);
            let remainingText = section.substring(firstLineIndex + stepMatch[0].length).trim();
            
            let descText = remainingText, resultText = "", tipText = "";
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
            if (descText) finalBodyHTML += `<div class="roadmap-desc">${descText.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>`;
            if (resultText) finalBodyHTML += `<div class="result-box"><strong style="color:var(--green-jade);">📌 결과물</strong><br>${resultText.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>`;
            if (tipText) finalBodyHTML += `<div class="tip-box"><strong style="color:#B36B00;">💡 현실적 Tip</strong><br>${tipText.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>`;
            bodyContent = finalBodyHTML;
        } else {
            titleText = "📜 입신양명 비기";
            bodyContent = section.replace(/^[■#*]+\s*/g, '').replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        }

        const stageDiv = document.createElement('div');
        stageDiv.className = "nes-container with-title roadmap-stage-card";
        const titleP = document.createElement('p');
        titleP.className = "title"; titleP.innerText = titleText;
        const contentP = document.createElement('p');
        contentP.innerHTML = bodyContent;
        stageDiv.appendChild(titleP); stageDiv.appendChild(contentP);
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
        <div id="search-results" class="job-list-container" style="margin-top: 15px; max-height: 250px; overflow-y: auto; width: 95%; margin-left: auto; margin-right: auto;"></div>
        <div style="text-align: center; margin-top: 20px;">
            <button type="button" class="nes-btn is-warning" onclick="location.reload()">처음으로 돌아가기</button>
        </div>
    `;
    container.appendChild(searchStage);
    updateSlideButtons();
}

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

async function handlePhase2Search() {
    const query = document.getElementById('phase2-search-input').value;
    const resultsContainer = document.getElementById('phase2-search-results');
    const resultsWindow = document.getElementById('phase2-search-results-window');
    if (!query) { alert("검색어를 입력하시게!"); return; }
    try {
        const response = await fetch(`/api/search_job?query=${encodeURIComponent(query)}`);
        const data = await response.json();
        if (data.status === 'success') {
            resultsContainer.innerHTML = "";
            if (data.results.length === 0) { resultsContainer.innerHTML = "<p>그런 직무는 없사옵니다...</p>"; }
            else {
                data.results.forEach(job => {
                    const btn = document.createElement('button');
                    btn.className = "nes-btn is-success";
                    btn.style.display = "block"; btn.style.width = "96%"; btn.style.padding = "4px 8px";
                    btn.style.margin = "0 auto 10px auto"; btn.style.textAlign = "left";
                    btn.innerText = job.JK중분류;
                    btn.onclick = () => { resultsWindow.classList.add('hidden'); showJobDetail(job, 2); };
                    resultsContainer.appendChild(btn);
                });
            }
            resultsWindow.classList.remove('hidden');
        }
    } catch (error) { alert("검색 중 오류가 발생했사옵니다."); }
}

async function handleSearch() {
    const query = document.getElementById('search-input').value;
    if (!query) { alert("검색어를 입력하시게!"); return; }
    try {
        const response = await fetch(`/api/search_job?query=${encodeURIComponent(query)}`);
        const data = await response.json();
        if (data.status === 'success') {
            const container = document.getElementById('search-results');
            container.innerHTML = "";
            if (data.results.length === 0) { container.innerHTML = "<p>그런 직무는 없사옵니다...</p>"; return; }
            data.results.forEach(job => {
                const btn = document.createElement('button');
                btn.className = "nes-btn"; btn.style.display = "block"; btn.style.width = "90%"; btn.style.marginBottom = "10px";
                btn.innerText = job.JK중분류;
                btn.onclick = () => { showJobDetail(job, 6); };
                container.appendChild(btn);
            });
        }
    } catch (error) { alert("검색 중 오류가 발생했사옵니다."); }
}
