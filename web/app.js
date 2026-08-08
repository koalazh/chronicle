const app = document.querySelector("#app");

const state = {
  page: "cover",
  scenario: null,
  timeline: [],
  tick: 0,
  selectedEvent: null,
  eventDetail: null,
  source: null,
  drawer: false,
  setup: false,
  settings: false,
  config: null,
  lifetimeSeat: "A",
  lifetime: null,
  branch: null,
  branchRecords: [],
  setupMessage: null,
};

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
  return body;
}

async function loadBase() {
  const [scenario, timeline, config] = await Promise.all([
    api("/api/scenario"), api("/api/timeline"), api("/api/config"),
  ]);
  state.scenario = scenario;
  state.timeline = timeline.items;
  state.tick = timeline.current_tick;
  state.config = config;
  state.setup = config.setup_required;
  state.selectedEvent = state.timeline.find((item) => item.is_current)?.id || state.timeline[0]?.id;
  if (state.selectedEvent) state.eventDetail = await api(`/api/events/${state.selectedEvent}?tick=${state.tick}`);
}

function render() {
  if (!state.scenario) {
    app.innerHTML = '<div class="boot-state"><span class="eyebrow">CHRONICLE / 甲申</span><span>正在打开观测台</span></div>';
    return;
  }
  if (state.page === "cover") renderCover();
  else if (state.page === "chronicle") renderChronicle();
  else if (state.page === "lifetimes") renderLifetimes();
  else if (state.page === "branch") renderBranch();
  else renderAbout();
  if (state.drawer) renderDrawer();
  if (state.setup || state.settings) renderSettingsModal();
}

function renderCover() {
  app.innerHTML = `
    <main class="cover" data-testid="cover">
      <svg class="cover-map" viewBox="0 0 1000 650" aria-hidden="true">
        <path d="M112 485 C260 400 290 205 482 252 S722 384 882 150" />
        <path d="M154 550 C330 520 438 370 560 335 S780 290 910 232" />
        <path d="M160 420 C330 420 420 110 680 140 S805 205 920 280" />
        <line x1="152" y1="485" x2="872" y2="150" /><line x1="470" y1="250" x2="820" y2="500" />
        <circle cx="482" cy="252" r="4" /><circle cx="882" cy="150" r="4" /><circle cx="820" cy="500" r="4" />
      </svg>
      <div class="cover-content">
        <div class="cover-kicker">CHRONICLE / DIGITAL HISTORICAL OBSERVATORY</div>
        <h1 class="cover-title">甲申</h1>
        <p class="cover-subtitle">崇祯十七年，最后一个春天。</p>
        <p class="cover-copy"><span>三个主体。</span><span>三份彼此不同的世界。</span><span>一段已经发生、却尚未成为过去的历史。</span></p>
        <button class="cover-enter" data-action="enter">进入 Chronicle&nbsp; →</button>
      </div>
      <div class="cover-meta">正月初一 — 三月十九 / 1644</div>
    </main>`;
  bindActions();
}

function renderShell(content, page) {
  app.innerHTML = `
    <header class="topbar">
      <button class="brand" data-action="home" aria-label="返回首页"><span class="brand-mark">甲</span><span class="brand-name">Chronicle</span></button>
      <nav class="nav" aria-label="Primary navigation">
        <button data-page="chronicle" aria-current="${page === "chronicle" ? "page" : "false"}">Chronicle</button>
        <button data-page="lifetimes" aria-current="${page === "lifetimes" ? "page" : "false"}">Lifetimes</button>
        ${state.branch ? `<button data-page="branch" aria-current="${page === "branch" ? "page" : "false"}">Branch</button>` : ""}
        <button data-page="about" aria-current="${page === "about" ? "page" : "false"}">About</button>
      </nav>
      <button class="utility-button" data-action="settings" aria-label="Runtime settings">⋯<span>Runtime</span></button>
    </header>${content}`;
  bindActions();
}

