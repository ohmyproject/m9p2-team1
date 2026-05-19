// --- Supabase 초기화 ---
let supabaseClient = null;
let currentSession = null;
let lastScores = null; // 최근 추출된 RIASEC 점수 저장
let lastMajorAnswer = null;
let roadmapChatMessages = [];
let activeRoadmapId = null;
let activeThreadId = null;
let activeSessionId = null;

async function initSupabase() {
    try {
        const response = await fetch('/api/supabase_config');
        const config = await response.json();
        
        if (config.status === 'success') {
            supabaseClient = supabase.createClient(config.url, config.publishable_key);

            supabaseClient.auth.onAuthStateChange((event, session) => {
                currentSession = session;
                updateAuthUI(session);
            });

            const { data: { session } } = await supabaseClient.auth.getSession();
            currentSession = session;
            updateAuthUI(session);
        } else {
            console.error("Supabase 설정 로드 실패:", config.message);
        }
    } catch (error) {
        console.error("Supabase 초기화 중 오류 발생:", error);
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
    const { error } = await supabaseClient.auth.signInWithOAuth({
        provider: provider,
        options: { redirectTo: window.location.origin }
    });
    if (error) alert("로그인 오류: " + error.message);
}

async function handleSignOut() {
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

            const toolbar = document.createElement('div');
            toolbar.className = "history-bulk-toolbar";
            toolbar.innerHTML = `
                <label class="history-select-all">
                    <input type="checkbox" id="history-select-all" onchange="toggleHistorySelection(this.checked)">
                    <span>전체 선택</span>
                </label>
                <div class="history-bulk-actions">
                    <span id="history-selected-count">0개 선택</span>
                    <button type="button" class="nes-btn is-error" id="history-delete-selected" onclick="deleteSelectedRoadmaps()" disabled>선택 삭제</button>
                </div>
            `;
            historyList.appendChild(toolbar);

            data.data.forEach(item => {
                const date = new Date(item.created_at).toLocaleDateString();
                const itemJson = JSON.stringify(item).replace(/'/g, "&apos;");
                const div = document.createElement('div');
                div.className = "nes-container is-rounded with-title history-card";
                div.dataset.roadmapId = item.id;
                
                div.innerHTML = `
                    <p class="title">${date} - ${item.job_name}</p>
                    <div class="history-card-row">
                        <div class="history-card-check">
                            <input type="checkbox" class="history-select-checkbox" id="history-check-${item.id}" value="${item.id}" onchange="updateHistorySelectionState()">
                            <label for="history-check-${item.id}"></label>
                        </div>
                        <span class="history-card-desc">기록된 로드맵을 다시 확인하시겠소?</span>
                        <div class="history-card-actions">
                            <button type="button" class="nes-btn is-primary" onclick='viewSavedRoadmap(${itemJson})'>보기</button>
                            <button type="button" class="nes-btn is-success" onclick='downloadHistoryImage(${itemJson})'>📸 이미지 저장</button>
                            <button type="button" class="nes-btn is-error" onclick="deleteSavedRoadmap('${item.id}', this)">삭제</button>
                        </div>
                    </div>
                `;
                historyList.appendChild(div);
            });
            updateHistorySelectionState();
        } else {
            historyList.innerHTML = "<p>오류: " + data.message + "</p>";
        }
    } catch (error) {
        historyList.innerHTML = "<p>서버 연결 실패!</p>";
    }
}

function getSelectedHistoryIds() {
    return Array.from(document.querySelectorAll('.history-select-checkbox:checked')).map(input => input.value);
}

function updateHistorySelectionState() {
    const checkboxes = Array.from(document.querySelectorAll('.history-select-checkbox'));
    const selectedIds = getSelectedHistoryIds();
    const selectAll = document.getElementById('history-select-all');
    const countLabel = document.getElementById('history-selected-count');
    const deleteBtn = document.getElementById('history-delete-selected');

    if (selectAll) {
        selectAll.checked = checkboxes.length > 0 && selectedIds.length === checkboxes.length;
        selectAll.indeterminate = selectedIds.length > 0 && selectedIds.length < checkboxes.length;
    }
    if (countLabel) countLabel.textContent = `${selectedIds.length}개 선택`;
    if (deleteBtn) deleteBtn.disabled = selectedIds.length === 0;
}

