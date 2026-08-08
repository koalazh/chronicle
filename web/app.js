const app = document.querySelector("#app");

const labels = {
  marker: {
    world: "历史节点",
    fork: "分叉点",
  },
  evidence: {
    corroborated: "多来源印证",
    single_attested: "单一来源",
    disputed: "存在争议",
    approximate: "时间约略化",
  },
  provenance: {
    historical: "史料事实",
    modeled: "研究性建模",
    branch_derived: "推演产生",
  },
  action: {
    WAIT: "等待",
    SEND_MESSAGE: "传递消息",
    ISSUE_ORDER: "发出命令",
    PREPARE_MOVEMENT: "准备移动",
  },
};

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
  lifetimeSummaries: {},
  lifetimeLoading: false,
  branch: null,
  branchRecords: [],
  setupMessage: null,
  formDraft: null,
  notice: null,
};

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
}[char]));

function numberValue(value, fallback = 0) {
  const result = Number(value);
  return Number.isFinite(result) ? result : fallback;
}

function formatCount(value) {
  return String(numberValue(value));
}

function shortDate(value) {
  const text = String(value || "").trim();
  return text.replace(/^崇祯十七年\s*/, "") || text;
}

function dayLabel(tick) {
  return "观测台第 " + (numberValue(tick) + 1) + " 天";
}

function markerLabel(marker, hasFork = false) {
  if (hasFork || marker === "fork") return labels.marker.fork;
  return labels.marker[marker] || "历史节点";
}

function evidenceLabel(value) {
  return labels.evidence[value] || "证据待核";
}

function provenanceLabel(value) {
  return labels.provenance[value] || "来源待核";
}

function actionLabel(value) {
  return labels.action[value] || "行动";
}

function displayResearchText(value) {
  return String(value || "")
    .replace(/\bChronicle Host\b/g, "观测台")
    .replace(/\bSource Pack\b/g, "史料包")
    .replace(/\bCanon wake\b/g, "既定历史观察")
    .replace(/\bsimulation boundary\b/g, "推演边界")
    .replace(/\bmessage delay\b/g, "消息延迟")
    .replace(/\bapproximate\b/g, "时间约略化")
    .replace(/\bauthority\b/g, "人物权限")
    .replace(/\bintention\b/g, "行动")
    .replace(/\bChronicle\b/g, "观测台")
    .replace(/\bRuntime\b/g, "运行时")
    .replace(/\bAgent\b/g, "人物模型")
    .replace(/\bLLM\b/g, "语言模型")
    .replace(/\bHost\b/g, "观测台")
    .replace(/\beffects\b/g, "状态变化")
    .replace(/\btick\b/g, "观测日")
    .replace(/\bCanon\b/g, "既定历史");
}

function displayEventTitle(item) {
  const tags = Array.isArray(item?.tags) ? item.tags : [];
  const isBoundary = tags.includes("boundary") || Array.isArray(item?.world_effects) && item.world_effects.some((effect) => effect.type === "simulation_boundary");
  return isBoundary ? "观测台到达边界" : (item?.title || "未命名节点");
}

function forkTick() {
  const forkEvent = state.timeline.find((item) => item.id === state.scenario?.fork?.event_id);
  return forkEvent ? numberValue(forkEvent.tick) : Number.POSITIVE_INFINITY;
}

function canOpenBranch() {
  return state.tick >= forkTick();
}

function finalTick() {
  return numberValue(state.timeline[state.timeline.length - 1]?.tick, 78);
}

function friendlyError(error, fallback = "操作没有完成，请稍后再试。") {
  const message = String(error?.message || "");
  const mappings = [
    ["tick outside", "这个时间点不在本次观测范围内。"],
    ["cannot move backwards", "历史时间只能向前推进。"],
    ["branch is no longer active", "这次受限推演已经到达边界。"],
    ["branch not found", "没有找到这次受限推演。"],
    ["unknown Seat", "暂时无法找到这位人物。"],
    ["Seat not found", "暂时无法找到这位人物。"],
    ["Base URL and model", "请填写模型连接地址和模型名称。"],
    ["API key is required", "请填写模型连接所需的密钥。"],
    ["An API key is required", "请填写模型连接所需的密钥。"],
    ["Provider returned", "模型服务暂时没有接受连接，请检查设置。"],
    ["Connection failed", "暂时无法连接模型，请检查地址和网络。"],
    ["HTTP ", fallback],
  ];
  const matched = mappings.find(([needle]) => message.includes(needle));
  if (matched) return matched[1];
  if (/^[\u4e00-\u9fff]/.test(message) && !message.includes("HTTP")) return message;
  return fallback;
}

function setupResultText(result) {
  if (result?.ok) return "模型连接成功，可以继续准备人物。";
  return "暂时无法连接模型，请检查地址、密钥和模型名称。";
}

function branchResultText(result) {
  if (result?.status === "accepted") return "这次行动已被接受，受限推演前进了一天。";
  if (result?.status === "rejected") return "这次行动没有被接受，当前人物的权限或行动前提不满足。";
  return "观测台暂时无法处理这次行动。";
}