function renderChronicle() {
  const event = state.eventDetail?.event || {};
  const assertion = state.eventDetail?.assertions?.[0] || {};
  const whoKnows = state.eventDetail?.who_knows?.[assertion.id] || {};
  const knowledge = state.scenario.actors.map((actor) => {
    const known = whoKnows[actor.seat];
    return `<div class="knowledge-row"><div><div class="knowledge-name">${escapeHtml(actor.display_name)}</div><div class="knowledge-seat">${escapeHtml(actor.runtime_alias)} / ${escapeHtml(actor.profile)}</div></div><div class="knowledge-status ${known ? "new" : "unknown"}">${known ? "已知" : "尚未获知"}</div></div>`;
  }).join("");
  const timeline = state.timeline.map((item) => `<button class="timeline-item" data-event="${item.id}" data-marker="${item.marker}" data-past="${item.is_past}" aria-current="${item.id === state.selectedEvent}"><span class="timeline-dot"></span><span><span class="timeline-date">${escapeHtml(item.native_date.split("崇祯十七年").pop())}</span><span class="timeline-title">${escapeHtml(item.title)}</span><span class="timeline-tag">${escapeHtml(item.marker)}${item.has_fork ? " / fork" : ""}</span></span></button>`).join("");
  const mapNodes = state.scenario.locations.map((location) => `<g><circle class="map-node ${location.id === (event.world_effects || []).find((effect) => effect.target === location.id)?.target ? "active" : ""}" cx="${location.x}%" cy="${location.y}%" r="1.2"></circle><text class="map-label" x="${location.x + 1.4}%" y="${location.y - 1}%">${escapeHtml(location.display_name)}</text><text class="map-alias" x="${location.x + 1.4}%" y="${location.y + 2}%">${escapeHtml(location.runtime_alias)}</text></g>`).join("");
  const mapLines = state.scenario.routes.map((route) => { const from = state.scenario.locations.find((x) => x.id === route.from_location); const to = state.scenario.locations.find((x) => x.id === route.to_location); return from && to ? `<line class="map-route ${route.id.includes("capital") ? "canonical" : ""}" x1="${from.x}%" y1="${from.y}%" x2="${to.x}%" y2="${to.y}%"></line>` : ""; }).join("");
  const eventText = assertion.normalized_evidence || "这条事件记录由 Source Pack 与 Chronicle Host 共同约束。";
  const currentDate = event.native_date || state.scenario.summary.window.start;
  const page = `<main class="page" data-testid="chronicle-page">
    <section class="page-header"><div><div class="page-kicker">CHRONICLE / CANON</div><h1 class="page-title">谁知道什么，何时知道？</h1></div><p class="page-lede">历史事实属于 Canon。信息必须经过传播。每个主体只带着自己真正收到的东西进入下一次判断。</p></section>
    <section class="chronicle-layout">
      <aside class="timeline" aria-label="Historical timeline"><div class="timeline-heading"><span class="section-label">TIMELINE</span><span class="timeline-range">${state.timeline.length} EVENTS</span></div>${timeline}</aside>
      <section class="observatory"><div class="observatory-top"><div><div class="date-display">${escapeHtml(currentDate)}</div><div class="tick-display">DAY ${String(state.tick).padStart(2, "0")} / CANON WINDOW</div></div><button class="advance-button" data-action="advance">推进一天&nbsp; →</button></div>
        <div class="map-frame"><svg class="map-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="甲申路线图">${mapLines}${mapNodes}<path class="map-route" d="M13 64 C36 50 51 38 70 44 S82 53 91 30" vector-effect="non-scaling-stroke"></path><circle class="map-message" cx="58" cy="43" r="1.2"></circle></svg><div class="map-legend"><span>route</span><span>message in transit</span></div></div>
        <div class="current-event"><div class="event-eyebrow"><span>CURRENT EVENT</span><span>〔${escapeHtml(assertion.evidence_status || "SOURCE")}〕</span></div><h2 class="event-title">${escapeHtml(event.title || "等待事件")}</h2><p class="event-copy">${escapeHtml(eventText)}</p><div class="event-actions"><button class="text-button" data-source="${escapeHtml(assertion.id || "")}">查看史料&nbsp;〔${escapeHtml(assertion.id || "—")}〕</button>${state.selectedEvent === state.scenario.fork.event_id ? `<button class="text-button" data-action="create-branch">从这里分叉&nbsp; ↘</button>` : ""}</div></div>
      </section>
      <aside class="context-panel"><div class="section-label">CONTEXT / KNOWLEDGE</div><h2 class="context-title">WHO KNOWS?</h2><p class="context-copy">世界已经发生，不等于每一个主体都已获知。</p><div class="knowledge-list">${knowledge}</div><div class="context-note">信息的延迟不是噪音。它就是这个实验的世界。</div></aside>
    </section></main>`;
  renderShell(page, "chronicle");
}

