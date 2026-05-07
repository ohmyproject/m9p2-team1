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
                
                const _itemJson = JSON.stringify(item).replace(/'/g, "&apos;");
                div.innerHTML = `
                    <p class="title">${date} - ${item.job_name}</p>
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <span>기록된 로드맵을 다시 확인하시겠소?</span>
                        <div style="display: flex; gap: 10px;">
                            <button type="button" class="nes-btn is-primary" onclick='viewSavedRoadmap(${_itemJson})'>보기</button>
                            <button type="button" class="nes-btn is-success" onclick='downloadHistoryImage(${_itemJson})'>📸 이미지 저장</button>
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
    selectedJob = { JK중분류: item.job_name, 직무정보: item.job_description || '' };
    // Supabase에 저장된 점수가 있으면 복원, 없으면 null
    const hasScores = item.riasec_scores && Object.keys(item.riasec_scores).length > 0;
    lastScores = hasScores ? item.riasec_scores : null;
    if (hasScores) renderScores(item.riasec_scores);
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

// ─────────────────────────────────────────────
// 📸 이미지 저장: RIASEC 점수 + 직무 정보 + 로드맵 가로 배치
// ─────────────────────────────────────────────
// 과거 기록 모달에서 바로 이미지 저장 (선택한 item 데이터 기반)
async function downloadHistoryImage(item) {
    // 임시로 전역 상태 교체 후 saveRoadmapImage 호출
    const prevJob = selectedJob;
    const prevScores = lastScores;
    const prevSlide = currentSlide;
    const prevTotal = totalSlides;

    const container = document.getElementById('roadmap-content');
    const savedHTML = container.innerHTML;
    const savedTransform = container.style.transform;

    selectedJob = { JK중분류: item.job_name, 직무정보: item.job_description || '' };
    const hasScores = item.riasec_scores && Object.keys(item.riasec_scores).length > 0;
    lastScores = hasScores ? item.riasec_scores : null;

    // 로드맵 텍스트를 DOM에 렌더링
    renderRoadmapFromText(item.roadmap_text);
    await new Promise(r => setTimeout(r, 150));

    await saveRoadmapImage();

    // 상태 복원
    container.innerHTML = savedHTML;
    container.style.transform = savedTransform;
    selectedJob = prevJob;
    lastScores = prevScores;
    currentSlide = prevSlide;
    totalSlides = prevTotal;
}

async function saveRoadmapImage() {
    // selectedJob 없으면 저장 불가. lastScores는 없어도 됨 (그래프 생략)
    if (!selectedJob) {
        alert("저장할 직무가 없사옵니다. 직무를 먼저 선택해 주시게.");
        return;
    }

    const hasScores = !!(lastScores && Object.keys(lastScores).length > 0);

    // ── 임시 캔버스용 컨테이너 생성 ──
    const wrap = document.createElement('div');
    wrap.style.cssText = `
        position: fixed;
        left: -9999px; top: 0;
        width: 1800px;
        background: #1a1208;
        display: flex;
        flex-direction: column;
        align-items: stretch;
        font-family: 'DungGeunMo', sans-serif;
        padding: 32px;
        gap: 28px;
        box-sizing: border-box;
    `;
    document.body.appendChild(wrap);

    // ── 1행: 타이틀 ──
    const titleBar = document.createElement('div');
    titleBar.style.cssText = `
        text-align: center;
        color: #f7d51d;
        font-size: 28px;
        font-weight: bold;
        letter-spacing: 3px;
        text-shadow: 2px 2px #000;
        padding-bottom: 12px;
        border-bottom: 3px solid #c89820;
    `;
    titleBar.textContent = '노비 JOB아라! — 나의 맞춤 면천 비급';
    wrap.appendChild(titleBar);

    // ── 2행: 점수 있으면 RIASEC 그래프, 없으면 생략하고 직무 정보를 위로 ──
    if (hasScores) {
        wrap.appendChild(buildScorePanel(lastScores));
    }

    // ── 3행: 직무 정보 패널 (항상 표시) ──
    wrap.appendChild(buildJobPanel(selectedJob));

    // ── 4행: 로드맵 슬라이드 가로 배치 패널 ──
    wrap.appendChild(buildRoadmapPanel());

    // ── 하단 저작권 표시 ──
    const footer = document.createElement('div');
    footer.style.cssText = `
        text-align: center;
        color: #7a6040;
        font-size: 14px;
        padding-top: 8px;
        border-top: 2px solid #3d2b1a;
    `;
    footer.textContent = '노비 JOB아라! — 나의 면천 여정을 기록하다';
    wrap.appendChild(footer);

    // ── 저장 버튼 비활성화 ──
    const saveBtn = document.querySelector('.save-img-btn');
    if (saveBtn) { saveBtn.textContent = '⏳ 저장 중...'; saveBtn.disabled = true; }

    try {
        await new Promise(r => setTimeout(r, 200)); // 렌더링 대기

        const canvas = await html2canvas(wrap, {
            scale: 1.5,
            useCORS: true,
            allowTaint: true,
            backgroundColor: '#1a1208',
            logging: false,
            width: wrap.offsetWidth,
            height: wrap.offsetHeight,
        });

        const link = document.createElement('a');
        const jobName = selectedJob?.JK중분류 || 'roadmap';
        link.download = `노비JOB아라_${jobName}_로드맵.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
    } catch (e) {
        alert('이미지 저장 중 오류: ' + e.message);
    } finally {
        document.body.removeChild(wrap);
        if (saveBtn) { saveBtn.textContent = '📸 이미지 저장'; saveBtn.disabled = false; }
    }
}