function setNotice(text, error = false) {
  state.notice = { text, error };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || body.error || "request failed");
  return body;
}

async function loadBase() {
  const [scenario, timeline, config] = await Promise.all([
    api("/api/scenario"),
    api("/api/timeline"),
    api("/api/config"),
  ]);
  state.scenario = scenario;
  state.timeline = timeline.items;
  state.tick = timeline.current_tick;
  state.config = config;
  state.setup = config.setup_required;
  state.selectedEvent = state.timeline.find((item) => item.is_current)?.id || state.timeline[0]?.id;
  if (state.selectedEvent) {
    state.eventDetail = await api("/api/events/" + state.selectedEvent + "?tick=" + state.tick);
  }
}

async function loadLifetimeSummaries() {
  const entries = await Promise.all(state.scenario.actors.map(async (actor) => [
    actor.seat,
    await api("/api/lifetimes/" + actor.seat),
  ]));
  state.lifetimeSummaries = Object.fromEntries(entries);
}

function render() {
  if (!state.scenario) {
    app.innerHTML = '<div class="boot-state"><span class="eyebrow">甲申 · 历史观测台</span><span>正在打开观测台</span></div>';
    return;
  }
  if (state.page === "cover") renderCover();
  else if (state.page === "chronicle") renderChronicle();
  else if (state.page === "lifetimes") renderLifetimes();
  else if (state.page === "branch") renderBranch();
  else renderAbout();
  if (state.drawer) renderDrawer();
  if (state.setup || state.settings) renderSettingsModal();
  if (state.notice) renderNotice();
  bindActions();
}

function renderCover() {
  const setupNote = state.setup
    ? '<p class="cover-note">首次使用需要连接模型，设置会保存在本机服务端。</p>'
    : "";
  app.innerHTML =
    '<main class="cover" data-testid="cover">' +
      '<svg class="cover-map" viewBox="0 0 1000 650" aria-hidden="true">' +
        '<path d="M112 485 C260 400 290 205 482 252 S722 384 882 150" />' +
        '<path d="M154 550 C330 520 438 370 560 335 S780 290 910 232" />' +
        '<path d="M160 420 C330 420 420 110 680 140 S805 205 920 280" />' +
        '<line x1="152" y1="485" x2="872" y2="150" />' +
        '<line x1="470" y1="250" x2="820" y2="500" />' +
        '<circle cx="482" cy="252" r="4" />' +
        '<circle cx="882" cy="150" r="4" />' +
        '<circle cx="820" cy="500" r="4" />' +
      '</svg>' +
      '<div class="cover-content">' +
        '<div class="cover-kicker">甲申 · 历史观测台</div>' +
        '<h1 class="cover-title">甲申</h1>' +
        '<p class="cover-subtitle">最后一个春天，三个人只知道各自收到的消息。</p>' +
        '<p class="cover-copy"><span>看见历史如何发生</span><span>看见消息如何抵达</span><span>进入一次有边界的历史分叉</span></p>' +
        '<button class="cover-enter" data-action="enter">开始观测&nbsp; →</button>' +
        setupNote +
      '</div>' +
      '<div class="cover-meta">崇祯十七年正月初一 — 三月十九 · 1644</div>' +
    '</main>';
}

function renderShell(content, page) {
  const branchAvailable = canOpenBranch() || Boolean(state.branch);
  const branchNav = branchAvailable
    ? '<button data-page="branch" aria-current="' + (page === "branch" ? "page" : "false") + '">受限推演</button>'
    : '<span class="nav-disabled" aria-disabled="true" title="抵达历史分叉点后开放">受限推演</span>';
  app.innerHTML =
    '<header class="topbar">' +
      '<button class="brand" data-action="home" aria-label="返回甲申观测台首页"><span class="brand-mark">甲</span><span class="brand-name">甲申观测台</span></button>' +
      '<nav class="nav" aria-label="主导航">' +
        '<button data-page="chronicle" aria-current="' + (page === "chronicle" ? "page" : "false") + '">观测台</button>' +
        '<button data-page="lifetimes" aria-current="' + (page === "lifetimes" ? "page" : "false") + '">人物经历</button>' +
        branchNav +
        '<button data-page="about" aria-current="' + (page === "about" ? "page" : "false") + '">方法与边界</button>' +
      '</nav>' +
      '<button class="utility-button" data-action="settings" aria-label="打开模型设置">⋯<span>模型设置</span></button>' +
    '</header>' +
    content;
}