function renderLifetimes() {
  if (!state.lifetime) {
    const entries = state.scenario.actors.map((actor) => `<article class="lifetime-entry"><div class="seat-label">${escapeHtml(actor.runtime_alias)} / LONG-TERM SUBJECT</div><h3>${escapeHtml(actor.display_name)} · Lifetime</h3><p>${escapeHtml(actor.description)}</p><div class="lifetime-stats"><div class="stat"><strong>—</strong><span>observations</span></div><div class="stat"><strong>—</strong><span>intentions</span></div><div class="stat"><strong>—</strong><span>memories</span></div></div><button class="open-lifetime" data-seat="${actor.seat}">打开 Lifetime&nbsp; →</button></article>`).join("");
    renderShell(`<main class="page" data-testid="lifetimes-page"><section class="page-header"><div><div class="page-kicker">LIFETIMES / THREE SUBJECTS</div><h1 class="page-title">他们留下了什么？</h1></div><p class="page-lede">Life Record 记录一个主体真正经历过什么。Hermes Memory 只代表它选择带进未来的有限主观经验。</p></section><section class="lifetimes-grid">${entries}</section></main>`, "lifetimes");
    return;
  }
  const life = state.lifetime;
  const actor = life.actor;
  const records = life.records.length ? life.records.map((record, index) => `<div class="life-record"><div class="life-record-date">DAY ${String(record.tick).padStart(2, "0")}</div><div class="life-record-dot ${record.wake_type === "reflection" ? "memory" : ""}"></div><div><div class="life-record-title">${record.wake_type === "reflection" ? "Reflection / 主观记忆重新排列" : `${record.observation_ids.length} observations received`}</div><div class="life-record-meta">${record.intentions.length} intentions · epoch ${escapeHtml(record.runtime_epoch)}</div></div></div>`).join("") : `<div class="muted" style="padding:20px 0">还没有 Wake。推进 Canon 后，可以从这里唤醒一个主体。</div>`;
  const memory = life.memory.text || "暂未形成 durable memory。只有 Reflection 才能让经验进入这里。";
  const seats = state.scenario.actors.map((item) => `<button class="${item.seat === state.lifetimeSeat ? "active" : ""}" data-seat="${item.seat}">${escapeHtml(item.display_name)}</button>`).join("");
  renderShell(`<main class="page" data-testid="lifetime-page"><section class="page-header"><div><div class="page-kicker">LIFETIME / ${escapeHtml(actor.runtime_alias)}</div><h1 class="page-title">${escapeHtml(actor.display_name)} · Lifetime</h1></div><p class="page-lede">不是聊天记录。是一条由观察、判断、矛盾与记忆组成的生命线。</p></section><section class="lifetime-detail"><aside class="lifetime-rail"><div class="section-label">SEAT</div><div class="seat-switcher">${seats}</div><div class="context-note">只展示 Host 可追溯的经历；未收到的信息不进入这里。</div></aside><section class="life-content"><div class="life-intro"><div><h2>DAY ${String(state.tick).padStart(2, "0")}</h2><p>${life.stats.observations} observations · ${life.stats.intentions} intentions · ${life.stats.memories} durable memories</p></div><button class="primary-button" data-action="wake">Wake this Lifetime</button></div><div class="life-line"><div class="section-label">LIFE RECORD / APPEND-ONLY</div><div class="life-line-track"><span class="life-marker" style="left:8%" data-label="observation"></span><span class="life-marker contradiction" style="left:55%" data-label="contradiction"></span><span class="life-marker memory" style="left:82%" data-label="memory"></span></div>${records}</div><div class="memory-lineage"><div class="section-label">HERMES MEMORY / SUBJECTIVE</div><h3>${life.memory.versions.length ? "A memory carried forward" : "No durable memory yet"}</h3><p>${escapeHtml(memory)}</p><div class="lineage-flow"><span>Observation</span><span>Belief</span><span>Contradicting event</span><span>Reflection</span><span>Memory</span></div></div></section></section></main>`, "lifetimes");
}