// ── RIASEC 점수 패널 빌더 ──
function buildScorePanel(scores) {
    const RL = [
        { name: "현실형", k: "R" }, { name: "탐구형", k: "I" }, { name: "예술형", k: "A" },
        { name: "사회형", k: "S" }, { name: "진취형", k: "E" }, { name: "관습형", k: "C" }
    ];
    const stdScores = {
        R: scores["현실형"]?.표준점수 || 0, I: scores["탐구형"]?.표준점수 || 0,
        A: scores["예술형"]?.표준점수 || 0, S: scores["사회형"]?.표준점수 || 0,
        E: scores["진취형"]?.표준점수 || 0, C: scores["관습형"]?.표준점수 || 0
    };
    const maxStd = Math.max(...Object.values(stdScores), 1);

    const sorted = [...RL].sort((a, b) => (stdScores[b.k] || 0) - (stdScores[a.k] || 0));
    const t3 = sorted.slice(0, 3).map(l => l.k).join('');

    const panel = document.createElement('div');
    panel.style.cssText = `
        background: #f5e9c8;
        border: 4px solid #3d2b1a;
        border-radius: 6px;
        padding: 22px 28px;
        box-shadow: 4px 4px 0 #1a1008;
    `;

    const head = document.createElement('div');
    head.style.cssText = `
        font-size: 18px; font-weight: bold; color: #1a1008;
        border-bottom: 2px solid #c89820;
        padding-bottom: 10px; margin-bottom: 16px;
    `;
    head.textContent = '🏅 나의 직업흥미 점수 (RIASEC)';
    panel.appendChild(head);

    // 바 차트 (가로로 6개 나란히)
    const barsRow = document.createElement('div');
    barsRow.style.cssText = `display: flex; gap: 16px; align-items: flex-end; margin-bottom: 14px;`;

    RL.forEach(l => {
        const v = stdScores[l.k] || 0;
        const pct = Math.round((v / maxStd) * 100);
        const BAR_HEIGHT = 120;

        const col = document.createElement('div');
        col.style.cssText = `
            display: flex; flex-direction: column; align-items: center; gap: 6px; flex: 1;
        `;

        // 점수 숫자
        const valTxt = document.createElement('div');
        valTxt.style.cssText = `font-size: 18px; font-weight: bold; color: #1a1008;`;
        valTxt.textContent = v;
        col.appendChild(valTxt);

        // 세로 바
        const trackWrap = document.createElement('div');
        trackWrap.style.cssText = `
            width: 40px; height: ${BAR_HEIGHT}px;
            background: #e0c097; border: 2px solid #9a7a40; border-radius: 4px;
            display: flex; align-items: flex-end; overflow: hidden;
        `;
        const fill = document.createElement('div');
        fill.style.cssText = `
            width: 100%; height: ${pct}%;
            background: linear-gradient(180deg, #f7d51d, #c89820);
            border-radius: 2px;
        `;
        trackWrap.appendChild(fill);
        col.appendChild(trackWrap);

        // 레이블
        const lbl = document.createElement('div');
        lbl.style.cssText = `font-size: 13px; color: #3d2b1a; font-weight: bold; text-align: center;`;
        lbl.textContent = `${l.name}(${l.k})`;
        col.appendChild(lbl);

        barsRow.appendChild(col);
    });
    panel.appendChild(barsRow);

    // 흥미 코드 뱃지
    const codeBadge = document.createElement('div');
    codeBadge.style.cssText = `
        background: #fff9c4; border-left: 5px solid #c89820;
        border-radius: 0 4px 4px 0; padding: 10px 16px;
        font-size: 16px; color: #1a1008; font-weight: bold;
        box-shadow: 2px 2px 4px rgba(0,0,0,0.08);
    `;
    codeBadge.textContent = `흥미 코드 ${t3} — ${sorted[0].name} 성향 (대표코드: ${sorted[0].k})`;
    panel.appendChild(codeBadge);

    return panel;
}