function renderChronicle() {
  const event = state.eventDetail?.event || {};
  const assertion = state.eventDetail?.assertions?.[0] || {};
  const whoKnows = state.eventDetail?.who_knows?.[assertion.id] || {};
  const knowledge = state.scenario.actors.map((actor) => {
    const known = Boolean(whoKnows[actor.seat]);
    return '<div class="knowledge-row">' +
      '<div><div class="knowledge-name">' + escapeHtml(actor.display_name) + '</div><div class="knowledge-seat">' + (known ? "已经收到相关消息" : "还没有收到相关消息") + '</div></div>' +
      '<div class="knowledge-status ' + (known ? "new" : "unknown") + '">' + (known ? "已知道" : "尚未知道") + '</div>' +
    '</div>';
  }).join("");
  const timeline = state.timeline.map((item) =>
    '<button class="timeline-item" data-event="' + escapeHtml(item.id) + '" data-marker="' + escapeHtml(item.marker) + '" data-past="' + item.is_past + '" aria-current="' + (item.id === state.selectedEvent ? "true" : "false") + '">' +
      '<span class="timeline-dot"></span>' +
      '<span><span class="timeline-date">' + escapeHtml(shortDate(item.native_date)) + '</span><span class="timeline-title">' + escapeHtml(displayEventTitle(item)) + '</span><span class="timeline-tag">' + escapeHtml(markerLabel(item.marker, item.has_fork)) + '</span></span>' +
    '</button>'
  ).join("");
  const effects = Array.isArray(event.world_effects) ? event.world_effects : [];
  const mapNodes = state.scenario.locations.map((location) => {
    const active = effects.some((effect) => effect.target === location.id);
    return '<g><circle class="map-node ' + (active ? "active" : "") + '" cx="' + location.x + '%" cy="' + location.y + '%" r="1.2"></circle><text class="map-label" x="' + (location.x + 1.4) + '%" y="' + (location.y - 1) + '%">' + escapeHtml(location.display_name) + '</text></g>';
  }).join("");
  const mapLines = state.scenario.routes.map((route) => {
    const from = state.scenario.locations.find((item) => item.id === route.from_location);
    const to = state.scenario.locations.find((item) => item.id === route.to_location);
    return from && to
      ? '<line class="map-route ' + (route.id.includes("capital") ? "canonical" : "") + '" x1="' + from.x + '%" y1="' + from.y + '%" x2="' + to.x + '%" y2="' + to.y + '%"></line>'
      : "";
  }).join("");
  const eventText = displayResearchText(assertion.normalized_evidence || "这条事件记录由史料与观测台的历史规则共同约束。");
  const currentDate = event.native_date || state.scenario.summary.window.start;
  const forkVisible = canOpenBranch() && event.id === state.scenario.fork.event_id;
  const sourceButton = assertion.id
    ? '<button class="text-button" data-source="' + escapeHtml(assertion.id) + '">查看史料依据&nbsp; ↗</button>'
    : "";
  const page = '<main class="page" data-testid="chronicle-page">' +
    '<section class="page-header"><div><div class="page-kicker">观测台 · 既定历史</div><h1 class="page-title">谁已经知道，谁还不知道？</h1></div><p class="page-lede">历史事件已经发生，但消息不会同时抵达每个人。这里展示人物真正收到的消息，以及它们如何影响下一步判断。</p></section>' +
    '<section class="chronicle-layout">' +
      '<aside class="timeline" aria-label="历史时间线"><div class="timeline-heading"><span class="section-label">历史时间线</span><span class="timeline-range">' + state.timeline.length + ' 个节点</span></div>' + timeline + '</aside>' +
      '<section class="observatory">' +
        '<div class="observatory-top"><div><div class="date-display">' + escapeHtml(currentDate) + '</div><div class="tick-display">' + dayLabel(state.tick) + ' · 既定历史</div></div><button class="advance-button" data-action="advance" ' + (state.tick >= finalTick() ? "disabled" : "") + '>推进一天&nbsp; →</button></div>' +
        '<div class="map-frame"><svg class="map-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="甲申路线与消息图">' + mapLines + mapNodes + '<path class="map-route" d="M13 64 C36 50 51 38 70 44 S82 53 91 30" vector-effect="non-scaling-stroke"></path><circle class="map-message" cx="58" cy="43" r="1.2"></circle></svg><div class="map-legend"><span>历史路线</span><span>传递中的消息</span></div></div>' +
        '<div class="current-event"><div class="event-eyebrow"><span>当前节点</span><span>〔' + escapeHtml(evidenceLabel(assertion.evidence_status)) + '〕</span></div><h2 class="event-title">' + escapeHtml(displayEventTitle(event)) + '</h2><p class="event-copy">' + escapeHtml(eventText) + '</p><div class="event-actions">' + sourceButton + (forkVisible ? '<button class="text-button" data-action="create-branch">进入受限推演&nbsp; ↘</button>' : "") + '</div></div>' +
      '</section>' +
      '<aside class="context-panel"><div class="section-label">信息送达</div><h2 class="context-title">谁已经知道</h2><p class="context-copy">世界已经发生，不等于每个人都已经获知。</p><div class="knowledge-list">' + knowledge + '</div><div class="context-note">信息抵达的时间差，就是这次观测的一部分。</div></aside>' +
    '</section>' +
  '</main>';
  renderShell(page, "chronicle");
}