function renderBranch() {
  const branch = state.branch;
  const fork = state.scenario.fork;
  if (!branch) {
    renderShell(`<main class="page" data-testid="branch-page"><section class="page-header"><div><div class="page-kicker">BRANCH / ONE CURATED FORK</div><h1 class="page-title">如果提议被接受？</h1></div><p class="page-lede">Branch 不是改变历史的按钮。它只从一个真实提出过的节点出发，沿着 Host 能够支撑的规则走十四天。</p></section><section class="branch-hero"><div><div class="section-label">HISTORICAL DECISION</div><h2>${escapeHtml(fork.display_name)}</h2><p>南迁相关讨论中的“太子抚军江南”路线未获采纳。Chronicle 允许一次、且只有一次有边界的分叉。</p><div class="branch-actions"><button class="primary-button" data-action="create-branch">接受这项提议&nbsp; ↘</button></div></div><div class="branch-premise"><strong>Chronicle constraint</strong><span>${escapeHtml(fork.runtime_premise)}<br />14 simulated days maximum.<br />No World Master LLM.</span></div></section></main>`, "branch");
    return;
  }
  const stateView = branch.state_json || {};
  const status = branch.status === "boundary";
  const records = state.branchRecords || [];
  const recordText = records.length ? records.slice(-3).map((record) => `<div class="branch-state-row"><strong>DAY ${record.tick}</strong><span>${escapeHtml(record.result_json.message || record.result_json.reason || record.action_json.type)}</span></div>`).join("") : `<div class="muted" style="padding:15px 0">尚未提交 Branch action。</div>`;
  renderShell(`<main class="page" data-testid="branch-page"><section class="page-header"><div><div class="page-kicker">BRANCH / ${status ? "MODEL BOUNDARY" : "SIMULATED DAY " + stateView.day_offset}</div><h1 class="page-title">Canon / Branch</h1></div><p class="page-lede">共同状态淡出；差异只在它们真正进入世界之后出现。</p></section><section class="branch-board"><div class="branch-columns"><div class="branch-column"><h3>CANON <span>HISTORICAL</span></h3><div class="branch-state-row"><strong>Historical choice</strong><span>提议未获采纳</span></div><div class="branch-state-row"><strong>World</strong><span>Host 继续推进 Canon Event Deck</span></div><div class="branch-state-row"><strong>Boundary</strong><span>三月十九日停止</span></div></div><div class="branch-column"><h3>BRANCH <span>BRANCH-DERIVED</span></h3><div class="branch-state-row"><strong>Premise</strong><span>${escapeHtml(fork.display_name)} 已被接受</span></div><div class="branch-state-row"><strong>Day</strong><span>${stateView.day_offset || 0} / 14 simulated days</span></div><div class="branch-state-row"><strong>Messages</strong><span>${(stateView.messages || []).length} in transit / delivered by Host</span></div>${recordText}</div></div>${status ? `<div class="boundary"><h2>The model ends here.</h2><p>推演在这里停止。</p><ul><li>历史事件不再由 LLM 自动补写</li><li>当前世界状态仍可追溯</li><li>继续推演需要未经支持的假设</li></ul></div>` : `<div class="branch-controls"><label for="branch-seat">ACTOR</label><select id="branch-seat"><option value="A">Seat A / 崇祯</option><option value="B">Seat B / 李自成</option><option value="C">Seat C / 吴三桂</option></select><label for="branch-action">INTENTION</label><select id="branch-action"><option value="WAIT">WAIT / 等待</option><option value="SEND_MESSAGE">SEND_MESSAGE / 传递消息</option><option value="ISSUE_ORDER">ISSUE_ORDER / 发出命令</option><option value="PREPARE_MOVEMENT">PREPARE_MOVEMENT / 准备移动</option></select><button class="primary-button" data-action="branch-step">提交 intention&nbsp; →</button></div>`}</section></main>`, "branch");
}