function toggleHistorySelection(checked) {
    document.querySelectorAll('.history-select-checkbox').forEach(input => {
        input.checked = checked;
    });
    updateHistorySelectionState();
}

async function deleteSelectedRoadmaps() {
    const selectedIds = getSelectedHistoryIds();
    if (selectedIds.length === 0) {
        alert("삭제할 기록을 선택해주세요.");
        return;
    }
    if (!confirm(`선택한 ${selectedIds.length}개의 기록을 삭제하시겠소? 한 번 지우면 되돌릴 수 없느니라.`)) return;

    const deleteBtn = document.getElementById('history-delete-selected');
    if (deleteBtn) deleteBtn.disabled = true;

    try {
        const response = await fetch('/api/delete_roadmaps', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${currentSession.access_token}`
            },
            body: JSON.stringify({ ids: selectedIds })
        });
        const data = await response.json();

        if (data.status === 'success') {
            const deletedIds = Array.isArray(data.deleted_ids) ? data.deleted_ids : selectedIds;
            deletedIds.forEach(id => {
                document.querySelectorAll('.history-card').forEach(card => {
                    if (card.dataset.roadmapId === id) card.remove();
                });
            });

            const historyList = document.getElementById('history-list');
            if (historyList && document.querySelectorAll('.history-card').length === 0) {
                historyList.innerHTML = "<p>아직 저장된 로드맵이 없사옵니다.</p>";
            } else {
                updateHistorySelectionState();
            }
            alert(`${data.deleted_count || deletedIds.length}개의 기록이 삭제되었느니라.`);
        } else {
            alert("선택 삭제 실패: " + data.message);
            updateHistorySelectionState();
        }
    } catch (error) {
        alert("서버 연결 실패!");
        updateHistorySelectionState();
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
            btnElement.closest('.history-card')?.remove();
            
            // 만약 리스트가 비었다면 메시지 표시
            const historyList = document.getElementById('history-list');
            if (document.querySelectorAll('.history-card').length === 0) {
                historyList.innerHTML = "<p>아직 저장된 로드맵이 없사옵니다.</p>";
            } else {
                updateHistorySelectionState();
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
    selectedJob = { JK중분류: item.job_name, 직무정보: item.job_information || '' };
    // 챗봇이 흥미점수를 읽을 수 있도록 lastScores에도 저장
    lastScores = item.riasec_scores || {};
    lastRoadmapText = item.roadmap_text || '';
    activeRoadmapId = item.id || null;
    activeThreadId = null;
    activeSessionId = null;
    renderScores(lastScores);
    renderRoadmapFromText(item.roadmap_text);
    nextPhase(6);
}

document.addEventListener('DOMContentLoaded', initSupabase);

const dialogues = {
    2: "어서오거라! 아래 두 가지 길 중 하나를 선택하시게나.",
    3: "오호, 너의 기질을 해독해 보았느니라.\n한번 확인해 보겠느냐?",
    4: "방보를 확인하시게. 자네에게 제일 잘 맞을 것 같은 10가지의 일거리 라네.\n어떤일을 하기를 원하는가? 하나 선택해 보게나.",
    5: "호오, 그 일을 해보려는가? \n그렇다면 관련된 학문(전공)은 접해본 적이 있는가?",
    7: "이 직무가 어떤 일을 하는지 자세히 읽어보게나. 마음에 드는가?"
};

let selectedJob = null;
let tempRecommendations = [];
let lastRoadmapText = null;   // 챗봇 맥락·이미지 저장용

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

async function handleLoadSavedScores() {
    if (!currentSession) {
        alert("먼저 로그인해 주시게! 저장된 점수를 불러오려면 계정 확인이 필요하옵니다.");
        return;
    }

    document.getElementById('typewriter-2').innerText = "예전 기록에서 가장 최근 점수를 찾고 있사옵니다... 잠시만 기다려 주시옵소서.";
    document.getElementById('action-2').classList.add('hidden');

    try {
        const response = await fetch('/api/latest_riasec_scores', {
            headers: { 'Authorization': `Bearer ${currentSession.access_token}` }
        });
        const data = await response.json();

        if (data.status === 'success') {
            tempRecommendations = data.recommendations || [];
            lastScores = data.scores;
            renderScores(data.scores);
            nextPhase(3);
        } else {
            alert("점수 불러오기 실패: " + data.message);
            document.getElementById('action-2').classList.remove('hidden');
        }
    } catch (error) {
        alert("서버 연결 실패!");
        document.getElementById('action-2').classList.remove('hidden');
    }
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
    renderCategoryPanel(tempRecommendations);
    renderJobList(tempRecommendations.slice(0, 10));
    nextPhase(4);
}

function renderCategoryPanel(allJobs) {
    const panel = document.getElementById('category-panel-list');
    if (!panel) return;
    panel.innerHTML = '';

    // TOP 10 전체 버튼
    const allBtn = document.createElement('button');
    allBtn.className = 'nes-btn is-primary category-filter-btn';
    allBtn.id = 'cat-btn-all';
    allBtn.style.cssText = 'display:block;width:100%;margin-bottom:8px;text-align:left;';
    allBtn.innerText = '⭐ TOP 10 전체';
    allBtn.onclick = () => {
        setActiveCategoryBtn('all');
        renderJobList(tempRecommendations.slice(0, 10));
    };
    panel.appendChild(allBtn);

    // 구분선
    const sep = document.createElement('div');
    sep.style.cssText = 'border-top:2px solid #c89820;margin:8px 0 10px;';
    panel.appendChild(sep);

    // 대분류 버튼 목록
    const categories = [];
    const seen = new Set();
    allJobs.forEach(job => {
        const cat = job['JK대분류'] || '';
        if (cat && !seen.has(cat)) { seen.add(cat); categories.push(cat); }
    });

    categories.forEach(cat => {
        const btn = document.createElement('button');
        btn.className = 'nes-btn category-filter-btn';
        btn.dataset.cat = cat;
        btn.style.cssText = 'display:block;width:100%;margin-bottom:8px;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
        btn.title = cat;
        btn.innerText = cat;
        btn.onclick = () => {
            setActiveCategoryBtn(cat);
            const filtered = allJobs.filter(j => (j['JK대분류'] || '') === cat);
            renderJobList(filtered);
        };
        panel.appendChild(btn);
    });
}

function setActiveCategoryBtn(key) {
    document.querySelectorAll('.category-filter-btn').forEach(btn => {
        btn.classList.remove('is-primary');
    });
    const target = key === 'all'
        ? document.getElementById('cat-btn-all')
        : document.querySelector(`.category-filter-btn[data-cat="${CSS.escape(key)}"]`);
    if (target) target.classList.add('is-primary');
}

function showJobDetail(job, fromPhase) {
    selectedJob = job;
    document.getElementById('detail-title').innerText = `📜 ${job.JK중분류} 상세 정보`;
    document.getElementById('detail-content').innerHTML = formatJobInfo(job.직무정보);
    const backBtn = document.getElementById('back-to-list-btn');
    backBtn.onclick = () => nextPhase(fromPhase);
    nextPhase(7);
}

function formatJobInfo(rawText) {
    if (!rawText) return '<p class="jd-empty">상세 정보가 없사옵니다.</p>';

    const sectionConfig = [
        { icon: '📌', cls: 'jd-define' },
        { icon: '🎯', cls: 'jd-role'   },
        { icon: '💼', cls: 'jd-tasks'  },
        { icon: '🔧', cls: 'jd-skills' },
    ];

    const lines = rawText.split('\n');
    const sections = [];
    let current = null;

    for (const line of lines) {
        const m = line.match(/^(\d+)\.\s+(.+)/);
        if (m) {
            if (current) sections.push(current);
            const full = m[2];
            const colonIdx = full.indexOf(':');
            const title = colonIdx !== -1 ? full.slice(0, colonIdx).trim() : full.trim();
            const rest  = colonIdx !== -1 ? full.slice(colonIdx + 1).trim() : '';
            current = { title, lines: rest ? [rest] : [] };
        } else if (current) {
            current.lines.push(line);
        }
    }
    if (current) sections.push(current);

    if (sections.length === 0) return `<p class="jd-para">${rawText.replace(/\n/g, '<br>')}</p>`;

    return sections.map((sec, i) => {
        const cfg = sectionConfig[i] || sectionConfig[0];
        return `<div class="jd-section ${cfg.cls}">
            <div class="jd-section-title">${cfg.icon} ${sec.title}</div>
            <div class="jd-section-body">${buildDetailHtml(sec.lines.join('\n'))}</div>
        </div>`;
    }).join('');
}

function buildDetailHtml(text) {
    const lines = text.split('\n');
    let html = '';
    const openLists = [];

    const closeListsTo = (depth) => {
        while (openLists.length > 0 && openLists[openLists.length - 1] > depth) {
            html += '</ul>';
            openLists.pop();
        }
    };

    for (const line of lines) {
        if (!line.trim()) continue;
        const indent = (line.match(/^( *)/) || ['', ''])[1].length;
        const trimmed = line.trim();
        if (trimmed.startsWith('- ')) {
            const content = trimmed.slice(2);
            const depth = Math.floor(indent / 2);
            closeListsTo(depth);
            if (openLists.length === 0 || openLists[openLists.length - 1] < depth) {
                html += `<ul class="${openLists.length === 0 ? 'jd-list' : 'jd-sublist'}">`;
                openLists.push(depth);
            }
            html += `<li>${content}</li>`;
        } else {
            closeListsTo(-1);
            html += `<p class="jd-para">${trimmed}</p>`;
        }
    }
    closeListsTo(-1);
    return html;
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
        btn.innerText = `${index + 1}. ${job.JK중분류} (일치율: ${(job.최종유사도 * 100).toFixed(2)}%)`;
        btn.onclick = () => { showJobDetail(job, 4); };
        container.appendChild(btn);
    });
}

async function showRoadmap(answer) {
    if (!selectedJob) { alert("선택된 직무가 없사옵니다!"); return; }
    lastMajorAnswer = answer;
    activeRoadmapId = null;
    activeThreadId = null;
    activeSessionId = null;

    document.getElementById('typewriter-5').innerText = "AI 대감이 맞춤형 신분 상승의 길을 점치고 있사옵니다...\n잠시만 기다려 주시옵소서.";
    document.getElementById('action-5').classList.add('hidden');

    const requestData = {
        job_name: selectedJob.JK중분류,
        is_major_required: selectedJob.전공필수 === 'O',
        user_major_status: answer,
        riasec_scores: lastScores,
        job_information: selectedJob.직무정보
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
            lastRoadmapText  = data.roadmap;
            activeRoadmapId = data.roadmap_id || null;
            activeThreadId = data.thread_id || null;
            activeSessionId = data.session_id || null;
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
    roadmapChatMessages = [];

    const sections = rawText.split(/(?=(?:■|#|\*)*\s*\d+단계)/g).map(s => s.trim()).filter(s => s.length > 20);
    if (sections.length > 1 && !sections[0].includes("1단계") && sections[0].length < 100) {
         sections[1] = sections[0] + "\n\n" + sections[1];
         sections.shift();
    }
    totalSlides = sections.length + 1;
    updateSlideButtons();

    sections.forEach((section, index) => {
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
        if (index === sections.length - 1) {
            const actionDiv = document.createElement('div');
            actionDiv.className = "roadmap-final-actions";
            actionDiv.innerHTML = `
                <button type="button" class="nes-btn is-success" onclick="saveRoadmapImage()">🖼️ 이미지로 저장</button>
                <button type="button" class="nes-btn is-warning" onclick="location.reload()">처음으로</button>
            `;
            stageDiv.appendChild(actionDiv);
        }
        container.appendChild(stageDiv);
    });

    const chatStage = document.createElement('div');
    chatStage.className = "nes-container with-title roadmap-stage-card chatbot-stage-card";
    chatStage.innerHTML = `
        <p class="title">🔍 탐봇 — 직무 탐색 도우미</p>
        <p class="roadmap-chat-intro">추천 직무가 나에게 진짜 맞는지 검증하고, 대안 직무를 비교 탐색해드려요.<br>※ 흥미 기반 탐색이며 최종 진로 판정이 아닙니다.</p>
        <div class="roadmap-chat-suggestions">
            <button type="button" class="nes-btn is-small" onclick="useRoadmapChatPrompt('이 직무가 내 흥미 유형과 실제로 잘 맞아? 장단점도 알려줘')">✅ 직무 적합성 확인</button>
            <button type="button" class="nes-btn is-small" onclick="useRoadmapChatPrompt('이 직무와 비슷하면서 진입 장벽이 낮은 대안 직무를 추천해줘')">🔄 대안 직무 탐색</button>

        </div>
        <div id="roadmap-chat-log" class="roadmap-chat-log"></div>
        <div class="roadmap-chat-input-row">
            <input type="text" id="roadmap-chat-input" class="nes-input" placeholder="직무 적합성, 대안 직무 등을 물어보세요..." onkeydown="handleRoadmapChatKey(event)">
            <button type="button" class="nes-btn is-primary" id="roadmap-chat-send" onclick="sendRoadmapChat()">질문</button>
        </div>
    `;
    container.appendChild(chatStage);
    addRoadmapChatMessage("assistant", "안녕하세요! 직무 탐색 도우미 탐봇이에요 👋\n\n로드맵까지 받으셨군요! 이제 '이 직무가 진짜 나한테 맞나?'를 같이 검증해봐요.\n\n✅ 직무 적합성 검증 — 내 흥미 유형과 이 직무가 맞는지 분석\n🔄 대안 직무 비교 — 비슷하거나 진입이 더 쉬운 직무 탐색\n\n위 버튼을 눌러보거나, 궁금한 걸 바로 물어보세요!");
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

function escapeHtml(text) {
    return String(text || '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
}

function addRoadmapChatMessage(role, text, citations = []) {
    const log = document.getElementById('roadmap-chat-log');
    if (!log) return null;

    const msg = document.createElement('div');
    msg.className = `roadmap-chat-message ${role === 'user' ? 'is-user' : 'is-bot'}`;

    const label = document.createElement('div');
    label.className = "roadmap-chat-label";
    label.textContent = role === 'user' ? '나' : '탐봇';

    const body = document.createElement('div');
    body.className = "roadmap-chat-body";
    body.innerHTML = escapeHtml(text).replace(/\n/g, '<br>');

    if (citations && citations.length > 0) {
        const citeWrap = document.createElement('div');
        citeWrap.className = "roadmap-chat-citations";
        citeWrap.innerHTML = citations.slice(0, 5).map((item, index) => {
            const title = escapeHtml(item.title || item.url || `출처 ${index + 1}`);
            const url = escapeHtml(item.url || '#');
            return `<a href="${url}" target="_blank" rel="noopener noreferrer">[${index + 1}] ${title}</a>`;
        }).join('');
        body.appendChild(citeWrap);
    }

    msg.appendChild(label);
    msg.appendChild(body);
    log.appendChild(msg);
    log.scrollTop = log.scrollHeight;

    return body; // 실시간 업데이트를 위해 body 요소 반환
}

function handleRoadmapChatKey(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        sendRoadmapChat();
    }
}

function useRoadmapChatPrompt(prompt) {
    const input = document.getElementById('roadmap-chat-input');
    if (input) input.value = prompt;
    sendRoadmapChat(prompt);
}

async function sendRoadmapChat(promptOverride) {
    const input = document.getElementById('roadmap-chat-input');
    const sendBtn = document.getElementById('roadmap-chat-send');
    const message = (promptOverride || (input ? input.value : '') || '').trim();
    if (!message) return;

    if (input) input.value = '';
    if (sendBtn) { sendBtn.disabled = true; sendBtn.textContent = '질문 중...'; }

    roadmapChatMessages.push({ role: 'user', content: message });
    addRoadmapChatMessage('user', message);

    const botMsgBody = addRoadmapChatMessage('assistant', '');
    let fullReply = "";

    try {
        const hasRiasecScores = !!(lastScores && Object.keys(lastScores).length > 0);
        const headers = { 'Content-Type': 'application/json' };
        if (currentSession) { headers['Authorization'] = `Bearer ${currentSession.access_token}`; }

        const response = await fetch('/api/roadmap_chat', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                message,
                messages: roadmapChatMessages.slice(-8),
                roadmap_id: activeRoadmapId,
                thread_id: activeThreadId,
                session_id: activeSessionId,
                job_name: selectedJob?.JK중분류 || '',
                job_information: selectedJob?.직무정보 || '',
                riasec_scores: lastScores,
                has_riasec_scores: hasRiasecScores,
                score_context_note: hasRiasecScores ? '' : '직무 직접 검색으로 들어온 경우에는 저장된 흥미점수가 없어 RIASEC 기반 답변을 제공할 수 없습니다.',
                roadmap_text: lastRoadmapText,
                recommendations: tempRecommendations,
                user_major_status: lastMajorAnswer
            })
        });

        // 에러 응답 안전하게 파싱
        if (!response.ok) {
            let msg = '';
            try {
                const errorData = await response.json();
                msg = errorData.message || '';
            } catch {
                msg = `(HTTP ${response.status})`;
            }
            if (botMsgBody) botMsgBody.innerHTML = `잠시 답변을 드리기 어렵네요. ${msg}`.trim();
            return;
        }

        // 헤더에서 thread/session ID 수신
        const newThreadId = response.headers.get('X-Thread-Id');
        const newSessionId = response.headers.get('X-Session-Id');
        if (newThreadId) activeThreadId = newThreadId;
        if (newSessionId) activeSessionId = newSessionId;

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const log = document.getElementById('roadmap-chat-log');

        while (true) {
            const { done, value } = await reader.read();

            // 스트림 종료 시 TextDecoder 버퍼 플러시
            if (done) {
                const remaining = decoder.decode();
                if (remaining) {
                    fullReply += remaining;
                    if (botMsgBody) {
                        botMsgBody.innerHTML = escapeHtml(fullReply).replace(/\n/g, '<br>');
                    }
                }
                break;
            }

            const chunk = decoder.decode(value, { stream: true });
            fullReply += chunk;

            if (botMsgBody) {
                botMsgBody.innerHTML = escapeHtml(fullReply).replace(/\n/g, '<br>');
            }
            if (log) log.scrollTop = log.scrollHeight;
        }

        roadmapChatMessages.push({ role: 'assistant', content: fullReply });

    } catch (error) {
        if (botMsgBody) botMsgBody.innerHTML = '서버 연결이 잠시 불안정해요. 조금 뒤 다시 물어봐 주세요.';
    } finally {
        if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = '질문'; }
        if (input) input.focus();
    }
}

// ─────────────────────────────────────────────
// 📸 이미지 저장: RIASEC 점수 + 직무 정보 + 로드맵 가로 배치
// ─────────────────────────────────────────────

// 과거 기록 모달에서 바로 이미지 저장
async function downloadHistoryImage(item) {
    const prevJob    = selectedJob;
    const prevScores = lastScores;
    const prevSlide  = currentSlide;
    const prevTotal  = totalSlides;

    const container   = document.getElementById('roadmap-content');
    const savedHTML   = container.innerHTML;
    const savedTransform = container.style.transform;

    selectedJob = { JK중분류: item.job_name, 직무정보: item.job_information || '' };
    const hasScores = item.riasec_scores && Object.keys(item.riasec_scores).length > 0;
    lastScores = hasScores ? item.riasec_scores : null;

    renderRoadmapFromText(item.roadmap_text);
    await new Promise(r => setTimeout(r, 150));
    await saveRoadmapImage();

    // 상태 복원
    container.innerHTML      = savedHTML;
    container.style.transform = savedTransform;
    selectedJob  = prevJob;
    lastScores   = prevScores;
    currentSlide = prevSlide;
    totalSlides  = prevTotal;
}

async function saveRoadmapImage() {
    if (!selectedJob) {
        alert("저장할 직무가 없사옵니다. 직무를 먼저 선택해 주시게.");
        return;
    }

    // html2canvas CDN 동적 로드
    if (!window.html2canvas) {
        await new Promise((resolve, reject) => {
            const s = document.createElement('script');
            s.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
            s.onload = resolve; s.onerror = reject;
            document.head.appendChild(s);
        });
    }

    const hasScores = !!(lastScores && Object.keys(lastScores).length > 0);

    // ── 임시 캔버스용 컨테이너 생성 ──
    const wrap = document.createElement('div');
    wrap.style.cssText = `
        position: fixed; left: -9999px; top: 0;
        width: 1800px;
        background: #1a1208;
        display: flex; flex-direction: column; align-items: stretch;
        font-family: 'DungGeunMo', sans-serif;
        padding: 32px; gap: 28px; box-sizing: border-box;
    `;
    document.body.appendChild(wrap);

    // 1행: 타이틀
    const titleBar = document.createElement('div');
    titleBar.style.cssText = `
        text-align: center; color: #f7d51d;
        font-size: 28px; font-weight: bold; letter-spacing: 3px;
        text-shadow: 2px 2px #000;
        padding-bottom: 12px; border-bottom: 3px solid #c89820;
    `;
    titleBar.textContent = '노비 JOB아라! — 나의 맞춤 면천 비급';
    wrap.appendChild(titleBar);

    // 2행: RIASEC (점수 있을 때만)
    if (hasScores) wrap.appendChild(buildScorePanel(lastScores));

    // 3행: 직무 정보
    wrap.appendChild(buildJobPanel(selectedJob));

    // 4행: 로드맵 가로 배치
    wrap.appendChild(buildRoadmapPanel());

    // 하단 푸터
    const footer = document.createElement('div');
    footer.style.cssText = `
        text-align: center; color: #7a6040; font-size: 14px;
        padding-top: 8px; border-top: 2px solid #3d2b1a;
    `;
    footer.textContent = '노비 JOB아라! — 나의 면천 여정을 기록하다';
    wrap.appendChild(footer);

    // 저장 버튼 비활성화
    const saveBtn = document.querySelector('.roadmap-stage-card .nes-btn.is-success');
    if (saveBtn) { saveBtn.textContent = '⏳ 저장 중...'; saveBtn.disabled = true; }

    try {
        await new Promise(r => setTimeout(r, 200));
        const canvas = await html2canvas(wrap, {
            scale: 1.5, useCORS: true, allowTaint: true,
            backgroundColor: '#1a1208', logging: false,
            width: wrap.offsetWidth, height: wrap.offsetHeight,
        });
        const link = document.createElement('a');
        link.download = `노비JOB아라_${(selectedJob?.JK중분류 || 'roadmap').replace(/\s+/g,'_')}_로드맵.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
    } catch (e) {
        alert('이미지 저장 중 오류: ' + e.message);
    } finally {
        document.body.removeChild(wrap);
        if (saveBtn) { saveBtn.textContent = '🖼️ 이미지로 저장'; saveBtn.disabled = false; }
    }
}

// ── RIASEC 세로 막대 차트 패널 ──
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
        background: #f5e9c8; border: 4px solid #3d2b1a;
        border-radius: 6px; padding: 22px 28px; box-shadow: 4px 4px 0 #1a1008;
    `;

    const head = document.createElement('div');
    head.style.cssText = `font-size: 18px; font-weight: bold; color: #1a1008;
        border-bottom: 2px solid #c89820; padding-bottom: 10px; margin-bottom: 16px;`;
    head.textContent = '🏅 나의 직업흥미 점수 (RIASEC)';
    panel.appendChild(head);

    const barsRow = document.createElement('div');
    barsRow.style.cssText = `display: flex; gap: 16px; align-items: flex-end; margin-bottom: 14px;`;

    RL.forEach(l => {
        const v = stdScores[l.k] || 0;
        const pct = Math.round((v / maxStd) * 100);
        const BAR_HEIGHT = 120;

        const col = document.createElement('div');
        col.style.cssText = `display: flex; flex-direction: column; align-items: center; gap: 6px; flex: 1;`;

        const valTxt = document.createElement('div');
        valTxt.style.cssText = `font-size: 18px; font-weight: bold; color: #1a1008;`;
        valTxt.textContent = v;
        col.appendChild(valTxt);

        const trackWrap = document.createElement('div');
        trackWrap.style.cssText = `
            width: 40px; height: ${BAR_HEIGHT}px;
            background: #e0c097; border: 2px solid #9a7a40; border-radius: 4px;
            display: flex; align-items: flex-end; overflow: hidden;
        `;
        const fill = document.createElement('div');
        fill.style.cssText = `
            width: 100%; height: ${pct}%;
            background: linear-gradient(180deg, #f7d51d, #c89820); border-radius: 2px;
        `;
        trackWrap.appendChild(fill);
        col.appendChild(trackWrap);

        const lbl = document.createElement('div');
        lbl.style.cssText = `font-size: 13px; color: #3d2b1a; font-weight: bold; text-align: center;`;
        lbl.textContent = `${l.name}(${l.k})`;
        col.appendChild(lbl);

        barsRow.appendChild(col);
    });
    panel.appendChild(barsRow);

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

// ── 직무 정보 패널 ──
function buildJobPanel(job) {
    const panel = document.createElement('div');
    panel.style.cssText = `
        background: #f5e9c8; border: 4px solid #3d2b1a;
        border-radius: 6px; padding: 22px 28px; box-shadow: 4px 4px 0 #1a1008;
    `;

    const head = document.createElement('div');
    head.style.cssText = `font-size: 18px; font-weight: bold; color: #1a1008;
        border-bottom: 2px solid #c89820; padding-bottom: 10px; margin-bottom: 16px;`;
    head.textContent = `📋 선택 직무: ${job.JK중분류 || ''}`;
    panel.appendChild(head);

    const body = document.createElement('div');
    body.style.cssText = `font-size: 14px; color: #333; line-height: 1.75;`;

    const rawInfo = (job.직무정보 || '').replace(/<br\s*\/?>/gi, '\n');
    const sections = rawInfo.split(/\n(?=\d+\.\s)/);
    sections.forEach(sec => {
        const secDiv = document.createElement('div');
        secDiv.style.cssText = `margin-bottom: 10px;`;
        const trimmed = sec.trim();
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

// ── 로드맵 패널 (슬라이드 가로 배치) ──
function buildRoadmapPanel() {
    const cards = document.querySelectorAll('#roadmap-content .roadmap-stage-card');

    const panel = document.createElement('div');
    panel.style.cssText = `
        background: #0e0c06; border: 4px solid #c89820;
        border-radius: 6px; padding: 22px 28px; box-shadow: 4px 4px 0 #1a1008;
    `;

    const head = document.createElement('div');
    head.style.cssText = `font-size: 18px; font-weight: bold; color: #f7d51d;
        border-bottom: 2px solid #c89820; padding-bottom: 10px; margin-bottom: 20px;`;
    head.textContent = '🏯 나의 면천 로드맵';
    panel.appendChild(head);

    const row = document.createElement('div');
    row.style.cssText = `display: flex; gap: 16px; align-items: stretch;`;

    const roadmapCards = Array.from(cards).filter(c => {
        const title = c.querySelector('.title');
        return title && !c.classList.contains('chatbot-stage-card');
    });

    roadmapCards.forEach((card, idx) => {
        const colDiv = document.createElement('div');
        colDiv.style.cssText = `
            flex: 1; background: #1e1a0e;
            border: 3px solid #c89820; border-radius: 6px;
            padding: 18px 20px; min-width: 0; box-shadow: 3px 3px 0 #000;
        `;

        const titleEl = card.querySelector('.title');
        const titleDiv = document.createElement('div');
        titleDiv.style.cssText = `
            font-size: 16px; font-weight: bold; color: #f7d51d;
            margin-bottom: 14px; padding-bottom: 8px; border-bottom: 2px solid #3d2b1a;
        `;
        titleDiv.textContent = titleEl ? titleEl.textContent : `제${idx + 1}관문`;
        colDiv.appendChild(titleDiv);

        const descEl = card.querySelector('.roadmap-desc');
        if (descEl) {
            const d = document.createElement('div');
            d.style.cssText = `
                font-size: 13px; color: #f0e0b0; line-height: 1.75;
                background: rgba(245,230,200,0.08);
                border: 1px solid #3d2b1a; border-radius: 4px;
                padding: 10px 12px; margin-bottom: 10px;
            `;
            d.innerHTML = descEl.innerHTML;
            colDiv.appendChild(d);
        }

        const resultEl = card.querySelector('.result-box');
        if (resultEl) {
            const r = document.createElement('div');
            r.style.cssText = `
                font-size: 13px; color: #a8e6b0; line-height: 1.7;
                border-left: 4px solid #4aa52e; background: rgba(74,165,46,0.08);
                padding: 8px 12px; margin-bottom: 8px; border-radius: 0 4px 4px 0;
            `;
            r.innerHTML = resultEl.innerHTML;
            colDiv.appendChild(r);
        }

        const tipEl = card.querySelector('.tip-box');
        if (tipEl) {
            const t = document.createElement('div');
            t.style.cssText = `
                font-size: 13px; color: #f0d070; line-height: 1.7;
                border-left: 4px solid #EF9F27; background: rgba(239,159,39,0.08);
                padding: 8px 12px; border-radius: 0 4px 4px 0;
            `;
            t.innerHTML = tipEl.innerHTML;
            colDiv.appendChild(t);
        }

        row.appendChild(colDiv);
    });

    panel.appendChild(row);
    return panel;
}

// ────────────────────────────────────────────────────

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