function renderLifetimes() {
  if (!state.lifetime) {
    const entries = state.scenario.actors.map((actor) => {
      const summary = state.lifetimeSummaries[actor.seat];
      const stats = summary?.stats || {};
      const value = state.lifetimeLoading && !summary ? "读取中" : formatCount(stats.observations);
      return '<article class="lifetime-entry">' +
        '<div class="seat-label">人物经历</div>' +
        '<h3>' + escapeHtml(actor.display_name) + '</h3>' +
        '<p>' + escapeHtml(actor.description) + '</p>' +
        '<div class="lifetime-stats"><div class="stat"><strong>' + value + '</strong><span>收到的信息</span></div><div class="stat"><strong>' + (state.lifetimeLoading && !summary ? "读取中" : formatCount(stats.intentions)) + '</strong><span>形成的判断</span></div><div class="stat"><strong>' + (state.lifetimeLoading && !summary ? "读取中" : formatCount(stats.memories)) + '</strong><span>长期记忆</span></div></div>' +
        '<button class="open-lifetime" data-seat="' + escapeHtml(actor.seat) + '">查看经历&nbsp; →</button>' +
      '</article>';
    }).join("");
    renderShell(
      '<main class="page" data-testid="lifetimes-page"><section class="page-header"><div><div class="page-kicker">人物经历</div><h1 class="page-title">他们分别经历了什么？</h1></div><p class="page-lede">人物经历记录一个人真正收到过的信息、形成过的判断，以及后来愿意保留下来的长期记忆。</p></section><section class="lifetimes-grid">' +
      entries +
      '</section></main>',
      "lifetimes"
    );
    return;
  }

  const life = state.lifetime;
  const actor = life.actor || {};
  const records = Array.isArray(life.records) ? life.records : [];
  const memoryVersions = Array.isArray(life.memory?.versions) ? life.memory.versions : [];
  const recordMarkup = records.length
    ? records.map((record) => {
      const isReflection = record.wake_type === "reflection";
      const observationCount = Array.isArray(record.observation_ids) ? record.observation_ids.length : 0;
      const intentionCount = Array.isArray(record.intentions) ? record.intentions.length : 0;
      return '<div class="life-record"><div class="life-record-date">' + escapeHtml(dayLabel(record.tick)) + '</div><div class="life-record-dot ' + (isReflection ? "memory" : "") + '"></div><div><div class="life-record-title">' + (isReflection ? "重新理解了先前的判断" : "记录了 " + observationCount + " 条新信息") + '</div><div class="life-record-meta">' + (intentionCount ? "形成 " + intentionCount + " 个判断" : "这次观察没有形成新的判断") + '</div></div></div>';
    }).join("")
    : '<div class="empty-state">还没有经历记录。推进历史后，可以从这里记录一次人物观察。</div>';
  const memoryText = String(life.memory?.text || "").trim() || "暂未形成长期记忆。需要经过重新理解，经验才可能被保留下来。";
  const seats = state.scenario.actors.map((item) =>
    '<button class="' + (item.seat === state.lifetimeSeat ? "active" : "") + '" data-seat="' + escapeHtml(item.seat) + '">' + escapeHtml(item.display_name) + '</button>'
  ).join("");
  const reflectButton = records.length
    ? '<button class="secondary-button" data-action="reflect">重新理解这段经历</button>'
    : "";
  const page = '<main class="page" data-testid="lifetime-page">' +
    '<section class="page-header"><div><div class="page-kicker">人物经历</div><h1 class="page-title">' + escapeHtml(actor.display_name) + '的经历</h1></div><p class="page-lede">这不是聊天记录，而是一条由观察、判断、现实反馈与长期记忆组成的经历线。</p></section>' +
    '<section class="lifetime-detail"><aside class="lifetime-rail"><div class="section-label">选择人物</div><div class="seat-switcher">' + seats + '</div><div class="context-note">只展示观测台能够追溯的经历；人物没有收到的信息不会进入这里。</div></aside>' +
      '<section class="life-content"><div class="life-intro"><div><h2>' + dayLabel(state.tick) + '</h2><p>' + formatCount(life.stats?.observations) + ' 条信息 · ' + formatCount(life.stats?.intentions) + ' 个判断 · ' + formatCount(life.stats?.memories) + ' 条长期记忆</p></div><div class="life-actions"><button class="primary-button" data-action="wake">记录一次观察</button>' + reflectButton + '</div></div>' +
        '<div class="life-line"><div class="section-label">经历记录</div><div class="life-line-track"><span class="life-marker" style="left:8%" data-label="观察"></span><span class="life-marker contradiction" style="left:55%" data-label="现实反馈"></span><span class="life-marker memory" style="left:82%" data-label="长期记忆"></span></div>' + recordMarkup + '</div>' +
        '<div class="memory-lineage"><div class="section-label">长期记忆</div><h3>' + (memoryVersions.length ? "已经形成可携带的经验" : "暂未形成长期记忆") + '</h3><p>' + escapeHtml(memoryText) + '</p><div class="lineage-flow"><span>收到信息</span><span>形成判断</span><span>现实反馈</span><span>重新理解</span><span>长期记忆</span></div></div>' +
      '</section>' +
    '</section>' +
  '</main>';
  renderShell(page, "lifetimes");
}