function renderAbout() {
  renderShell(`<main class="page" data-testid="about-page"><section class="page-header"><div><div class="page-kicker">ABOUT / METHOD</div><h1 class="page-title">让历史保持它的边界。</h1></div><p class="page-lede">Chronicle 不重建任何人的心。它只观察：有限信息如何进入一个长期存在的主体，并在之后改变它。</p></section><section class="about-grid"><div class="formula">Truth <span>≠</span> Knowledge <span>≠</span> Belief</div><article class="about-block"><h2>Canonical Chronicle</h2><p>时间、史料事实、消息送达、Seat 权限和世界状态都由 Chronicle Host 拥有。Agent 可以理解世界，但不能直接改写世界。</p></article><article class="about-block"><h2>Historical Blindness</h2><p>Runtime 使用 opaque alias。崇祯、李自成、吴三桂和后来的结局属于展示与审计层，不直接进入 Agent 的输入。</p></article><article class="about-block"><h2>Lifetime ≠ transcript</h2><p>每次 Wake 都是 Fresh Hermes Session。Life Record 完整记录经历；Hermes Memory 只留下主体真正选择携带的有限经验。</p></article><article class="about-block"><h2>Why stop?</h2><p>当下一步需要猜测未经约束的大战、联盟或长期政权命运，模型必须停止。一个诚实的边界比一段流畅的虚构更重要。</p></article><article class="about-block"><h2>What Branch means</h2><p>Branch 不是预测，也不是自由改史。V1 只有“太子抚军江南”这个有史料出处的节点，最多模拟十四天。</p></article><article class="about-block"><h2>Hermes Runtime</h2><p>三个 Seat 来自同一个 Actor Distribution，使用相同模型与协议。Host 只调用 Hermes 原生 HTTP/Session/Memory 能力，不再实现第二套 Agent Runtime。</p></article></section></main>`, "about");
}

function renderDrawer() {
  const assertion = state.source?.assertion || {};
  const citations = (state.source?.sources || []).map((source) => `<div class="citation"><strong>${escapeHtml(source.work)}</strong><span>${escapeHtml(source.locator)}</span><a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">打开来源 ↗</a></div>`).join("");
  const drawer = `<div class="drawer-scrim open" data-action="close-drawer"></div><aside class="source-drawer open" aria-label="Source Inspector"><button class="drawer-close" data-action="close-drawer">×</button><div class="drawer-kicker">SOURCE INSPECTOR / ${escapeHtml(assertion.id || "")}</div><h2 class="drawer-title">${escapeHtml(assertion.claim || "历史断言")}</h2><span class="drawer-status">${escapeHtml(assertion.evidence_status || "SOURCE")}</span><div class="drawer-section"><h3>NORMALIZED EVIDENCE</h3><p>${escapeHtml(assertion.normalized_evidence || "暂无归一化证据")}</p></div><div class="drawer-section"><h3>PRIMARY SOURCES</h3>${citations}</div><div class="drawer-section"><h3>PROVENANCE</h3><p>${escapeHtml(assertion.provenance || "historical")} / 这是 Source Pack 的审计字段，不是 Agent 的输入。</p></div></aside>`;
  app.insertAdjacentHTML("beforeend", drawer);
  bindActions();
}

