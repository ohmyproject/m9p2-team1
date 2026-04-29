(function () {
  const scoreOrder = [
    { label: "현실형", code: "R" },
    { label: "탐구형", code: "I" },
    { label: "예술형", code: "A" },
    { label: "사회형", code: "S" },
    { label: "진취형", code: "E" },
    { label: "관습형", code: "C" },
  ];

  const state = {
    selectedFile: null,
    extractedScores: null,
    recommendedJobs: [],
    selectedJob: null,
    profile: {},
    chatStep: "idle",
    currentRoadmap: null,
  };

  const elements = {
    dropzone: document.getElementById("dropzone"),
    fileInput: document.getElementById("file-input"),
    fileName: document.getElementById("file-name"),
    analyzeBtn: document.getElementById("analyze-btn"),
    statusText: document.getElementById("status-text"),
    analysisView: document.getElementById("analysis-view"),
    chatView: document.getElementById("chat-view"),
    scoresGrid: document.getElementById("scores-grid"),
    top3Chip: document.getElementById("top3-chip"),
    radarChart: document.getElementById("radar-chart"),
    recommendations: document.getElementById("recommendations"),
    backBtn: document.getElementById("back-btn"),
    selectedJobPanel: document.getElementById("selected-job-panel"),
    chatThread: document.getElementById("chat-thread"),
    choiceRow: document.getElementById("choice-row"),
    roadmapShell: document.getElementById("roadmap-shell"),
    roadmapDrawer: document.getElementById("roadmap-drawer"),
    roadmapDrawerBackdrop: document.getElementById("roadmap-drawer-backdrop"),
    roadmapDrawerClose: document.getElementById("roadmap-drawer-close"),
    roadmapDrawerTitle: document.getElementById("roadmap-drawer-title"),
    roadmapDrawerMeta: document.getElementById("roadmap-drawer-meta"),
    roadmapDrawerBody: document.getElementById("roadmap-drawer-body"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function summarizeText(value, maxLength = 140) {
    const compact = String(value ?? "").replace(/\s+/g, " ").trim();
    if (compact.length <= maxLength) return compact;
    return `${compact.slice(0, maxLength - 1).trim()}…`;
  }

  function parseRawRoadmapSteps(rawText) {
    const text = String(rawText || "");
    const pattern = /(?:^|\n)\s*(?:■\s*)?([123])단계\s*[:：]\s*([^\n]+)\n?([\s\S]*?)(?=\n\s*(?:■\s*)?[123]단계\s*[:：]|$)/g;
    const steps = [];
    let match;

    while ((match = pattern.exec(text)) && steps.length < 3) {
      const [, number, heading, body] = match;
      const actions = [];
      let output = "";

      body.split(/\n/).forEach((line) => {
        const cleaned = line.trim().replace(/^[-•]\s*/, "");
        if (!cleaned) return;
        if (cleaned.includes("결과물") && !output) {
          output = cleaned.includes(":") ? cleaned.split(":").slice(1).join(":").trim() : cleaned;
          return;
        }
        if (actions.length < 3) actions.push(cleaned);
      });

      steps.push({
        title: `Step ${number}. ${heading.trim()}`,
        period: "AI 생성",
        actions: actions.length ? actions.slice(0, 3) : [summarizeText(body, 90)],
        output: output || "전체 내용 보기에서 세부 결과물을 확인하세요.",
      });
    }

    return steps;
  }

  function normalizeRoadmapData(data) {
    const normalized = { ...(data || {}) };
    if ((!Array.isArray(normalized.steps) || normalized.steps.length === 0) && normalized.raw_text) {
      const parsedSteps = parseRawRoadmapSteps(normalized.raw_text);
      if (parsedSteps.length) normalized.steps = parsedSteps;
    }
    if (!normalized.summary && normalized.raw_text) {
      normalized.summary = summarizeText(normalized.raw_text, 170);
    }
    return normalized;
  }

  function openRoadmapDrawer() {
    const roadmap = state.currentRoadmap;
    if (!roadmap || !roadmap.raw_text) return;

    elements.roadmapDrawerTitle.textContent = `${state.selectedJob?.title || "선택 직무"} 전체 로드맵`;
    elements.roadmapDrawerMeta.textContent = [state.profile.major, "AI 생성"]
      .filter(Boolean)
      .join(" · ");
    elements.roadmapDrawerBody.textContent = roadmap.raw_text;
    elements.roadmapDrawer.classList.remove("is-hidden");
    elements.roadmapDrawerBackdrop.classList.remove("is-hidden");
    elements.roadmapDrawer.setAttribute("aria-hidden", "false");
  }

  function closeRoadmapDrawer() {
    elements.roadmapDrawer.classList.add("is-hidden");
    elements.roadmapDrawerBackdrop.classList.add("is-hidden");
    elements.roadmapDrawer.setAttribute("aria-hidden", "true");
  }

  function setStatus(message, kind = "") {
    elements.statusText.textContent = message;
    elements.statusText.className = kind ? `status ${kind}` : "status";
  }

  function formatScore(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric.toFixed(0) : "-";
  }

  function formatSimilarity(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric.toFixed(4) : "-";
  }

  function scoreEntries() {
    return scoreOrder.map((item) => {
      const score = state.extractedScores?.[item.label] || {};
      return {
        ...item,
        raw: Number(score["원점수"] ?? 0),
        tScore: Number(score["T점수"] ?? 0),
      };
    });
  }

  function top3Codes() {
    return scoreEntries()
      .sort((a, b) => (b.raw - a.raw) || (b.tScore - a.tScore))
      .slice(0, 3)
      .map((item) => item.code)
      .join("");
  }

  function setFile(file) {
    if (!file) return;
    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      state.selectedFile = null;
      elements.fileName.textContent = "PDF 파일만 선택할 수 있습니다.";
      setStatus("PDF 파일만 업로드할 수 있습니다.", "error");
      return;
    }

    state.selectedFile = file;
    elements.fileName.textContent = file.name;
    elements.dropzone.classList.add("has-file");
    setStatus("분석 버튼을 누르면 추천직무를 계산합니다.");
  }

  function showAnalysisView() {
    elements.analysisView.classList.remove("is-hidden");
    elements.chatView.classList.add("is-hidden");
  }

  function showChatView() {
    elements.analysisView.classList.add("is-hidden");
    elements.chatView.classList.remove("is-hidden");
  }

  function renderScores() {
    if (!state.extractedScores) {
      elements.scoresGrid.innerHTML = '<div class="empty">분석 후 표준점수와 원점수가 여기에 표시됩니다.</div>';
      elements.top3Chip.textContent = "TOP3 -";
      return;
    }

    elements.top3Chip.textContent = `TOP3 ${top3Codes()}`;
    elements.scoresGrid.innerHTML = scoreEntries().map((score) => `
      <article class="score-card">
        <div class="score-card-head">
          <span class="score-code">${score.code}</span>
          <span class="score-name">${escapeHtml(score.label)}</span>
        </div>
        <div class="score-t">${formatScore(score.tScore)}</div>
        <div class="score-raw">원점수 ${formatScore(score.raw)}</div>
      </article>
    `).join("");
  }

  function radarPoint(cx, cy, radius, index) {
    const angle = (-90 + index * 60) * Math.PI / 180;
    return {
      x: cx + Math.cos(angle) * radius,
      y: cy + Math.sin(angle) * radius,
    };
  }

  function pointList(points) {
    return points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");
  }

  function renderRadar() {
    if (!state.extractedScores) {
      elements.radarChart.innerHTML = '<div class="empty">점수가 추출되면 6축 그래프가 나타납니다.</div>';
      return;
    }

    const cx = 160;
    const cy = 150;
    const maxRadius = 104;
    const entries = scoreEntries();
    const levels = [0.2, 0.4, 0.6, 0.8, 1];
    const grid = levels.map((level) => {
      const points = entries.map((_, index) => radarPoint(cx, cy, maxRadius * level, index));
      return `<polygon class="radar-grid-line" points="${pointList(points)}"></polygon>`;
    }).join("");
    const axes = entries.map((_, index) => {
      const edge = radarPoint(cx, cy, maxRadius, index);
      return `<line class="radar-axis" x1="${cx}" y1="${cy}" x2="${edge.x.toFixed(1)}" y2="${edge.y.toFixed(1)}"></line>`;
    }).join("");
    const shapePoints = entries.map((entry, index) => {
      const radius = Math.max(0, Math.min(100, entry.tScore)) / 100 * maxRadius;
      return radarPoint(cx, cy, radius, index);
    });
    const labels = entries.map((entry, index) => {
      const labelPoint = radarPoint(cx, cy, maxRadius + 27, index);
      return `<text class="radar-label" x="${labelPoint.x.toFixed(1)}" y="${labelPoint.y.toFixed(1)}">${entry.code}</text>`;
    }).join("");

    elements.radarChart.innerHTML = `
      <svg class="radar-svg" viewBox="0 0 320 300" role="img" aria-label="RIASEC 표준점수 육각형 그래프">
        ${grid}
        ${axes}
        <polygon class="radar-shape" points="${pointList(shapePoints)}"></polygon>
        ${shapePoints.map((point) => `<circle class="radar-dot" cx="${point.x.toFixed(1)}" cy="${point.y.toFixed(1)}" r="4"></circle>`).join("")}
        ${labels}
      </svg>
    `;
  }

  function renderRecommendations() {
    if (!state.recommendedJobs.length) {
      elements.recommendations.innerHTML = '<div class="empty">분석 버튼을 누르면 현재 유사도 기반 추천직무가 표시됩니다.</div>';
      return;
    }

    elements.recommendations.innerHTML = state.recommendedJobs.map((job) => `
      <article class="job-card" data-job-id="${escapeHtml(job.id)}">
        <div class="job-card-body">
          <div class="job-card-top">
            <span class="job-rank">${escapeHtml(job.rank || "-")}</span>
            <span class="similarity">유사도 ${formatSimilarity(job.final_score)}</span>
          </div>
          <div class="job-title-row">
            <h3>${escapeHtml(job.title)}</h3>
          </div>
          <p>${escapeHtml(job.description || "직무 정의 요약이 없습니다.")}</p>
          <div class="job-meta">
            <span>${escapeHtml(job.category || "-")}</span>
            <span>Top3 ${escapeHtml(job.top3 || "-")}</span>
          </div>
          <div class="tag-row">
            ${(job.tags || []).slice(0, 2).map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("")}
          </div>
          <div class="job-action">선택해서 로드맵 생성</div>
        </div>
      </article>
    `).join("");
  }

  function selectedJobMarkup() {
    const job = state.selectedJob;
    if (!job) return "";
    return `
      <div class="selected-job-head">
        <div>
          <p class="eyebrow">선택 직무</p>
          <h1>${escapeHtml(job.title)}</h1>
        </div>
        <span class="similarity">유사도 ${formatSimilarity(job.final_score)}</span>
      </div>
      <p class="selected-desc">${escapeHtml(job.description || "")}</p>
      <div class="job-meta">
        <span>${escapeHtml(job.category || "-")}</span>
        <span>${escapeHtml(job.onet_title || "-")}</span>
        <span>Top3 ${escapeHtml(job.top3 || "-")}</span>
      </div>
    `;
  }

  function renderChat() {
    const messages = [];
    if (state.selectedJob) {
      messages.push({ who: "bot", text: `${state.selectedJob.title} 로드맵을 만들기 위해 전공 여부만 확인할게요.` });
    }
    if (state.profile.major) {
      messages.push({ who: "user", text: state.profile.major });
    }
    if (state.chatStep === "major") {
      messages.push({ who: "bot", text: "이 직무는 전공 기반으로 준비하나요, 비전공에서 시작하나요?" });
    }
    if (state.chatStep === "loading") {
      messages.push({ who: "bot", text: "답변을 반영해 3단계 로드맵을 생성하고 있습니다." });
    }

    elements.chatThread.innerHTML = messages.map((message) => `
      <div class="message ${message.who}">
        <div class="message-bubble">${escapeHtml(message.text)}</div>
      </div>
    `).join("");

    if (state.chatStep === "major") {
      elements.choiceRow.innerHTML = `
        <button class="choice-btn" data-major="전공자" type="button">전공자</button>
        <button class="choice-btn" data-major="비전공자" type="button">비전공자</button>
      `;
    } else {
      elements.choiceRow.innerHTML = "";
    }
  }

  function renderRoadmap(data) {
    const roadmap = normalizeRoadmapData(data);
    const steps = roadmap.steps || [];
    const hasRawText = Boolean(String(roadmap.raw_text || "").trim());
    const certifications = roadmap.certifications || [];
    const resources = roadmap.resources || [];
    const hasExtra = certifications.length > 0 || resources.length > 0;
    state.currentRoadmap = roadmap;

    elements.roadmapShell.innerHTML = `
      <div class="roadmap-head">
        <p class="eyebrow">맞춤 로드맵</p>
        <h2>${escapeHtml(state.selectedJob?.title || "선택 직무")}</h2>
        <div class="answer-summary">
          <span>${escapeHtml(state.profile.major || "-")}</span>
          <span>AI 생성</span>
        </div>
        ${hasRawText ? '<button class="ghost-btn roadmap-full-btn" data-roadmap-open="true" type="button">전체 내용 보기</button>' : ""}
      </div>
      <p class="roadmap-summary">${escapeHtml(roadmap.summary || "")}</p>
      <div class="roadmap-steps">
        ${steps.map((step, index) => `
          <article class="step-card ${hasRawText ? "is-clickable" : ""}" ${hasRawText ? 'data-roadmap-open="true" tabindex="0" role="button" aria-label="전체 로드맵 보기"' : ""}>
            <div class="step-number">${index + 1}</div>
            <div>
              <div class="step-head">
                <h3>${escapeHtml(step.title || `Step ${index + 1}`)}</h3>
                <span>${escapeHtml(step.period || "-")}</span>
              </div>
              <ul>${(step.actions || []).map((action) => `<li>${escapeHtml(action)}</li>`).join("")}</ul>
              <p class="step-output">결과물: ${escapeHtml(step.output || "-")}</p>
            </div>
          </article>
        `).join("")}
      </div>
      ${hasExtra ? `
        <div class="roadmap-extra">
          ${certifications.length ? `
            <section>
              <h3>자격증과 공부방향</h3>
              <ul>${certifications.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
            </section>
          ` : ""}
          ${resources.length ? `
            <section>
              <h3>참고 자료</h3>
              <ul>${resources.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
            </section>
          ` : ""}
        </div>
      ` : ""}
    `;
  }

  async function createRoadmap() {
    if (!state.selectedJob) return;
    state.chatStep = "loading";
    state.currentRoadmap = null;
    closeRoadmapDrawer();
    renderChat();
    elements.roadmapShell.innerHTML = '<div class="loading-box">로드맵 생성 중...</div>';

    try {
      const response = await fetch("/roadmap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: Number(state.selectedJob.id),
          profile: {
            major: state.profile.major,
          },
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "로드맵 생성에 실패했습니다.");
      state.chatStep = "complete";
      renderChat();
      renderRoadmap(data.roadmap || {});
      setStatus(`${state.selectedJob.title} 로드맵이 생성되었습니다.`, "success");
    } catch (error) {
      state.chatStep = "major";
      state.profile.major = "";
      renderChat();
      elements.roadmapShell.innerHTML = `<div class="empty">${escapeHtml(error.message || "로드맵을 생성하지 못했습니다.")}</div>`;
      setStatus(error.message || "로드맵 생성 중 오류가 발생했습니다.", "error");
    }
  }

  function startJobConversation(job) {
    state.selectedJob = job;
    state.profile = {};
    state.chatStep = "major";
    state.currentRoadmap = null;
    closeRoadmapDrawer();
    elements.selectedJobPanel.innerHTML = selectedJobMarkup();
    elements.roadmapShell.innerHTML = "";
    renderChat();
    showChatView();
    setStatus(`${job.title} 로드맵 질문을 시작합니다.`);
  }

  async function analyzePdf() {
    if (!state.selectedFile) {
      setStatus("먼저 PDF 파일을 선택해주세요.", "error");
      return;
    }

    elements.analyzeBtn.disabled = true;
    setStatus("PDF를 분석하고 추천직무를 계산하는 중입니다...");

    const formData = new FormData();
    formData.append("file", state.selectedFile);

    try {
      const response = await fetch("/recommend", { method: "POST", body: formData });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "PDF 분석에 실패했습니다.");

      state.extractedScores = data.extracted_scores;
      state.recommendedJobs = data.recommendations || [];
      state.selectedJob = null;
      state.profile = {};
      state.chatStep = "idle";
      state.currentRoadmap = null;
      closeRoadmapDrawer();

      renderScores();
      renderRadar();
      renderRecommendations();
      showAnalysisView();
      setStatus("분석이 완료되었습니다. 추천직무를 선택하면 로드맵 질문이 시작됩니다.", "success");
    } catch (error) {
      setStatus(error.message || "PDF 분석 중 오류가 발생했습니다.", "error");
    } finally {
      elements.analyzeBtn.disabled = false;
    }
  }

  function bindEvents() {
    elements.fileInput.addEventListener("change", () => setFile(elements.fileInput.files[0]));
    elements.dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        elements.fileInput.click();
      }
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      elements.dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        elements.dropzone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      elements.dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        elements.dropzone.classList.remove("is-dragging");
      });
    });
    elements.dropzone.addEventListener("drop", (event) => {
      setFile(event.dataTransfer.files[0]);
    });

    elements.analyzeBtn.addEventListener("click", analyzePdf);
    elements.backBtn.addEventListener("click", () => {
      closeRoadmapDrawer();
      showAnalysisView();
      setStatus("추천 결과로 돌아왔습니다.");
    });

    elements.recommendations.addEventListener("click", (event) => {
      const card = event.target.closest("[data-job-id]");
      if (!card) return;
      const job = state.recommendedJobs.find((item) => String(item.id) === card.dataset.jobId);
      if (job) startJobConversation(job);
    });

    elements.choiceRow.addEventListener("click", (event) => {
      const button = event.target.closest("button");
      if (!button) return;
      if (button.dataset.major) {
        state.profile.major = button.dataset.major;
        createRoadmap();
      }
    });

    elements.roadmapShell.addEventListener("click", (event) => {
      if (event.target.closest("[data-roadmap-open]")) openRoadmapDrawer();
    });

    elements.roadmapShell.addEventListener("keydown", (event) => {
      const trigger = event.target.closest("[data-roadmap-open]");
      if (!trigger || (event.key !== "Enter" && event.key !== " ")) return;
      event.preventDefault();
      openRoadmapDrawer();
    });

    elements.roadmapDrawerClose.addEventListener("click", closeRoadmapDrawer);
    elements.roadmapDrawerBackdrop.addEventListener("click", closeRoadmapDrawer);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeRoadmapDrawer();
    });
  }

  function init() {
    bindEvents();
    renderScores();
    renderRadar();
    renderRecommendations();
  }

  init();
})();