function renderBranch() {
  const branch = state.branch;
  const fork = state.scenario.fork || {};
  const forkEvent = state.timeline.find((item) => item.id === fork.event_id);
  if (!branch) {
    const unavailable = !canOpenBranch()
      ? '<div class="branch-unavailable"><strong>尚未到达这个时间点</strong><span>分叉点位于 ' + escapeHtml(shortDate(forkEvent?.native_date || "")) + '。推进观测台到这里后，才可以进入受限推演。</span></div>'
      : '<div class="branch-actions"><button class="primary-button" data-action="create-branch">进入受限推演&nbsp; ↘</button></div>';
    renderShell(
      '<main class="page" data-testid="branch-page"><section class="page-header"><div><div class="page-kicker">受限推演</div><h1 class="page-title">如果这项提议被接受？</h1></div><p class="page-lede">这不是改变历史的按钮，而是从一个真实出现过的历史节点出发，沿着观测台能够支撑的规则前进。</p></section><section class="branch-hero"><div><div class="section-label">历史分叉点</div><h2>' + escapeHtml(fork.display_name || "一次历史提议") + '</h2><p>这项提议在既定历史中没有被采纳。到达对应时间点后，观测台允许只进行一次、最多十四天的受限推演。</p>' + unavailable + '</div><div class="branch-premise"><strong>这次推演的边界</strong><span>最多前进十四天。行动必须符合人物权限和已定义的历史规则。不会由模型续写未被约束的历史。</span></div></section></main>',
      "branch"
    );
    return;
  }

  const stateView = branch.state_json || {};
  const boundary = branch.status === "boundary";
  const records = state.branchRecords || [];
  const recordText = records.length
    ? records.slice(-3).map((record) => '<div class="branch-state-row"><strong>' + escapeHtml(dayLabel(record.tick)) + '</strong><span>' + branchResultText(record.result_json || {}) + '</span></div>').join("")
    : '<div class="empty-state">还没有提交推演行动。</div>';
  const branchActionOptions = ["WAIT", "SEND_MESSAGE", "ISSUE_ORDER", "PREPARE_MOVEMENT"]
    .map((type) => '<option value="' + type + '">' + escapeHtml(actionLabel(type)) + '</option>')
    .join("");
  const controls = boundary
    ? '<div class="boundary"><h2>推演在这里停止。</h2><p>当前状态仍然可以追溯；继续前进将需要未经支持的历史假设。</p><ul><li>不由模型自动补写历史事件</li><li>保留当前人物与世界状态</li><li>到达十四天边界后结束</li></ul></div>'
    : '<div class="branch-controls"><label for="branch-seat">人物</label><select id="branch-seat"><option value="A">崇祯</option><option value="B">李自成</option><option value="C">吴三桂</option></select><label for="branch-action">下一步</label><select id="branch-action">' + branchActionOptions + '</select><button class="primary-button" data-action="branch-step">提交这一步&nbsp; →</button></div>';
  renderShell(
    '<main class="page" data-testid="branch-page"><section class="page-header"><div><div class="page-kicker">受限推演</div><h1 class="page-title">既定历史与另一种可能</h1></div><p class="page-lede">推演只保留与历史节点有关的差异。每一步都由观测台验证，直到模型边界出现。</p></section><section class="branch-board"><div class="branch-columns"><div class="branch-column"><h3>既定历史 <span>已发生</span></h3><div class="branch-state-row"><strong>历史选择</strong><span>这项提议没有被采纳</span></div><div class="branch-state-row"><strong>世界状态</strong><span>观测台继续推进既定历史事件</span></div><div class="branch-state-row"><strong>停止时间</strong><span>崇祯十七年三月十九日</span></div></div><div class="branch-column"><h3>受限推演 <span>另一种可能</span></h3><div class="branch-state-row"><strong>起点</strong><span>' + escapeHtml(fork.display_name || "历史提议") + ' 已被接受</span></div><div class="branch-state-row"><strong>当前进度</strong><span>第 ' + formatCount(stateView.day_offset) + ' / 14 天</span></div><div class="branch-state-row"><strong>传递中的消息</strong><span>' + formatCount((stateView.messages || []).length) + ' 条</span></div>' + recordText + '</div></div>' + controls + '</section></main>',
    "branch"
  );
}