function renderSettingsModal() {
  const config = state.config || {};
  const message = state.setupMessage ? `<div class="setup-result ${state.setupMessage.error ? "error" : ""}">${escapeHtml(state.setupMessage.text)}</div>` : "";
  const title = state.setup ? "Chronicle Setup" : "Runtime settings";
  const intro = state.setup ? "让三个 Seat 使用同一个 OpenAI-compatible provider。API Key 只会写入本机 server-side runtime secret。" : "Runtime model 的变化会创建新的 Runtime Epoch。跨 epoch 的 Lifetime 比较应单独解释。";
  const modal = `<div class="modal-scrim" data-action="close-settings"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="settings-title"><div class="page-kicker">RUNTIME / ${state.setup ? "FIRST RUN" : "SETTINGS"}</div><h2 id="settings-title">${title}</h2><p>${intro}</p><div class="form-field"><label for="runtime-base">API BASE URL</label><input id="runtime-base" value="${escapeHtml(config.base_url || "")}" placeholder="https://provider.example/v1" autocomplete="off" /></div><div class="form-field"><label for="runtime-key">API KEY</label><input id="runtime-key" type="password" placeholder="${config.api_key ? "保留当前 key" : "••••••••••••"}" autocomplete="new-password" /></div><div class="form-field"><label for="runtime-model">MODEL</label><input id="runtime-model" value="${escapeHtml(config.model || "")}" placeholder="deepseek-v4-flash" autocomplete="off" /></div><div class="form-field"><label for="runtime-mode">API MODE</label><select id="runtime-mode"><option value="chat_completions" ${config.api_mode === "chat_completions" ? "selected" : ""}>Chat Completions</option><option value="responses" ${config.api_mode === "responses" ? "selected" : ""}>Responses</option></select></div><div class="form-field"><label for="runtime-reasoning">REASONING EFFORT <span class="muted">optional</span></label><input id="runtime-reasoning" value="${escapeHtml(config.reasoning_effort || "")}" placeholder="留空使用 provider default" autocomplete="off" /></div>${message}<div class="modal-actions"><button class="secondary-button" data-action="test-setup">Test connection</button><button class="primary-button" data-action="save-settings">${state.setup ? "Configure Chronicle" : "Save runtime"}</button></div></section></div>`;
  app.insertAdjacentHTML("beforeend", modal);
  bindActions();
}

function formPayload() {
  return { base_url: document.querySelector("#runtime-base")?.value.trim(), api_key: document.querySelector("#runtime-key")?.value || "", model: document.querySelector("#runtime-model")?.value.trim(), api_mode: document.querySelector("#runtime-mode")?.value, reasoning_effort: document.querySelector("#runtime-reasoning")?.value.trim() || "" };
}

async function refreshEvent(eventId = state.selectedEvent) {
  state.selectedEvent = eventId;
  state.eventDetail = await api(`/api/events/${eventId}?tick=${state.tick}`);
  state.timeline = (await api(`/api/timeline?tick=${state.tick}`)).items;
  render();
}