// ── 직무 정보 패널 빌더 ──
function buildJobPanel(job) {
    const panel = document.createElement('div');
    panel.style.cssText = `
        background: #f5e9c8;
        border: 4px solid #3d2b1a;
        border-radius: 6px;
        padding: 22px 28px;
        box-shadow: 4px 4px 0 #1a1008;
    `;

    const head = document.createElement('div');
    head.style.cssText = `
        font-size: 18px; font-weight: bold; color: #1a1008;
        border-bottom: 2px solid #c89820;
        padding-bottom: 10px; margin-bottom: 16px;
    `;
    head.textContent = `📋 선택 직무: ${job.JK중분류 || ''}`;
    panel.appendChild(head);

    const body = document.createElement('div');
    body.style.cssText = `font-size: 14px; color: #333; line-height: 1.75;`;

    // 직무정보 파싱 — 섹션별로 구분
    const rawInfo = (job.직무정보 || '').replace(/<br\s*\/?>/gi, '\n');
    const sections = rawInfo.split(/\n(?=\d+\.\s)/);

    sections.forEach(sec => {
        const secDiv = document.createElement('div');
        secDiv.style.cssText = `margin-bottom: 10px;`;
        const trimmed = sec.trim();
        // 제목(숫자. 로 시작)이면 굵게
        const titleMatch = trimmed.match(/^(\d+\.\s*.+?)[\n:]/);
        if (titleMatch) {
            const strong = document.createElement('strong');
            strong.style.cssText = `color: #1a1008; font-size: 15px;`;
            strong.textContent = titleMatch[0].replace(/\n$/, '');
            secDiv.appendChild(strong);
            const rest = document.createElement('span');
            rest.style.cssText = `color: #444;`;
            rest.textContent = ' ' + trimmed.substring(titleMatch[0].length).trim();
            secDiv.appendChild(rest);
        } else {
            secDiv.textContent = trimmed;
        }
        body.appendChild(secDiv);
    });

    panel.appendChild(body);
    return panel;
}

// ── 로드맵 패널 빌더 (슬라이드 가로 배치) ──
function buildRoadmapPanel() {
    // 현재 DOM에서 슬라이드 카드들 수집
    const cards = document.querySelectorAll('#roadmap-content .roadmap-stage-card');

    const panel = document.createElement('div');
    panel.style.cssText = `
        background: #0e0c06;
        border: 4px solid #c89820;
        border-radius: 6px;
        padding: 22px 28px;
        box-shadow: 4px 4px 0 #1a1008;
    `;

    const head = document.createElement('div');
    head.style.cssText = `
        font-size: 18px; font-weight: bold; color: #f7d51d;
        border-bottom: 2px solid #c89820;
        padding-bottom: 10px; margin-bottom: 20px;
    `;
    head.textContent = '🏯 나의 면천 로드맵';
    panel.appendChild(head);

    // 카드들을 가로로 나열
    const row = document.createElement('div');
    row.style.cssText = `
        display: flex;
        gap: 16px;
        align-items: stretch;
    `;

    // "다른 길 찾기" 슬라이드는 제외하고 로드맵 슬라이드만 추출
    const roadmapCards = Array.from(cards).filter(c => {
        const title = c.querySelector('.title');
        return title && !title.textContent.includes('다른 길 찾기');
    });

    roadmapCards.forEach((card, idx) => {
        const colDiv = document.createElement('div');
        colDiv.style.cssText = `
            flex: 1;
            background: #1e1a0e;
            border: 3px solid #c89820;
            border-radius: 6px;
            padding: 18px 20px;
            min-width: 0;
            box-shadow: 3px 3px 0 #000;
        `;

        // 카드 제목
        const titleEl = card.querySelector('.title');
        const titleDiv = document.createElement('div');
        titleDiv.style.cssText = `
            font-size: 16px; font-weight: bold;
            color: #f7d51d; margin-bottom: 14px;
            padding-bottom: 8px;
            border-bottom: 2px solid #3d2b1a;
        `;
        titleDiv.textContent = titleEl ? titleEl.textContent : `제${idx + 1}관문`;
        colDiv.appendChild(titleDiv);

        // 본문 (roadmap-desc)
        const descEl = card.querySelector('.roadmap-desc');
        if (descEl) {
            const descDiv = document.createElement('div');
            descDiv.style.cssText = `
                font-size: 13px; color: #f0e0b0; line-height: 1.75;
                background: rgba(245,230,200,0.08);
                border: 1px solid #3d2b1a; border-radius: 4px;
                padding: 10px 12px; margin-bottom: 10px;
            `;
            descDiv.innerHTML = descEl.innerHTML;
            colDiv.appendChild(descDiv);
        }

        // 결과물 박스
        const resultEl = card.querySelector('.result-box');
        if (resultEl) {
            const rDiv = document.createElement('div');
            rDiv.style.cssText = `
                font-size: 13px; color: #a8e6b0; line-height: 1.7;
                border-left: 4px solid #4aa52e;
                background: rgba(74,165,46,0.08);
                padding: 8px 12px; margin-bottom: 8px;
                border-radius: 0 4px 4px 0;
            `;
            rDiv.innerHTML = resultEl.innerHTML;
            colDiv.appendChild(rDiv);
        }

        // Tip 박스
        const tipEl = card.querySelector('.tip-box');
        if (tipEl) {
            const tDiv = document.createElement('div');
            tDiv.style.cssText = `
                font-size: 13px; color: #f0d070; line-height: 1.7;
                border-left: 4px solid #EF9F27;
                background: rgba(239,159,39,0.08);
                padding: 8px 12px;
                border-radius: 0 4px 4px 0;
            `;
            tDiv.innerHTML = tipEl.innerHTML;
            colDiv.appendChild(tDiv);
        }

        row.appendChild(colDiv);
    });

    panel.appendChild(row);
    return panel;
}