function renderAbout() {
  renderShell(
    '<main class="page" data-testid="about-page"><section class="page-header"><div><div class="page-kicker">方法与边界</div><h1 class="page-title">让历史保持它的边界。</h1></div><p class="page-lede">甲申观测台不替历史补写一个漂亮的结局。它观察有限信息如何进入人物经历，并在必要时停止。</p></section><section class="about-grid"><div class="formula">事实 <span>≠</span> 所知 <span>≠</span> 所信</div><article class="about-block"><h2>既定历史</h2><p>时间、史料事实、消息送达和世界状态由观测台统一维护。人物可以理解自己看到的世界，但不能直接改写已经发生的历史。</p></article><article class="about-block"><h2>历史盲点</h2><p>每个人只接收已经送达给自己的信息。后来我们知道的结局，不会被倒灌进人物当时的判断。</p></article><article class="about-block"><h2>人物经历不是聊天记录</h2><p>经历记录保留人物真正观察过什么、形成过什么判断。长期记忆只保留人物愿意带进下一次观察的有限经验。</p></article><article class="about-block"><h2>为什么停止</h2><p>当下一步需要猜测未经约束的战争、联盟或长期命运，观测台会停止。诚实的边界比流畅的虚构更重要。</p></article><article class="about-block"><h2>受限推演是什么</h2><p>受限推演不是预测，也不是自由改史。当前版本只从一个有史料出处的历史提议出发，最多前进十四天。</p></article><article class="about-block"><h2>模型连接</h2><p>人物模型可以帮助整理观察和判断，但它不拥有时间线、史料或世界状态。模型连接的实际来源与能力，以模型设置和技术详情中的验证结果为准。</p></article></section><details class="technical-details about-technical"><summary>查看技术说明</summary><p>Chronicle、Hermes、Source Pack 和 Memory 是本项目使用的技术组件名称。它们用于支撑观测、人物经历和审计流程，不是普通用户需要先理解的产品概念。</p></details></main>',
    "about"
  );
}

function renderDrawer() {
  const assertion = state.source?.assertion || {};
  const sources = state.source?.sources || [];
  const citations = sources.length
    ? sources.map((source) => {
      const link = source.url
        ? '<a href="' + escapeHtml(source.url) + '" target="_blank" rel="noreferrer">打开出处 ↗</a>'
        : '<span class="muted">暂无在线链接</span>';
      return '<div class="citation"><strong>' + escapeHtml(source.work || "未标注出处") + '</strong><span>' + escapeHtml(source.locator || "出处位置未标注") + '</span>' + link + '</div>';
    }).join("")
    : '<div class="empty-state">暂未关联可打开的出处。</div>';
  const technical = assertion.id
    ? '<details class="technical-details"><summary>查看技术详情</summary><p>断言编号：' + escapeHtml(assertion.id) + '<br />内容来源：' + escapeHtml(assertion.provenance || "未标注") + '</p></details>'
    : "";
  const drawer =
    '<div class="drawer-scrim open" data-action="close-drawer"></div>' +
    '<aside class="source-drawer open" aria-label="史料依据"><button class="drawer-close" data-action="close-drawer" aria-label="关闭史料依据">×</button><div class="drawer-kicker">史料依据</div><h2 class="drawer-title">' + escapeHtml(displayResearchText(assertion.claim || "历史断言")) + '</h2><span class="drawer-status">' + escapeHtml(evidenceLabel(assertion.evidence_status)) + '</span><div class="drawer-section"><h3>研究说明</h3><p>' + escapeHtml(displayResearchText(assertion.normalized_evidence || "暂时没有可展示的研究说明。")) + '</p></div><div class="drawer-section"><h3>主要出处</h3>' + citations + '</div><div class="drawer-section"><h3>内容来源</h3><p>' + escapeHtml(provenanceLabel(assertion.provenance)) + '</p></div>' + technical + '</aside>';
  app.insertAdjacentHTML("beforeend", drawer);
}