function bindActions() {
  document.querySelectorAll("[data-page]").forEach((button) => button.addEventListener("click", async () => {
    state.page = button.dataset.page;
    state.lifetime = null;
    state.source = null;
    state.drawer = false;
    if (state.page === "branch" && state.branch) await loadBranch();
    render();
  }));
  document.querySelectorAll("[data-event]").forEach((button) => button.addEventListener("click", () => refreshEvent(button.dataset.event)));
  document.querySelectorAll("[data-source]").forEach((button) => button.addEventListener("click", async () => { state.source = await api(`/api/sources/${button.dataset.source}`); state.drawer = true; render(); }));
  document.querySelectorAll("[data-seat]").forEach((button) => button.addEventListener("click", async () => { state.lifetimeSeat = button.dataset.seat; state.lifetime = await api(`/api/lifetimes/${state.lifetimeSeat}`); render(); }));
  document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => handleAction(button.dataset.action)));
}

async function handleAction(action) {
  if (action === "enter") { state.page = "chronicle"; render(); return; }
  if (action === "home") { state.page = "cover"; state.lifetime = null; render(); return; }
  if (action === "settings") { state.settings = true; render(); return; }
  if (action === "close-settings") { state.setup = false; state.settings = false; state.setupMessage = null; render(); return; }
  if (action === "close-drawer") { state.drawer = false; state.source = null; render(); return; }
  if (action === "advance") { if (state.tick < 78) { state.tick += 1; await api("/api/canon/advance", { method: "POST", body: JSON.stringify({ tick: state.tick }) }); await refreshEvent(state.timeline.find((item) => item.tick === state.tick)?.id || state.selectedEvent); } return; }
  if (action === "create-branch") { state.branch = await api("/api/branch", { method: "POST" }); state.page = "branch"; await loadBranch(); render(); return; }
  if (action === "wake") { await api(`/api/lifetimes/${state.lifetimeSeat}/wake`, { method: "POST", body: JSON.stringify({ tick: state.tick, wake_type: "observation", live: false }) }); state.lifetime = await api(`/api/lifetimes/${state.lifetimeSeat}`); render(); return; }
  if (action === "branch-step") { const seat = document.querySelector("#branch-seat")?.value || "A"; const type = document.querySelector("#branch-action")?.value || "WAIT"; const payload = type === "SEND_MESSAGE" ? "The road is closing; confirm your position." : type === "ISSUE_ORDER" ? "Hold the inner road until the next report." : ""; const target = type === "PREPARE_MOVEMENT" ? "capital" : ""; await api(`/api/branch/${state.branch.id}/step?seat=${seat}`, { method: "POST", body: JSON.stringify({ type, target, recipient: type === "SEND_MESSAGE" ? "C" : "", payload, priority: "urgent" }) }); await loadBranch(); render(); return; }
  if (action === "test-setup") { const result = await api("/api/setup/test", { method: "POST", body: JSON.stringify(formPayload()) }); state.setupMessage = { text: result.message, error: !result.ok }; render(); return; }
  if (action === "save-settings") { try { const result = await api("/api/setup/configure", { method: "POST", body: JSON.stringify(formPayload()) }); state.setup = false; state.settings = false; state.setupMessage = { text: result.message, error: false }; state.config = await api("/api/config"); render(); } catch (error) { state.setupMessage = { text: error.message, error: true }; render(); } }
}

async function loadBranch() {
  if (!state.branch?.id) return;
  const loaded = await api(`/api/branch/${state.branch.id}`);
  state.branch = loaded.branch;
  state.branchRecords = loaded.records;
  state.branch.stateRecords = loaded.records;
}

window.addEventListener("keydown", (event) => {
  if (state.page !== "chronicle" || state.drawer || state.setup || state.settings) return;
  if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  const index = state.timeline.findIndex((item) => item.id === state.selectedEvent);
  const next = Math.min(state.timeline.length - 1, Math.max(0, index + (event.key === "ArrowDown" ? 1 : -1)));
  refreshEvent(state.timeline[next].id);
});

loadBase().then(render).catch((error) => { app.innerHTML = `<div class="boot-state"><span class="eyebrow">CHRONICLE / ERROR</span><span class="error-text">${escapeHtml(error.message)}</span></div>`; });