function renderSettingsModal() {
  const config = state.config || {};
  const draft = state.formDraft || {};
  const firstRun = state.setup;
  const baseUrl = draft.base_url ?? config.base_url ?? "";
  const model = draft.model ?? config.model ?? "";
  const apiMode = draft.api_mode ?? config.api_mode;
  const reasoningEffort = draft.reasoning_effort ?? config.reasoning_effort ?? "";
  const message = state.setupMessage
    ? '<div class="setup-result ' + (state.setupMessage.error ? "error" : "") + '" role="status">' + escapeHtml(state.setupMessage.text) + '</div>'
    : "";
  const steps = firstRun
    ? '<ol class="setup-steps"><li class="active"><strong>连接模型</strong><span>填写一次模型连接信息</span></li><li><strong>准备人物</strong><span>由观测台创建人物经历</span></li><li><strong>开始观测</strong><span>进入甲申的历史时间线</span></li></ol>'
    : "";
  const modal =
    '<div class="modal-scrim"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="settings-title"><button class="modal-close" data-action="close-settings" aria-label="关闭模型设置">×</button><div class="page-kicker">' + (firstRun ? "开始前的准备" : "模型连接") + '</div><h2 id="settings-title">' + (firstRun ? "连接模型" : "模型设置") + '</h2><p>' + (firstRun ? "连接完成后，观测台会准备三位人物的经历记录。密钥只由本机服务端保存。" : "修改模型设置会影响之后新增的人物经历记录。已经保存的历史记录不会被覆盖。") + '</p>' + steps +
    '<div class="form-field"><label for="runtime-base">模型连接地址</label><input id="runtime-base" value="' + escapeHtml(baseUrl) + '" placeholder="https://provider.example/v1" autocomplete="off" /></div>' +
    '<div class="form-field"><label for="runtime-key">模型密钥</label><input id="runtime-key" type="password" placeholder="' + (config.api_key ? "保留当前密钥" : "请输入模型密钥") + '" autocomplete="new-password" /><div class="form-help">密钥不会回填到页面，只会写入本机服务端。</div></div>' +
    '<div class="form-field"><label for="runtime-model">模型名称</label><input id="runtime-model" value="' + escapeHtml(model) + '" placeholder="请输入模型名称" autocomplete="off" /></div>' +
    '<div class="form-field"><label for="runtime-mode">接口类型</label><select id="runtime-mode"><option value="chat_completions" ' + (apiMode === "chat_completions" ? "selected" : "") + '>对话接口</option><option value="responses" ' + (apiMode === "responses" ? "selected" : "") + '>响应接口</option></select></div>' +
    '<div class="form-field"><label for="runtime-reasoning">推理强度 <span class="muted">可选</span></label><input id="runtime-reasoning" value="' + escapeHtml(reasoningEffort) + '" placeholder="留空使用模型默认设置" autocomplete="off" /></div>' +
    message +
    '<div class="modal-actions"><button class="secondary-button" data-action="test-setup">测试连接</button><button class="primary-button" data-action="save-settings">' + (firstRun ? "保存并准备人物" : "保存设置") + '</button></div></section></div>';
  app.insertAdjacentHTML("beforeend", modal);
}

function renderNotice() {
  const notice = state.notice;
  app.insertAdjacentHTML(
    "beforeend",
    '<div class="notice ' + (notice.error ? "error" : "") + '" role="alert"><span>' + escapeHtml(notice.text) + '</span><button data-action="clear-notice" aria-label="关闭提示">知道了</button></div>'
  );
}

function formPayload() {
  return {
    base_url: document.querySelector("#runtime-base")?.value.trim(),
    api_key: document.querySelector("#runtime-key")?.value || "",
    model: document.querySelector("#runtime-model")?.value.trim(),
    api_mode: document.querySelector("#runtime-mode")?.value,
    reasoning_effort: document.querySelector("#runtime-reasoning")?.value.trim() || "",
  };
}

async function refreshEvent(eventId = state.selectedEvent) {
  state.selectedEvent = eventId;
  state.eventDetail = await api("/api/events/" + eventId + "?tick=" + state.tick);
  state.timeline = (await api("/api/timeline?tick=" + state.tick)).items;
  render();
}

async function openPage(page) {
  state.page = page;
  state.lifetime = null;
  state.source = null;
  state.drawer = false;
  if (page === "lifetimes") {
    state.lifetimeLoading = true;
    render();
    try {
      await loadLifetimeSummaries();
    } catch (error) {
      setNotice(friendlyError(error, "人物经历暂时无法读取。"), true);
    } finally {
      state.lifetimeLoading = false;
      render();
    }
    return;
  }
  if (page === "branch" && state.branch) {
    try {
      await loadBranch();
    } catch (error) {
      setNotice(friendlyError(error, "受限推演暂时无法读取。"), true);
    }
  }
  render();
}

function bindActions() {
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.addEventListener("click", () => openPage(button.dataset.page));
  });
  document.querySelectorAll("[data-event]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await refreshEvent(button.dataset.event);
      } catch (error) {
        setNotice(friendlyError(error, "这个历史节点暂时无法读取。"), true);
        render();
      }
    });
  });
  document.querySelectorAll("[data-source]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        state.source = await api("/api/sources/" + button.dataset.source);
        state.drawer = true;
        render();
      } catch (error) {
        setNotice(friendlyError(error, "史料依据暂时无法读取。"), true);
        render();
      }
    });
  });
  document.querySelectorAll("[data-seat]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.lifetimeSeat = button.dataset.seat;
      try {
        state.lifetime = await api("/api/lifetimes/" + state.lifetimeSeat);
      } catch (error) {
        setNotice(friendlyError(error, "这位人物的经历暂时无法读取。"), true);
      }
      render();
    });
  });
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => handleAction(button.dataset.action));
  });
  document.querySelectorAll(".modal-scrim").forEach((scrim) => {
    scrim.addEventListener("click", (event) => {
      if (event.target === scrim) handleAction("close-settings");
    });
  });
}

async function handleAction(action) {
  if (action === "enter") {
    state.page = "chronicle";
    render();
    return;
  }
  if (action === "home") {
    state.page = "cover";
    state.lifetime = null;
    render();
    return;
  }
  if (action === "settings") {
    state.settings = true;
    state.setupMessage = null;
    state.formDraft = null;
    render();
    return;
  }
  if (action === "close-settings") {
    state.setup = false;
    state.settings = false;
    state.setupMessage = null;
    state.formDraft = null;
    render();
    return;
  }
  if (action === "close-drawer") {
    state.drawer = false;
    state.source = null;
    render();
    return;
  }
  if (action === "clear-notice") {
    state.notice = null;
    render();
    return;
  }

  try {
    if (action === "advance") {
      if (state.tick >= finalTick()) {
        setNotice("已经到达本次历史观测的最后一天。");
        render();
        return;
      }
      const nextTick = state.tick + 1;
      await api("/api/canon/advance", {
        method: "POST",
        body: JSON.stringify({ tick: nextTick }),
      });
      state.tick = nextTick;
      setNotice("历史已推进一天。");
      await refreshEvent(state.timeline.find((item) => item.tick === state.tick)?.id || state.selectedEvent);
      return;
    }
    if (action === "create-branch") {
      if (!canOpenBranch()) {
        setNotice("推进观测台到历史分叉点后，才可以进入受限推演。", true);
        render();
        return;
      }
      state.branch = await api("/api/branch", { method: "POST" });
      state.page = "branch";
      await loadBranch();
      setNotice("受限推演已建立。");
      render();
      return;
    }
    if (action === "wake") {
      const result = await api("/api/lifetimes/" + state.lifetimeSeat + "/wake", {
        method: "POST",
        body: JSON.stringify({ tick: state.tick, wake_type: "observation", live: false }),
      });
      state.lifetime = await api("/api/lifetimes/" + state.lifetimeSeat);
      setNotice(result.source === "hermes"
        ? "这次观察已记录，并收到 Hermes 的返回结果。"
        : "这次观察已记录。当前记录来自观测台的确定性流程，未声称完成真实模型调用。");
      render();
      return;
    }
    if (action === "reflect") {
      const result = await api("/api/lifetimes/" + state.lifetimeSeat + "/reflect", {
        method: "POST",
        body: JSON.stringify({ tick: state.tick, live: false }),
      });
      state.lifetime = await api("/api/lifetimes/" + state.lifetimeSeat);
      setNotice(result.source === "hermes"
        ? "这段经历已重新理解，并收到 Hermes 的返回结果。"
        : "这段经历已重新理解。当前记录来自观测台的确定性流程，未声称完成真实模型调用。");
      render();
      return;
    }
    if (action === "branch-step") {
      const seat = document.querySelector("#branch-seat")?.value || "A";
      const type = document.querySelector("#branch-action")?.value || "WAIT";
      const payload = type === "SEND_MESSAGE"
        ? "The road is closing; confirm your position."
        : type === "ISSUE_ORDER"
          ? "Hold the inner road until the next report."
          : "";
      const target = type === "PREPARE_MOVEMENT" ? "capital" : "";
      const result = await api("/api/branch/" + state.branch.id + "/step?seat=" + seat, {
        method: "POST",
        body: JSON.stringify({
          type,
          target,
          recipient: type === "SEND_MESSAGE" ? "C" : "",
          payload,
          priority: "urgent",
        }),
      });
      await loadBranch();
      setNotice(branchResultText(result.result || {}), result.result?.status === "rejected");
      render();
      return;
    }
    if (action === "test-setup") {
      const payload = formPayload();
      state.formDraft = payload;
      const result = await api("/api/setup/test", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      state.setupMessage = { text: setupResultText(result), error: !result.ok };
      render();
      return;
    }
    if (action === "save-settings") {
      const firstRun = state.setup;
      const payload = formPayload();
      state.formDraft = payload;
      try {
        await api("/api/setup/configure", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (firstRun) {
          state.setupMessage = { text: "模型连接已保存，正在准备人物……", error: false };
          render();
          await api("/api/bootstrap", { method: "POST" });
          state.setup = false;
          state.settings = false;
          state.formDraft = null;
          state.config = await api("/api/config");
          state.page = "chronicle";
          setNotice("人物已准备好，可以开始观测。");
        } else {
          state.settings = false;
          state.formDraft = null;
          state.config = await api("/api/config");
          setNotice("模型设置已保存。");
        }
      } catch (error) {
        state.setupMessage = { text: friendlyError(error, "设置没有保存，请检查模型连接信息。"), error: true };
      }
      render();
    }
  } catch (error) {
    setNotice(friendlyError(error), true);
    render();
  }
}

async function loadBranch() {
  if (!state.branch?.id) return;
  const loaded = await api("/api/branch/" + state.branch.id);
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
  if (state.timeline[next]) {
    refreshEvent(state.timeline[next].id).catch((error) => {
      setNotice(friendlyError(error, "这个历史节点暂时无法读取。"), true);
      render();
    });
  }
});

loadBase().then(render).catch((error) => {
  app.innerHTML = '<div class="boot-state"><span class="eyebrow">甲申 · 历史观测台</span><span class="error-text">观测台暂时无法打开，请检查本地服务。</span></div>';
  console.error(error);
});
