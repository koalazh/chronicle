const app = document.querySelector("#app");

const labels = {
  marker: { world: "历史节点", fork: "进入时刻" },
  evidence: {
    corroborated: "多来源印证",
    single_attested: "单一来源",
    disputed: "存在争议",
    approximate: "时间约略化",
  },
  status: {
    ACCEPTED: "已记录",
    IMPOSSIBLE: "当前无法执行",
    UNSUPPORTED: "当前经历未开放",
    AMBIGUOUS: "需要说得更明确",
  },
  event: {
    CONTEXT_FROZEN: "视野已冻结",
    USER_INPUT: "输入已保存",
    INTENT_ACCEPTED: "意图已记录",
    INTENT_REJECTED: "意图被拒绝",
    INTENT_AWAITING_CONFIRMATION: "等待确认",
    INTENT_CONFIRMED: "已确认动作",
    INTENT_CANCELLED: "已取消动作",
    INPUT_REQUIRES_CLARIFICATION: "需要拆开动作",
    INQUIRY_ANSWERED: "查询已回答",
    AGENT_WAKE: "人物模型收到信息",
    AGENT_INTENT_ACCEPTED: "其他位置已行动",
    AGENT_INTENT_REJECTED: "其他位置行动被拒绝",
    AGENT_RESPONSE_REJECTED: "人物响应被拦截",
    MESSAGE_DISPATCHED: "消息发出",
    MESSAGE_DELIVERED: "消息抵达",
    ORDER_ISSUED: "命令记录",
    AUTHORITY_APPOINTED: "权限任命",
    MOVEMENT_PREPARED: "移动准备",
    PRINCIPAL_MOVED: "主位移动",
    FORCE_REDEPLOYED: "力量重新部署",
    DISCLOSURE_SET: "公开范围改变",
    WAIT_COMMITTED: "等待",
  },
};

const channelLabels = {
  "court-record": "朝廷记录",
  "road-report": "道路报告",
  "border-report": "边地报告",
  "command-camp": "军中记录",
  courier: "驿递",
  "frontier-memorial": "边镇奏报",
  "court-order": "朝廷命令",
  "border-rumor": "边地传闻",
  "emergency-courier": "紧急递报",
  intercepted_letter: "截获檄文",
  "intercepted-rumor": "截获传闻",
  "treasury-report": "库务报告",
  "inner-court": "内廷消息",
  "border-command": "关宁军令",
  "court-report": "朝廷报告",
  "road-rumor": "道路传闻",
  "wall-report": "城墙报告",
  "branch-message": "分支传信",
};

const reliabilityLabels = {
  "direct court calendar": "朝廷日历直录",
  fragmentary: "碎片记录",
  delayed: "延迟抵达",
  "internal order": "内部命令",
  "hostile-side report": "对立方报告",
  incomplete: "信息不完整",
  direct: "直接记录",
  official: "正式记录",
  urgent: "紧急报告",
  administrative: "行政记录",
  "second-hand": "转述消息",
  partial: "部分记录",
  weak: "可信度较低",
  "corroborating fragments": "互相印证的片段",
  "delayed official": "延迟的正式记录",
  late: "较晚转来",
  "late relay": "延迟转递",
  "urgent but compressed": "紧急但经过压缩",
  "official compilation": "正式汇编",
  "direct after delay": "延迟后的直接报告",
  relayed: "转递消息",
  compiled: "汇编记录",
  "hostile text": "对立方文字",
  "authored locally": "当地撰写",
  "direct political report": "直接政治报告",
  "delayed political report": "延迟的政治报告",
  "urgent but incomplete": "紧急但不完整",
  "official but delayed": "延迟的正式报告",
  "official synthesis": "正式综合判断",
  "multiple relays": "多次转递",
  "immediate but local": "即时但仅限局部",
  "direct outcome": "直接结果",
  "terminal relay": "终局转递",
  "last relay": "最后一次转递",
  "your Seat's committed message": "分支消息",
};

const observationCopies = {
  "o001-a": "新季在异样的天色中开启，京师记下一个不安的开端。",
  "o001-b": "东面传来秩序紊乱与时令不安的消息，完整情形尚未抵达。",
  "o001-c": "这个时节以远方的警讯开场，报告没有指出单一原因。",
  "o002-b": "新的公开名号与历法正在整合西部军令，这次行动将被视为一场战事。",
  "o002-a": "西部军队已形成更一致的公开秩序，但规模仍无法确认。",
  "o003-a": "西部道路上有数处据点不再按预期回报，各份报告还没有对上时序。",
  "o003-b": "东面道路仍足以支持继续推进，各地抵抗程度不一。",
  "o004-a": "一支援军已正式向西部道路出发，出发本身已经进入公开记录。",
  "o004-b": "一支朝廷军队已经离开京师道路，但粮秣与行进速度不明。",
  "o005-a": "援军比京师预期走得更慢，部队已经分散，各处关口也没有全部放行。",
  "o005-c": "西部援军在抵达受威胁道路前，可能正在失去协同。",
  "o006-a": "不止一处西部据点报告失守，消息对发生顺序与规模说法不一。",
  "o006-b": "西部军令已经越过又一道破口，可以继续推进，但身后道路并不稳固。",
  "o007-a": "太原已不再作为稳定防线回应，最后一份报告也不完整。",
  "o007-b": "太原已停止有组织抵抗，西部道路正向北方打开。",
  "o007-c": "一处重要北方据点已经失守，消息经过数次转递才抵达东部关口。",
  "o008-a": "北方威胁距京师比先前报告所说更近，具体位置仍无法确认。",
  "o009-a": "朝廷收到同一道路的两份报告，暂时无法拼成一个相互一致的说法。",
  "o009-b": "军中判断道路仍足以继续推进，但不知道京师已经听到了什么。",
  "o010-b": "宁武抵抗得比预期更久，西部军令必须在施压与时间之间取舍。",
  "o010-a": "宁武已成为眼下北方的迟滞点，防守激烈但并不稳固。",
  "o011-a": "宁武已经失守，报告没有给出剩余守军的可靠估计。",
  "o011-b": "宁武的迟滞结束，军队可以重新移动，但疲惫正在累积。",
  "o011-c": "一处山口经过集中交战后被攻取，东部关口还不知道下一个目标。",
  "o012-a": "下一个北方据点不再被视为可靠屏障，早先的把握正在被修正。",
  "o013-a": "截获的檄文指责朝廷闭塞、私享特权、民户困敝；它是一种立场论辩，并非中性报告。",
  "o013-b": "这份檄文试图把地方不满变成开关理由，其中的说法有用，但带有明显立场。",
  "o014-a": "大同正承受压力，守军是否继续坚守不能脱离当地情势判断。",
  "o014-b": "大同正在准备迎接推进中的军队，抵抗不会整齐一致。",
  "o015-a": "大同已不再是稳定的防守节点，报告来迟，也省略了完整经过。",
  "o015-c": "另一处北方守军已经失守，东部军令必须在不完整的地图上作出决定。",
  "o016-a": "京师关门与夜间行动受到更严限制，信息进出会变慢。",
  "o016-b": "京师正在收紧道路，军中无法判断这是准备还是恐慌。",
  "o017-a": "朝廷已经发出勤王召集令，但命令没有同时创造道路、粮秣或时间。",
  "o017-c": "东部军令被要求向京师移动，但这和当地防守需要发生冲突。",
  "o018-a": "勤王命令没有统一的粮秣估算，京师看不见每支部队真正的准备程度。",
  "o019-a": "内廷有人提议让太子南下建立第二个军政中心，但提议仍有争议，尚未成为命令。",
  "o019-b": "朝廷可能正在考虑南方军政线，西部军中不知道这是事实还是策略。",
  "o019-c": "京师已经议论过建立南方军政中心，但没有看到被接受的移动命令。",
  "o020-a": "南迁提议没有被接受，朝廷公开立场仍是留在京师。",
  "o020-b": "京师选择留下，西部军中不知道这是出于信心还是迫于形势。",
  "o021-a": "朝廷现在把北方通道视为决定性防线，其他移动不再是生效命令。",
  "o022-a": "宣府已经成为迫在眉睫的问题，报告无法可靠估计关口还能守多久。",
  "o022-b": "宣府已成为通往京师道路上的下一个实际关口。",
  "o023-a": "宣府守军已无法继续提供稳定屏障，投降与抵抗的说法互相冲突。",
  "o023-c": "一处北方屏障已经破裂，东部关口预计威胁将转向内侧关隘。",
  "o024-a": "从宣府通往内侧关隘的道路已没有可靠守军作为缓冲。",
  "o025-c": "东部边镇仍在自己的防守位置，京师的危急已被知晓，但并不在眼前。",
  "o025-a": "东部将领仍在内侧道路之外，朝廷已经请求答复。",
  "o026-c": "东部军令必须在向京师移动与打开自身关口的风险之间权衡，没有无代价的选项。",
  "o026-a": "朝廷正在讨论东部关宁军是否进入内侧道路，命令尚未定案。",
  "o027-a": "居庸关已成为决定性北方门槛，递报无法说明还有多少有组织的防守。",
  "o027-b": "居庸关是京师之前的下一道障碍，地形有利于拖延，却不保证结果。",
  "o028-a": "居庸关正在承受直接压力，京师还有发令时间，却不能假定命令一定送达。",
  "o028-b": "关口正在被试探，西部军中还没有看见京师内城。",
  "o029-a": "昌平已经失守，通向京师的剩余道路暴露出来。",
  "o029-c": "北方内城已经失守，任何向京师移动都在和正在关闭的道路赛跑。",
  "o030-a": "北方关口不再提供可靠的拖延，京师防守已从区域防线退为城内防守。",
  "o031-a": "来自北方道路的报告已经对移动方向达成一致，外层缓冲不再安全。",
  "o031-b": "军队正穿过一连串失守的关口逼近京师，下一项决定将直接面对城池。",
  "o031-c": "东部将领收到确认：北方道路已经崩解。",
  "o032-a": "外层防线已无法争取时间，命令现在转向城墙与城内民众。",
  "o033-a": "京师仍在持续发出命令，但命令能否越过城墙已不再确定。",
  "o033-c": "京师仍在发声，但消息要过了决定性时刻才抵达东部关口。",
  "o034-a": "京师内层防守正在失效，报告没有说明城墙之外发生了什么。",
  "o034-b": "军队已经抵达城门之前，军中只能看见城门、烟尘与人流，看不见每一条内街。",
  "o035-b": "京师已经失守，甲申观测窗口在此结束；后续政治命令不在本次记录之内。",
  "o035-c": "最后一次转递称京师已经失守，东部关口没有城内的直接视野。",
};

const state = {
  phase: "BOOT",
  view: "observe",
  scenario: null,
  timeline: [],
  tick: 0,
  selectedEvent: null,
  eventDetail: null,
  source: null,
  drawer: false,
  config: null,
  active: null,
  debrief: null,
  sealed: [],
  lifetime: null,
  lifetimeSeat: "A",
  lifetimeWorldlineId: null,
  interaction: null,
  inputDraft: "",
  settings: false,
  settingsMessage: null,
  notice: null,
  pendingAction: "",
  eventRequest: 0,
  branchLifetimes: [],
  ledger: null,
  lastMoment: null,
  requestControllers: {},
  modalReturnFocus: null,
};

const REQUEST_TIMEOUT_MS = 15000;

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

function shortDate(value) {
  const text = String(value || "").trim();
  return text.replace(/^崇祯十七年\s*/, "") || text;
}

function dayLabel(tick) {
  return `观测台第 ${numberValue(tick) + 1} 天`;
}

function evidenceLabel(value) {
  return labels.evidence[value] || "证据待核";
}

function statusLabel(value) {
  return labels.status[value] || value || "等待判断";
}

function actionLabel(value) {
  return {
    SEND_MESSAGE: "传递消息",
    ISSUE_ORDER: "下达命令",
    REQUEST_INFORMATION: "请求信息",
    APPOINT_AUTHORITY: "任命权限",
    PREPARE_MOVEMENT: "准备移动",
    MOVE_PRINCIPAL: "移动主位",
    REDEPLOY_FORCE: "重新部署力量",
    SET_DISCLOSURE: "设置公开范围",
    HOLD_POSITION: "保持位置",
    WAIT: "等待",
  }[value] || "一项行动";
}

function channelLabel(value) {
  return channelLabels[value] || "消息";
}

function reliabilityLabel(value) {
  return reliabilityLabels[value] || "来源未标记";
}

function observationPayload(item) {
  const observationId = String(item?.observation_id || "");
  if (observationId && observationCopies[observationId]) return observationCopies[observationId];
  const payload = String(item?.payload || "").trim();
  if (!payload) return "（没有可读内容）";
  return /[A-Za-z]{4,}/.test(payload) ? "这条报告已经抵达，但暂无中文抄本。" : payload;
}

function localizedRuntimeText(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const reached = state.active?.context?.what_reached_you || [];
  const matching = reached.find((item) => {
    const payload = String(item?.payload || "").trim();
    return payload && (text === payload || text.includes(payload));
  });
  if (matching) return text.replace(String(matching.payload), observationPayload(matching));
  if (/[一-鿿]/.test(text) || !/[A-Za-z]{4,}/.test(text)) return text;
  return "这段人物模型说明暂无中文显示稿。";
}

function runtimeStatusLabel(value) {
  return {
    READY: "已就绪",
    NOT_READY: "未就绪",
    SETUP_REQUIRED: "需要设置",
    UNKNOWN: "状态未知",
  }[value] || "状态未知";
}

function runtimeModeLabel(value) {
  return value === "live" ? "实时人物模型" : "确定性演示";
}

function sealReasonLabel(value) {
  return {
    user_exit: "用户主动退出",
    horizon_reached: "到达经历边界",
    simulation_boundary: "到达观测台边界",
  }[value] || value || "已封存";
}

function capitalStatusLabel(value) {
  return {
    standing: "仍在维持",
    strained: "局势紧绷",
    threatened: "受到威胁",
    collapsed: "秩序崩解",
  }[value] || value || "尚未改变";
}

function beliefLabel(value) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "已形成判断";
  const direction = { up: "增强", down: "减弱", unchanged: "暂未改变" }[value.direction] || "已形成判断";
  return value.statement ? `${value.statement}（${direction}）` : direction;
}

function displayEventTitle(item) {
  const tags = Array.isArray(item?.tags) ? item.tags : [];
  return tags.includes("boundary") ? "观测台到达边界" : (item?.title || "未命名节点");
}

function displayResearchText(value) {
  return String(value || "")
    .replace(/\bChronicle Host\b/g, "观测台")
    .replace(/\bSource Pack\b/g, "史料包")
    .replace(/\bsimulation boundary\b/g, "推演边界")
    .replace(/\bmessage delay\b/g, "消息延迟")
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

function setNotice(text, error = false) {
  state.notice = { text, error };
}

function friendlyError(error, fallback = "操作没有完成，请稍后再试。") {
  const message = String(error?.message || "");
  const mappings = [
    ["REQUEST_TIMEOUT", "请求超过 15 秒仍未完成；请检查本机服务后重试。"],
    ["Archivist view is locked", "一条人物经历正在进行中；请先退出当前经历。"],
    ["active human Worldline", "已经有一条人物经历正在进行中。"],
    ["Entry is not available", "先把观测台读取到这个历史时刻，才能进入。"],
    ["Entry does not expose", "这个历史位置暂未开放。"],
    ["Worldline is sealed", "这条人物经历已经封存，不能继续写入。"],
    ["no pending confirmation", "当前没有等待确认的动作。"],
    ["confirmation id", "确认信息已经失效，请重新提交动作。"],
    ["no defined route", "当前路线模型没有连接这两个位置。"],
    ["horizon_reached", "这条人物经历的最大时间范围已经结束。"],
    ["live Hermes", "实时人物模型尚未就绪；本次没有回退到虚构运行。"],
    ["input cannot be empty", "请先写下你要问或要做的事。"],
    ["HTTP 423", "当前人物经历正在占用观测台。"],
    ["HTTP ", fallback],
  ];
  const matched = mappings.find(([needle]) => message.includes(needle));
  if (matched) return matched[1];
  if (/^[\u4e00-\u9fff]/.test(message) && !message.includes("HTTP")) return message;
  return fallback;
}

async function api(path, options = {}, requestKey = "") {
  const controller = new AbortController();
  if (requestKey && state.requestControllers[requestKey]) {
    state.requestControllers[requestKey].abort("superseded");
  }
  if (requestKey) state.requestControllers[requestKey] = controller;
  const timeout = window.setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
      signal: options.signal || controller.signal,
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.error || `HTTP ${response.status}`);
    return body;
  } catch (error) {
    if (controller.signal.aborted && controller.signal.reason === "timeout") {
      throw new Error("REQUEST_TIMEOUT");
    }
    if (controller.signal.aborted && controller.signal.reason === "superseded") return null;
    throw error;
  } finally {
    window.clearTimeout(timeout);
    if (requestKey && state.requestControllers[requestKey] === controller) {
      delete state.requestControllers[requestKey];
    }
  }
}

async function loadEvent(eventId = state.selectedEvent) {
  if (!eventId) return;
  const request = ++state.eventRequest;
  state.eventDetail = null;
  render();
  try {
    const detail = await api(`/api/events/${encodeURIComponent(eventId)}?tick=${state.tick}`, {}, "event");
    if (!detail) return;
    if (request === state.eventRequest) {
      state.eventDetail = detail;
      render();
    }
  } catch (error) {
    if (request !== state.eventRequest || error?.message === "The operation was aborted.") return;
    setNotice(friendlyError(error, "这个历史节点暂时无法打开。"), true);
    render();
  }
}

async function loadArchivist() {
  const [scenario, timeline] = await Promise.all([
    api("/api/scenario"),
    api("/api/timeline"),
  ]);
  state.scenario = scenario;
  state.timeline = timeline.items || [];
  state.tick = timeline.current_tick;
  state.selectedEvent = state.timeline.find((item) => item.is_current)?.id || state.timeline[0]?.id || null;
  state.active = null;
  state.debrief = null;
  state.lifetime = null;
  state.lifetimeWorldlineId = null;
  state.branchLifetimes = [];
  state.ledger = null;
  state.lastMoment = null;
  state.phase = "OBSERVE";
  state.view = "observe";
  render();
  await loadEvent();
}

async function loadLifetime(seat = state.lifetimeSeat, worldlineId = state.active?.worldline?.id) {
  if (!worldlineId) {
    setNotice("进入一次人物经历后，才能查看这条经历的详细记录。", false);
    render();
    return;
  }
  try {
    const response = await api(`/api/worldlines/${encodeURIComponent(worldlineId)}/lifetimes/${encodeURIComponent(seat)}`);
    state.lifetime = response.lifetime;
    state.lifetimeWorldlineId = worldlineId;
    state.lifetimeSeat = seat;
    state.phase = "LIFETIME";
    state.view = "lifetimes";
    render();
  } catch (error) {
    setNotice(friendlyError(error, "人物经历暂时无法打开。"), true);
    render();
  }
}

async function boot() {
  try {
    state.config = await api("/api/config");
    const active = await api("/api/worldlines/active");
    if (active.active) {
      state.active = active.active;
      state.phase = "SEAT_ACTIVE";
      render();
      await refreshActive();
      return;
    }
    await loadArchivist();
    if (state.config.setup_required) {
      state.settings = true;
      render();
    }
  } catch (error) {
    state.phase = "ERROR";
    state.notice = { text: friendlyError(error, "观测台暂时无法打开。"), error: true };
    render();
  }
}

function forkTick() {
  return numberValue(state.scenario?.entry?.event_id
    ? state.timeline.find((item) => item.id === state.scenario.entry.event_id)?.tick
    : state.scenario?.fork?.event_id
      ? state.timeline.find((item) => item.id === state.scenario.fork.event_id)?.tick
      : Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY);
}

function finalTick() {
  return numberValue(state.timeline[state.timeline.length - 1]?.tick, 78);
}

function render() {
  if (state.phase === "BOOT") {
    app.innerHTML = '<div class="boot-state" data-testid="boot-state"><span class="eyebrow">甲申 · 历史观测台</span><span>正在打开观测台</span></div>';
  } else if (state.phase === "ERROR") {
    app.innerHTML = '<div class="boot-state"><span class="eyebrow">甲申 · 历史观测台</span><span class="error-text">' + escapeHtml(state.notice?.text || "观测台暂时无法打开。") + '</span><button class="text-button" data-action="retry">重新打开</button></div>';
  } else if (state.phase === "ENTERING") {
    renderEntering();
  } else if (state.phase === "SEAT_ACTIVE") {
    renderSeat();
  } else if (state.phase === "LIFETIME") {
    renderLifetime();
  } else if (state.phase === "DEBRIEF") {
    renderDebrief();
  } else if (state.view === "sealed") {
    renderSealed();
  } else if (state.view === "lifetimes") {
    renderLifetime();
  } else if (state.view === "method") {
    renderMethod();
  } else {
    renderObserver();
  }
  if (state.drawer) renderDrawer();
  if (state.settings) renderSettingsModal();
  if (state.notice) renderNotice();
  bindActions();
}

function renderEntering() {
  app.innerHTML = '<main class="boot-state entering-state" role="status" aria-live="polite"><span class="eyebrow">人物经历 · 崇祯</span><strong>正在建立你的视野</strong><span>读取入口、携带的经历与当前权限……</span></main>';
}

function renderCover() {
  return '<main class="cover" data-testid="cover">' +
    '<svg class="cover-map" viewBox="0 0 1000 650" aria-hidden="true"><path d="M112 485 C260 400 290 205 482 252 S722 384 882 150" /><path d="M154 550 C330 520 438 370 560 335 S780 290 910 232" /><path d="M160 420 C330 420 420 110 680 140 S805 205 920 280" /><line x1="152" y1="485" x2="872" y2="150" /><line x1="470" y1="250" x2="820" y2="500" /><circle cx="482" cy="252" r="4" /><circle cx="882" cy="150" r="4" /><circle cx="820" cy="500" r="4" /></svg>' +
    '<div class="cover-content"><div class="cover-kicker">甲申 · 历史观测台</div><h1 class="cover-title">甲申</h1><p class="cover-subtitle">最后一个春天，三个人只知道各自收到的消息。</p><p class="cover-copy"><span>先看消息如何抵达</span><span>再进入一个历史位置</span><span>让每个判断留下因果</span></p><button class="cover-enter" data-action="enter-observe">开始观测&nbsp; →</button></div>' +
    '<div class="cover-meta">崇祯十七年正月初一 — 三月十九 · 1644</div></main>';
}

function renderShell(content, page = "observe") {
  return '<header class="topbar"><button class="brand" data-action="home" aria-label="返回甲申观测台"><span class="brand-mark">甲</span><span class="brand-name">甲申观测台</span></button><nav class="nav" aria-label="主导航"><button data-view="observe" aria-current="' + (page === "observe" ? "page" : "false") + '">观测台</button><button data-view="lifetimes" aria-current="' + (page === "lifetimes" ? "page" : "false") + '">人物经历</button><button data-view="sealed" aria-current="' + (page === "sealed" ? "page" : "false") + '">封存回看</button><button data-view="method" aria-current="' + (page === "method" ? "page" : "false") + '">方法与边界</button></nav><button class="utility-button" data-action="settings" aria-label="打开模型设置">⋯<span>模型设置</span></button></header>' + content;
}

function renderObserver() {
  const event = state.eventDetail?.event || {};
  const assertion = state.eventDetail?.assertions?.[0] || {};
  const whoKnows = state.eventDetail?.who_knows?.[assertion.id] || {};
  const entry = state.scenario?.entry || state.scenario?.fork || {};
  const timeline = state.timeline.map((item) =>
    '<button class="timeline-item" data-event="' + escapeHtml(item.id) + '" data-marker="' + escapeHtml(item.marker || "world") + '" data-past="' + item.is_past + '" aria-current="' + (item.id === state.selectedEvent ? "true" : "false") + '"><span class="timeline-dot"></span><span><span class="timeline-date">' + escapeHtml(shortDate(item.native_date)) + '</span><span class="timeline-title">' + escapeHtml(displayEventTitle(item)) + '</span><span class="timeline-tag">' + escapeHtml(item.has_fork ? labels.marker.fork : labels.marker[item.marker] || labels.marker.world) + '</span></span></button>'
  ).join("");
  const knowledge = (state.scenario?.actors || []).map((actor) => {
    const known = Boolean(whoKnows[actor.seat]);
    return '<div class="knowledge-row"><div><div class="knowledge-name">' + escapeHtml(actor.display_name) + '</div><div class="knowledge-seat">' + (known ? "已经收到相关消息" : "还没有收到相关消息") + '</div></div><div class="knowledge-status ' + (known ? "new" : "unknown") + '">' + (known ? "已知道" : "尚未知道") + '</div></div>';
  }).join("");
  const mapNodes = (state.scenario?.locations || []).map((location) =>
    '<g><circle class="map-node" cx="' + location.x + '%" cy="' + location.y + '%" r="1.2"></circle><text class="map-label" x="' + (location.x + 1.4) + '%" y="' + (location.y - 1) + '%">' + escapeHtml(location.display_name) + '</text></g>'
  ).join("");
  const mapLines = (state.scenario?.routes || []).map((route) => {
    const from = state.scenario.locations.find((item) => item.id === route.from_location);
    const to = state.scenario.locations.find((item) => item.id === route.to_location);
    return from && to ? '<line class="map-route ' + (route.id.includes("capital") ? "canonical" : "") + '" x1="' + from.x + '%" y1="' + from.y + '%" x2="' + to.x + '%" y2="' + to.y + '%"></line>' : "";
  }).join("");
  const mapObservationMarkers = Object.entries(state.eventDetail?.observations || {}).map(([seat, observations]) => {
    if (!observations.some((item) => item.delivered)) return "";
    const actor = (state.scenario?.actors || []).find((item) => item.seat === seat);
    const location = (state.scenario?.locations || []).find((item) => item.id === actor?.initial_location);
    return location ? '<circle class="map-message" cx="' + location.x + '%" cy="' + location.y + '%" r="1.2"></circle>' : "";
  }).join("");
  const canEnter = state.tick >= forkTick();
  const entryCta = canEnter
    ? '<button class="primary-button" data-action="enter-entry">进入此刻 · 崇祯&nbsp; ↘</button>'
    : '<div class="branch-unavailable"><strong>进入尚未开放</strong><span>先读取到“太子抚军江南”这个历史时刻，才能接管其中一个位置。</span></div>';
  const entryTopCta = canEnter
    ? '<button class="primary-button entry-top-button" data-action="enter-entry">进入此刻 · 崇祯</button>'
    : '';
  const sourceButton = assertion.id ? '<button class="text-button" data-action="source" data-source="' + escapeHtml(assertion.id) + '">查看史料依据&nbsp; ↗</button>' : "";
  const eventText = assertion.normalized_evidence || "这条事件记录由史料与观测台的历史规则共同约束。";
  const page = '<main class="page" data-testid="chronicle-page"><section class="page-header"><div><div class="page-kicker">历史观测</div><h1 class="page-title">先看见消息，再决定是否进入。</h1></div><p class="page-lede">历史事件已经发生，但消息不会同时抵达每个人。阅读真实收到的报告，直到你愿意接管一个位置。</p></section><section class="chronicle-layout"><aside class="timeline" aria-label="历史时间线"><div class="timeline-heading"><span class="section-label">历史时间线</span><span class="timeline-range">' + state.timeline.length + ' 个节点</span></div>' + timeline + '</aside><section class="observatory"><div class="observatory-top"><div><div class="date-display">' + escapeHtml(event.native_date || state.scenario?.summary?.window?.start) + '</div><div class="tick-display">' + dayLabel(state.tick) + ' · 既定历史</div></div><div class="observatory-controls"><button class="advance-button" data-action="advance-canon" ' + (state.pendingAction === "advance-canon" || state.tick >= finalTick() ? "disabled" : "") + '>' + (state.pendingAction === "advance-canon" ? "正在读取…" : "读取下一历史节点&nbsp; →") + '</button>' + entryTopCta + '</div></div><div class="map-frame"><svg class="map-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="甲申路线与消息图">' + mapLines + mapNodes + mapObservationMarkers + '</svg><div class="map-legend"><span>历史路线</span><span>' + (mapObservationMarkers ? "当前节点已有消息抵达" : "消息抵达差异见右侧") + '</span></div></div><div class="current-event"><div class="event-eyebrow"><span>当前节点</span><span>〔' + escapeHtml(evidenceLabel(assertion.evidence_status)) + '〕</span></div><h2 class="event-title">' + escapeHtml(displayEventTitle(event)) + '</h2><p class="event-copy">' + (state.eventDetail ? escapeHtml(displayResearchText(eventText)) : '<span class="drawer-loading">正在读取这个历史节点……</span>') + '</p><div class="event-actions">' + sourceButton + '</div></div><div class="entry-invitation"><div><div class="section-label">可进入的历史位置 · ' + escapeHtml(entry.display_name || "太子抚军江南") + '</div><h2>进入一个已经拥有过去的位置</h2><p>' + escapeHtml(entry.seat_brief || "你接管的不是一个新角色，而是一个已经拥有过去、命令与未决消息的历史位置。") + '</p></div><div class="entry-action">' + entryCta + '</div></div></section><aside class="context-panel"><div class="section-label">信息送达</div><h2 class="context-title">谁已经知道</h2><p class="context-copy">世界已经发生，不等于每个人都已经获知。</p><div class="knowledge-list">' + knowledge + '</div><div class="context-note">信息抵达的时间差，就是这次观测的一部分。</div></aside></section></main>';
  app.innerHTML = renderShell(page, "observe");
}

function reachedMarkup(context) {
  const items = Array.isArray(context?.what_reached_you) ? context.what_reached_you : [];
  if (!items.length) return '<div class="empty-state">目前没有新的已送达消息。</div>';
  return items.slice(-8).map((item) => '<article class="seat-message"><div class="seat-message-meta">' + escapeHtml(dayLabel(item.received_at ?? item.delivery_tick ?? 0)) + ' · ' + escapeHtml(channelLabel(item.channel)) + '</div><p>' + escapeHtml(observationPayload(item)) + '</p><span>' + escapeHtml(reliabilityLabel(item.reliability_hint)) + '</span></article>').join("");
}

function carriedMarkup(context) {
  const carry = context?.what_you_carry || {};
  const memory = carry.memory || {};
  const orders = Array.isArray(carry.open_orders) ? carry.open_orders : [];
  const messages = Array.isArray(carry.messages) ? carry.messages : [];
  return '<div class="carry-block"><span class="carry-label">记忆</span><p>' + escapeHtml(localizedRuntimeText(memory.text || "暂未形成长期记忆。")) + '</p><small>' + (memory.hash ? "已保存并校验" : "尚未形成长期记忆版本") + '</small></div><div class="carry-block"><span class="carry-label">未决命令</span><p>' + escapeHtml(orders.length ? orders.map((item) => item.payload || "一项未决命令").join("；") : "目前没有") + '</p></div><div class="carry-block"><span class="carry-label">消息线</span><p>' + escapeHtml(messages.length ? `${messages.length} 条消息正在这条经历中流动` : "目前没有分支消息") + '</p></div>';
}

function canonMomentMarkup(moment) {
  const events = Array.isArray(moment?.canon_events) ? moment.canon_events : [];
  if (!events.length) return '<span class="moment-detail">本次没有新的既定历史节点。</span>';
  return '<div class="moment-detail" aria-label="本次抵达的既定历史节点">' + events.map((event) => '<span><strong>' + escapeHtml(event.title || "既定历史节点") + '</strong><small>' + escapeHtml(shortDate(event.native_date || "")) + '</small></span>').join("") + '</div>';
}

function interactionMarkup() {
  const result = state.interaction;
  if (!result) return "";
  const action = result.interpreted_actions?.[0]?.type ? ` · ${escapeHtml(actionLabel(result.interpreted_actions[0].type))}` : "";
  const confirm = result.requires_confirmation
    ? '<div class="interaction-actions"><button class="primary-button" data-action="confirm-input" ' + (state.pendingAction ? "disabled" : "") + '>确认这项动作</button><button class="text-button" data-action="cancel-input" ' + (state.pendingAction ? "disabled" : "") + '>取消</button></div>'
    : "";
  const details = Array.isArray(result.result?.action_results)
    ? '<div class="interaction-details">' + result.result.action_results.map((item) => '<div><span>' + escapeHtml(actionLabel(item.action?.type)) + '</span><strong>' + escapeHtml(statusLabel(item.status)) + '</strong><small>' + escapeHtml(localizedRuntimeText(item.reason)) + '</small></div>').join("") + '</div>'
    : "";
  const feedback = result.result?.message || (result.result?.reason && result.result.reason !== result.answer ? result.result.reason : "");
  return '<section class="interaction-result ' + (result.status === "ACCEPTED" || result.kind === "inquiry" ? "accepted" : "rejected") + '" aria-live="polite"><div class="section-label">' + escapeHtml(result.kind === "inquiry" ? "查询结果" : statusLabel(result.status)) + action + '</div>' + (result.answer ? '<p>' + escapeHtml(localizedRuntimeText(result.answer)) + '</p>' : '') + (feedback ? '<p>' + escapeHtml(localizedRuntimeText(feedback)) + '</p>' : '') + details + confirm + '</section>';
}

function renderSeat() {
  const active = state.active || {};
  const context = active.context || {};
  const seat = active.seat || {};
  const worldline = active.worldline || {};
  const authority = Array.isArray(context.authority) ? context.authority.map(actionLabel).join("、") : "";
  const busy = Boolean(state.pendingAction);
  const pending = Boolean(worldline.pending_confirmation);
  const mode = runtimeModeLabel(worldline.runtime_mode);
  const roster = state.branchLifetimes.map((item) => {
    const actor = item.actor || {};
    const role = item.seat === worldline.seat ? "你当前接管" : item.controller === "AGENT" ? "人物模型" : "人类席位";
    return '<div class="roster-item"><strong>' + escapeHtml(actor.display_name || "当前人物") + '</strong><span>' + escapeHtml(role) + ' · ' + escapeHtml(item.status === "ACTIVE" ? "经历中" : "已封存") + '</span></div>';
  }).join("");
  const moment = state.lastMoment
    ? '<section class="moment-strip" aria-live="polite"><div><span class="section-label">刚刚发生</span><strong>' + escapeHtml(dayLabel(state.lastMoment.advanced_to)) + '</strong></div><div><span>新抵达</span><b>' + escapeHtml((state.lastMoment.deliveries || []).length) + '</b></div><div><span>人物响应</span><b>' + escapeHtml((state.lastMoment.agent_wakes || []).length) + '</b></div><div><span class="section-label">既定历史</span>' + canonMomentMarkup(state.lastMoment) + '</div><p>' + escapeHtml((state.lastMoment.deliveries || []).length ? "消息已经写入经历；人物模型只在触发条件满足时被唤醒。" : "时间推进完成，没有新的消息抵达。") + '</p></section>'
    : '<section class="moment-strip moment-empty"><span class="section-label">当前时刻</span><p>输入会先留下意图；按“推进到下一到达”才会让时间和消息继续流动。</p></section>';
  const submitDisabled = busy || pending ? "disabled" : "";
  const advanceDisabled = busy || pending ? "disabled" : "";
  const sealDisabled = busy || pending ? "disabled" : "";
  app.innerHTML = `<div class="seat-shell"><header class="seat-topbar"><button class="brand" data-action="home" aria-label="返回观测台"><span class="brand-mark">甲</span><span class="brand-name">甲申 · 人物经历</span></button><div class="seat-topbar-meta"><span>${escapeHtml(seat.display_name || "当前人物")}</span><span class="runtime-chip ${worldline.runtime_mode === "live" ? "live" : "fixture"}">${escapeHtml(mode)}</span><span>${escapeHtml(dayLabel(worldline.current_tick))}</span></div><button class="utility-button" data-action="settings" aria-label="打开模型设置">⋯<span>设置</span></button></header><main class="seat-page"><section class="seat-intro"><div><div class="page-kicker">人物经历 · 你的视角</div><h1 class="page-title">你现在只拥有这一个位置的视野。</h1></div><p class="page-lede">这里不是全局地图。你看到的是已经抵达的消息、携带的经历，以及当前真正拥有的权限。</p></section>${moment}<div class="seat-grid"><section class="seat-zone known-zone"><div class="seat-zone-kicker">01 · 已知世界</div><h2>你能确认什么</h2><div class="known-summary"><strong>${escapeHtml(context.known_world?.known_observation_count || 0)}</strong><span>条已进入你经历的消息</span><small>截至 ${escapeHtml(dayLabel(context.tick))} · 已知 ${escapeHtml((context.visible_assertion_ids || []).length)} 条判断</small></div><div class="uncertainty-list">${(context.known_uncertainty || []).map((item) => '<p>· ' + escapeHtml(item) + '</p>').join("")}</div></section><section class="seat-zone reached-zone"><div class="seat-zone-kicker">02 · 哪些信息抵达</div><h2>进入你耳中的报告</h2><div class="seat-messages">${reachedMarkup(context)}</div></section><section class="seat-zone carry-zone"><div class="seat-zone-kicker">03 · 你携带的经历</div><h2>记忆、命令与消息线</h2>${carriedMarkup(context)}<div class="authority-note">当前权限：${escapeHtml(authority || "未标记")}</div><button class="text-button" data-action="open-branch-lifetime">查看完整经历</button></section><section class="seat-zone roster-zone"><div class="seat-zone-kicker">04 · 同一条经历中的位置</div><h2>其他位置不会看见你的全部视角</h2><div class="roster-list">${roster || '<div class="empty-state">人物位置正在载入。</div>'}</div><p class="roster-note">每个位置都有自己的经历记录；收到消息不代表已经拥有完整世界。</p></section><section class="seat-zone action-zone"><div class="seat-zone-kicker">05 · 你要做什么？</div><h2>用自然语言留下一个意图</h2><p id="worldline-input-help" class="action-help">可以提问，也可以说出一项行动。观测台会依据当前经历的动作规则和你的权限判断：接受、不可能、未开放，或需要说得更明确。</p><label class="sr-only" for="worldline-input">要询问或提交的行动</label><textarea id="worldline-input" class="worldline-input" data-input-draft aria-describedby="worldline-input-help" ${submitDisabled} placeholder="例如：给东部传信，请尽快确认关口；或者：我现在收到过哪些消息？">${escapeHtml(state.inputDraft)}</textarea><div class="seat-actions"><button class="primary-button" data-action="submit-input" aria-busy="${state.pendingAction === "submit-input"}" ${submitDisabled}>${state.pendingAction === "submit-input" ? "正在记录…" : "提交意图"}</button><button class="secondary-button" data-action="advance-worldline" aria-busy="${state.pendingAction === "advance-worldline"}" ${advanceDisabled}>${state.pendingAction === "advance-worldline" ? "正在推进…" : "推进到下一到达"}</button><button class="text-button" data-action="seal-worldline" ${sealDisabled}>退出并封存</button></div>${interactionMarkup()}</section></div></main></div>`;
}

function debriefText(contexts) {
  if (!contexts?.length) return '<div class="empty-state">没有保存的视野记录。</div>';
  let previousCount = 0;
  return contexts.slice(-5).map((context) => {
    const items = Array.isArray(context.what_reached_you) ? context.what_reached_you : [];
    const newItems = items.slice(previousCount);
    previousCount = items.length;
    const shown = (newItems.length ? newItems : []).slice(-3);
    const summary = shown.map(observationPayload).join("；") || "没有新的消息";
    return '<article class="debrief-context"><div class="seat-message-meta">' + escapeHtml(dayLabel(context.tick)) + ' · 当时冻结的视野</div><p>已知消息 ' + escapeHtml(items.length) + ' 条；本次新增：' + escapeHtml(summary) + '</p><small>你携带的记忆：' + escapeHtml(localizedRuntimeText(context.what_you_carry?.memory?.text || "空")) + '</small></article>';
  }).join("");
}

function debriefChanges(items) {
  if (!items?.length) return '<div class="empty-state">这次经历没有由你提交的动作。</div>';
  return items.map((item) => {
    const payload = item.payload || {};
    const action = payload.action?.type ? actionLabel(payload.action.type) : "";
    const detail = localizedRuntimeText(payload.payload || payload.action?.payload || payload.reason || payload.premise || payload.assessment || payload.response?.assessment || "一条因果事件");
    return '<article class="debrief-change"><span>' + escapeHtml(labels.event[item.event_type] || "经历发生变化") + '</span><p>' + escapeHtml(action ? action + " · " + detail : detail) + '</p><small>' + escapeHtml(dayLabel(item.tick)) + '</small></article>';
  }).join("");
}

function renderDebrief() {
  const report = state.debrief || {};
  const stop = report.where_stopped || {};
  const projection = report.what_was_true?.branch_projection || {};
  const page = '<main class="page debrief-page"><section class="page-header"><div><div class="page-kicker">封存回看</div><h1 class="page-title">你看见了什么，改变了什么？</h1></div><p class="page-lede">这里不评估你做得好不好，只把保存下来的视野、分支真相和因果链放回同一张桌面。</p></section><section class="debrief-stop"><div><span class="section-label">停在哪里</span><strong>' + escapeHtml(dayLabel(stop.tick)) + ' · ' + escapeHtml(sealReasonLabel(stop.reason)) + '</strong></div><p>这条人物经历的最大范围：第 ' + escapeHtml(stop.horizon) + ' 日。终点没有被扩写成模型之外的答案。</p></section><div class="debrief-grid"><section class="debrief-block"><div class="seat-zone-kicker">01 · 你看见的</div><h2>你真正收到的消息</h2>' + debriefText(report.what_you_saw?.contexts) + '</section><section class="debrief-block"><div class="seat-zone-kicker">02 · 分支实际发生的</div><h2>这条经历留下的状态</h2><div class="truth-summary"><div><strong>' + escapeHtml(projection.tick || stop.tick || 0) + '</strong><span>分支停在第几日</span></div><div><strong>' + escapeHtml(capitalStatusLabel(projection.capital_status)) + '</strong><span>首都状态</span></div><div><strong>' + escapeHtml((projection.orders || []).length) + '</strong><span>分支命令</span></div><div><strong>' + escapeHtml((projection.messages || []).length) + '</strong><span>分支消息</span></div></div><p class="debrief-note">以上来自分支记录的确定性投影；它不代表你当时已经知道这些事实。</p></section><section class="debrief-block debrief-wide"><div class="seat-zone-kicker">03 · 你改变的</div><h2>由你的输入产生的因果链</h2><div class="debrief-changes">' + debriefChanges(report.what_you_changed) + '</div></section></div><div class="debrief-actions"><button class="primary-button" data-action="return-observe">回到观测台</button></div></main>';
  app.innerHTML = '<div class="seat-shell"><header class="seat-topbar"><div class="brand"><span class="brand-mark">甲</span><span class="brand-name">甲申 · 封存回看</span></div><div class="seat-topbar-meta">已封存的人物经历</div></header>' + page + '</div>';
}

function renderSealed() {
  const entries = state.sealed.length
    ? state.sealed.map((item) => '<article class="sealed-card"><div><span class="seat-zone-kicker">太子抚军江南</span><h2>已封存的人物经历</h2><p>停在第 ' + escapeHtml(item.current_tick) + ' 日 · ' + escapeHtml(sealReasonLabel(item.seal_reason)) + '</p></div><button class="text-button" data-action="open-debrief" data-worldline="' + escapeHtml(item.id) + '">打开回看&nbsp; →</button></article>').join("")
    : '<div class="empty-state">还没有已封存的经历。</div>';
  app.innerHTML = renderShell('<main class="page"><section class="page-header"><div><div class="page-kicker">已封存经历</div><h1 class="page-title">每次进入都会留下可回看的路径。</h1></div><p class="page-lede">封存后不能继续写入；你可以回看当时收到的消息、分支实际状态和由输入牵引出的因果链。</p></section><section class="sealed-list">' + entries + '</section></main>', "sealed");
}

function renderLifetime() {
  const lifetime = state.lifetime || {};
  const actor = lifetime.actor || {};
  const records = Array.isArray(lifetime.records) ? lifetime.records : [];
  const beliefs = lifetime.beliefs || {};
  const memory = lifetime.memory || {};
  const versions = Array.isArray(memory.versions) ? memory.versions : [];
  const actors = state.scenario?.actors || state.branchLifetimes.map((item) => item.actor).filter(Boolean);
  const switcher = actors.map((item) => '<button class="' + (item.seat === state.lifetimeSeat ? "active" : "") + '" data-action="load-lifetime" data-seat="' + escapeHtml(item.seat) + '">' + escapeHtml(item.display_name) + '</button>').join("");
  const recordMarkup = records.length
    ? records.slice(-12).map((record) => {
        const intentions = Array.isArray(record.intentions) ? record.intentions : [];
        const title = record.wake_type === "REFLECTION" ? "一次反思" : record.wake_type === "INTENT" ? "一项行动" : "一次观察";
        const detail = intentions.length ? intentions.map((item) => actionLabel(item.action)).join("、") : "没有留下新的行动意图";
        return '<article class="life-record"><span class="life-record-date">' + escapeHtml(dayLabel(record.tick)) + '</span><span class="life-record-dot ' + (record.wake_type === "REFLECTION" ? "memory" : "") + '"></span><div><div class="life-record-title">' + escapeHtml(title) + ' · ' + escapeHtml(detail) + '</div><div class="life-record-meta">收到 ' + escapeHtml((record.observation_ids || []).length) + ' 条观察 · 运行配置已固定</div></div></article>';
      }).join("")
    : '<div class="empty-state">这个人物还没有保存的经历。</div>';
  const beliefMarkup = Object.entries(beliefs).length
    ? Object.entries(beliefs).map(([, value]) => '<div class="belief-row"><strong>' + escapeHtml(beliefLabel(value)) + '</strong></div>').join("")
    : '<div class="empty-state">还没有形成可显示的判断。</div>';
  const versionMarkup = versions.length
    ? versions.slice(-5).map((item) => '<div class="lineage-item"><span>' + escapeHtml(dayLabel(item.tick)) + '</span><p>' + escapeHtml(item.reason || "一次反思留下的记忆") + '</p></div>').join("")
    : '<p>当前没有反思记忆版本；普通观察不会自动改写长期记忆。</p>';
  const returnAction = state.active?.worldline?.id ? "return-seat" : "return-observe";
  const returnLabel = state.active?.worldline?.id ? "返回人物经历" : "回到观测台";
  const page = '<main class="page lifetime-page" data-testid="lifetimes-page"><section class="page-header"><div><div class="page-kicker">人物经历 · 只读</div><h1 class="page-title">看见一条经历怎样留下痕迹。</h1></div><p class="page-lede">这里是只读的人物经历页：经历、判断与记忆沿着时间留下来，但不会在这里手动唤醒人物。</p></section><section class="lifetime-detail"><aside class="lifetime-rail"><div class="section-label">选择人物</div><div class="seat-switcher">' + switcher + '</div></aside><section class="life-content"><div class="life-intro"><div><h2>' + escapeHtml(actor.display_name || "当前人物") + '</h2><p>只读经历记录</p></div><div class="lifetime-stats"><div class="stat"><strong>' + escapeHtml(lifetime.stats?.observations || 0) + '</strong><span>观察</span></div><div class="stat"><strong>' + escapeHtml(lifetime.stats?.intentions || 0) + '</strong><span>意图</span></div><div class="stat"><strong>' + escapeHtml(lifetime.stats?.memories || 0) + '</strong><span>记忆版本</span></div></div></div><section class="life-line"><div class="section-label">经历 → 判断 → 记忆</div><div class="life-records">' + recordMarkup + '</div></section><section class="belief-panel"><div class="section-label">当前判断</div>' + beliefMarkup + '</section><section class="memory-lineage"><div class="section-label">记忆沿袭</div><h3>哪些经历被携带下来</h3><div class="lineage-flow"><span>经历</span><span>反思</span><span>记忆</span><span>后续行为</span></div>' + versionMarkup + '<p class="memory-copy">' + escapeHtml(localizedRuntimeText(memory.text || "当前没有长期记忆文本。")) + '</p></section></section></section><div class="debrief-actions"><button class="primary-button" data-action="' + returnAction + '">' + returnLabel + '</button></div></main>';
  app.innerHTML = renderShell(page, "lifetimes");
}

function renderMethod() {
  const page = '<main class="page"><section class="page-header"><div><div class="page-kicker">方法与边界</div><h1 class="page-title">深度来自边界，而不是答案数量。</h1></div><p class="page-lede">观测台把既定历史、人物视野、分支记录和实时人物模型分成四层，任何一层都不能冒充另一层。</p></section><section class="about-grid"><div class="about-block"><h2>先观测</h2><p>先从全局视角读取历史节点和消息送达差异。这里可以看全局，但还没有进入任何人物。</p></div><div class="about-block"><h2>再进入</h2><p>进入一个历史位置后，当前人物只接收自己的视野。未来事实不会提前穿过这道边界。</p></div><div class="about-block"><h2>留下行动</h2><p>分支行动只写入不可改写的经历记录；时间推进到下一条消息或重要观察，消息按路线延迟。实时人物模型不可用时，界面明确显示确定性演示。</p></div><div class="about-block"><h2>最后回看</h2><p>封存后并列展示你看见的、分支实际发生的和你改变的。不打分，不调用模型替你总结因果。</p></div><div class="formula">视野 <span>≠</span> 世界 · 输入 <span>→</span> 因果 · 事实 <span>≠</span> 解释</div></section></main>';
  app.innerHTML = renderShell(page, "method");
}

function renderDrawer() {
  const source = state.source;
  const assertion = source?.assertion || {};
  const citations = (source?.sources || []).map((item) => '<div class="citation"><strong>' + escapeHtml(item.work) + '</strong><span>' + escapeHtml(item.locator) + '</span>' + (item.url ? '<a href="' + escapeHtml(item.url) + '" target="_blank" rel="noreferrer">打开来源</a>' : '') + '</div>').join("");
  app.insertAdjacentHTML("beforeend", '<div class="drawer-scrim open" data-action="close-drawer" aria-hidden="true"></div><aside class="source-drawer open" role="dialog" aria-modal="true" aria-labelledby="source-drawer-title"><button class="drawer-close" data-action="close-drawer" aria-label="关闭史料依据">×</button><div class="drawer-kicker">史料依据</div><h2 id="source-drawer-title" class="drawer-title">' + escapeHtml(assertion.claim || "正在读取史料依据") + '</h2><span class="drawer-status">' + escapeHtml(evidenceLabel(assertion.evidence_status)) + '</span><section class="drawer-section"><h3>研究说明</h3><p>' + escapeHtml(assertion.normalized_evidence || "") + '</p></section><section class="drawer-section"><h3>来源</h3>' + (citations || '<p class="drawer-loading">正在读取来源……</p>') + '</section></aside>');
}

function renderSettingsModal() {
  const config = state.config || {};
  const message = state.settingsMessage ? '<div class="setup-result ' + (state.settingsMessage.error ? "error" : "") + '" role="' + (state.settingsMessage.error ? "alert" : "status") + '" aria-live="polite">' + escapeHtml(state.settingsMessage.text) + '</div>' : "";
  const bootstrapCta = config.setup_required ? "" : '<button class="text-button" data-action="bootstrap-profiles" ' + (state.pendingAction === "bootstrap-profiles" ? "disabled" : "") + '>' + (state.pendingAction === "bootstrap-profiles" ? "正在准备…" : "准备人物模型") + '</button>';
  app.insertAdjacentHTML("beforeend", '<div class="modal-scrim"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="settings-title" aria-describedby="settings-description"><button class="modal-close" data-action="close-settings" aria-label="关闭模型设置">×</button><div class="page-kicker">模型设置</div><h2 id="settings-title">把实时人物模型放在边界之外。</h2><p id="settings-description">连接信息只写入本机服务端的受限配置文件。没有就绪的实时人物模型时，观测台会明确显示确定性演示，不会伪装成实时经历。</p><div class="form-field"><label for="settings-base-url">模型服务地址</label><input id="settings-base-url" autocomplete="url" value="' + escapeHtml(config.base_url || "") + '" placeholder="https://provider.example/v1" /></div><div class="form-field"><label for="settings-api-key">API 密钥</label><input id="settings-api-key" autocomplete="off" type="password" placeholder="已保存的密钥无需再次输入" /></div><div class="form-field"><label for="settings-model">模型名称</label><input id="settings-model" autocomplete="off" value="' + escapeHtml(config.model || "") + '" placeholder="model-name" /></div><div class="form-field"><label for="settings-api-mode">调用协议</label><select id="settings-api-mode"><option value="chat_completions">Chat Completions</option><option value="responses">Responses</option></select></div><div class="form-field"><label for="settings-reasoning-effort">推理强度（可选）</label><input id="settings-reasoning-effort" autocomplete="off" value="' + escapeHtml(config.reasoning_effort || "") + '" placeholder="留空使用服务端默认值" /></div><div class="setup-connection">当前状态：' + escapeHtml(runtimeStatusLabel(config.hermes_status)) + ' · ' + (config.hermes_ready ? "实时人物模型已就绪" : "当前使用确定性演示") + '</div><div class="modal-actions">' + bootstrapCta + '<button class="secondary-button" data-action="test-settings" aria-busy="' + (state.pendingAction === "test-settings") + '" ' + (state.pendingAction === "test-settings" ? "disabled" : "") + '>' + (state.pendingAction === "test-settings" ? "正在测试…" : "测试连接") + '</button><button class="primary-button" data-action="save-settings" aria-busy="' + (state.pendingAction === "save-settings") + '" ' + (state.pendingAction === "save-settings" ? "disabled" : "") + '>' + (state.pendingAction === "save-settings" ? "正在保存…" : "保存设置") + '</button></div>' + message + '</section></div>');
  const mode = document.querySelector("#settings-api-mode");
  if (mode && config.api_mode) mode.value = config.api_mode;
}

function renderNotice() {
  app.insertAdjacentHTML("beforeend", '<div class="notice ' + (state.notice.error ? "error" : "") + '" role="' + (state.notice.error ? "alert" : "status") + '" aria-live="polite"><span>' + escapeHtml(state.notice.text) + '</span><button data-action="close-notice" aria-label="关闭提示">知道了</button></div>');
}

async function advanceCanon() {
  state.pendingAction = "advance-canon";
  render();
  try {
    const result = await api("/api/canon/advance-next", { method: "POST", body: "{}" });
    state.tick = result.current_tick;
    state.timeline = (await api(`/api/timeline?tick=${state.tick}`)).items;
    state.selectedEvent = result.event?.id || state.selectedEvent;
    await loadEvent(state.selectedEvent);
  } catch (error) {
    setNotice(friendlyError(error), true);
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function enterEntry() {
  if (state.pendingAction) return;
  state.pendingAction = "enter-entry";
  state.phase = "ENTERING";
  render();
  try {
    const response = await api("/api/worldlines", {
      method: "POST",
      body: JSON.stringify({ entry_id: state.scenario.entry.id, seat: "A", live: Boolean(state.config?.hermes_ready) }),
    });
    state.active = response;
    state.interaction = null;
    state.inputDraft = "";
    state.lastMoment = null;
    state.phase = "SEAT_ACTIVE";
    await refreshActive();
  } catch (error) {
    state.phase = "OBSERVE";
    setNotice(friendlyError(error, "暂时无法进入这个历史位置。"), true);
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function refreshActive() {
  const response = await api("/api/worldlines/active");
  if (!response.active) {
    await loadArchivist();
    return false;
  }
  const worldlineId = response.active.worldline.id;
  const [surface, lifetimes, ledger] = await Promise.all([
    api(`/api/worldlines/${encodeURIComponent(worldlineId)}/context`),
    api(`/api/worldlines/${encodeURIComponent(worldlineId)}/lifetimes`),
    api(`/api/worldlines/${encodeURIComponent(worldlineId)}/ledger`),
  ]);
  state.active = surface;
  state.branchLifetimes = lifetimes.lifetimes || [];
  state.ledger = ledger;
  state.phase = "SEAT_ACTIVE";
  return true;
}

async function submitInput() {
  if (state.pendingAction) return;
  const textarea = document.querySelector(".worldline-input");
  const text = textarea ? textarea.value.trim() : state.inputDraft.trim();
  state.inputDraft = text;
  if (!text || !state.active?.worldline?.id) return;
  state.pendingAction = "submit-input";
  render();
  try {
    const response = await api(`/api/worldlines/${state.active.worldline.id}/input`, { method: "POST", body: JSON.stringify({ text }) });
    state.interaction = response.interaction;
    state.active.context = response.context;
    await refreshActive();
    state.lastMoment = null;
    state.inputDraft = "";
  } catch (error) {
    setNotice(friendlyError(error), true);
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function confirmInput() {
  if (state.pendingAction) return;
  const confirmation = state.interaction?.confirmation_id;
  if (!confirmation || !state.active?.worldline?.id) return;
  state.pendingAction = "confirm-input";
  render();
  try {
    const response = await api(`/api/worldlines/${state.active.worldline.id}/confirm`, { method: "POST", body: JSON.stringify({ confirmation_id: confirmation }) });
    state.interaction = response.interaction;
    state.active.context = response.context;
    await refreshActive();
    state.lastMoment = null;
  } catch (error) {
    setNotice(friendlyError(error), true);
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function cancelInput() {
  if (state.pendingAction) return;
  const confirmation = state.interaction?.confirmation_id;
  if (!confirmation || !state.active?.worldline?.id) return;
  state.pendingAction = "cancel-input";
  render();
  try {
    const response = await api(`/api/worldlines/${state.active.worldline.id}/cancel`, { method: "POST", body: JSON.stringify({ confirmation_id: confirmation }) });
    state.interaction = response.interaction;
    await refreshActive();
    state.lastMoment = null;
  } catch (error) {
    setNotice(friendlyError(error), true);
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function advanceWorldline() {
  if (state.pendingAction || !state.active?.worldline?.id || state.active.worldline.pending_confirmation) return;
  state.pendingAction = "advance-worldline";
  render();
  try {
    const response = await api(`/api/worldlines/${state.active.worldline.id}/advance`, { method: "POST", body: JSON.stringify({ live: state.active.worldline.runtime_mode === "live" }) });
    state.lastMoment = response.advanced_to === undefined ? null : response;
    state.interaction = null;
    if (response.worldline.status === "SEALED") {
      state.debrief = await api(`/api/worldlines/${response.worldline.id}/debrief`);
      state.phase = "DEBRIEF";
    } else {
      await refreshActive();
    }
  } catch (error) {
    setNotice(friendlyError(error), true);
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function sealWorldline() {
  if (state.pendingAction || !state.active?.worldline?.id || state.active.worldline.pending_confirmation) return;
  state.pendingAction = "seal-worldline";
  render();
  try {
    const response = await api(`/api/worldlines/${state.active.worldline.id}/seal`, { method: "POST", body: JSON.stringify({ reason: "user_exit" }) });
    state.debrief = await api(`/api/worldlines/${response.worldline.id}/debrief`);
    state.lastMoment = null;
    state.phase = "DEBRIEF";
  } catch (error) {
    setNotice(friendlyError(error), true);
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function openDebrief(worldlineId) {
  try {
    state.debrief = await api(`/api/worldlines/${encodeURIComponent(worldlineId)}/debrief`);
    state.phase = "DEBRIEF";
    render();
  } catch (error) {
    setNotice(friendlyError(error), true);
    render();
  }
}

async function loadSealed() {
  try {
    state.sealed = (await api("/api/worldlines")).worldlines || [];
    state.view = "sealed";
    render();
  } catch (error) {
    setNotice(friendlyError(error), true);
    render();
  }
}

async function loadSource(assertionId) {
  try {
    state.source = await api(`/api/sources/${encodeURIComponent(assertionId)}`);
    state.drawer = true;
    render();
  } catch (error) {
    setNotice(friendlyError(error, "史料依据暂时无法打开。"), true);
    render();
  }
}

async function bootstrapProfiles() {
  if (state.pendingAction) return;
  state.pendingAction = "bootstrap-profiles";
  state.settingsMessage = null;
  render();
  try {
    const result = await api("/api/bootstrap", { method: "POST", body: "{}" });
    state.settingsMessage = {
      text: result.ready ? "人物模型已准备完成，可以开始观测。" : "人物配置已准备；共享服务就绪后才会进入实时模式。",
      error: false,
    };
    state.config = await api("/api/config");
  } catch (error) {
    state.settingsMessage = { text: friendlyError(error, "人物模型暂时无法准备，请检查本机服务。"), error: true };
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function testSettings() {
  state.pendingAction = "test-settings";
  state.settingsMessage = null;
  render();
  const baseUrl = document.querySelector("#settings-base-url")?.value.trim() || "";
  const apiKey = document.querySelector("#settings-api-key")?.value || "";
  const model = document.querySelector("#settings-model")?.value.trim() || "";
  const apiMode = document.querySelector("#settings-api-mode")?.value || "chat_completions";
  const reasoningEffort = document.querySelector("#settings-reasoning-effort")?.value.trim() || "";
  try {
    const result = await api("/api/setup/test", { method: "POST", body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, model, api_mode: apiMode, reasoning_effort: reasoningEffort }) });
    state.settingsMessage = { text: result.ok ? "模型连接成功。" : (result.message || "连接没有成功。"), error: !result.ok };
  } catch (error) {
    state.settingsMessage = { text: friendlyError(error), error: true };
  } finally {
    state.pendingAction = "";
    render();
  }
}

async function saveSettings() {
  state.pendingAction = "save-settings";
  render();
  const baseUrl = document.querySelector("#settings-base-url")?.value.trim() || "";
  const apiKey = document.querySelector("#settings-api-key")?.value || "";
  const model = document.querySelector("#settings-model")?.value.trim() || "";
  const apiMode = document.querySelector("#settings-api-mode")?.value || "chat_completions";
  const reasoningEffort = document.querySelector("#settings-reasoning-effort")?.value.trim() || "";
  try {
    await api("/api/setup/configure", { method: "POST", body: JSON.stringify({ base_url: baseUrl, api_key: apiKey, model, api_mode: apiMode, reasoning_effort: reasoningEffort }) });
    state.config = await api("/api/config");
    state.settings = false;
    state.settingsMessage = null;
    setNotice("设置已保存在本机服务端。", false);
  } catch (error) {
    state.settingsMessage = { text: friendlyError(error), error: true };
  } finally {
    state.pendingAction = "";
    render();
    if (!state.settings) restoreModalFocus();
  }
}

function restoreModalFocus() {
  const target = state.modalReturnFocus;
  state.modalReturnFocus = null;
  if (target?.isConnected) {
    target.focus();
    return;
  }
  if (!target?.action) return;
  const replacement = [...document.querySelectorAll("[data-action]")].find((element) => {
    if (element.dataset.action !== target.action) return false;
    return !target.source || element.dataset.source === target.source;
  });
  replacement?.focus();
}

function rememberModalFocus() {
  const target = document.activeElement;
  state.modalReturnFocus = target?.dataset?.action
    ? { action: target.dataset.action, source: target.dataset.source || "" }
    : target;
}

function bindActions() {
  document.onkeydown = (event) => {
    if (event.key === "Escape") {
      if (state.settings) {
        state.settings = false;
        state.settingsMessage = null;
        render();
        restoreModalFocus();
      } else if (state.drawer) {
        state.drawer = false;
        state.source = null;
        render();
        restoreModalFocus();
      } else if (state.notice) {
        state.notice = null;
        render();
      }
      return;
    }
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog || event.key !== "Tab") return;
    const focusable = [...dialog.querySelectorAll("button, input, select, textarea, a[href]")].filter((item) => !item.disabled);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };
  document.querySelectorAll("[data-view]").forEach((element) => element.addEventListener("click", async () => {
    if (state.phase !== "OBSERVE") return;
    const view = element.dataset.view;
    if (view === "sealed") return loadSealed();
    if (view === "lifetimes") return loadLifetime("A");
    if (view === "method") {
      state.view = "method";
      render();
    } else {
      state.view = "observe";
      render();
    }
  }));
  document.querySelectorAll("[data-event]").forEach((element) => element.addEventListener("click", async () => {
    state.selectedEvent = element.dataset.event;
    await loadEvent(state.selectedEvent);
  }));
  document.querySelectorAll("[data-action]").forEach((element) => element.addEventListener("click", async () => {
    const action = element.dataset.action;
    if (action === "enter-observe") { await loadArchivist(); return; }
    if (action === "retry") { state.phase = "BOOT"; render(); await boot(); return; }
    if (action === "home") {
      if (state.phase === "SEAT_ACTIVE") {
        setNotice("当前经历尚未封存；请使用页面底部的“退出并封存”。", true);
        render();
        return;
      }
      await loadArchivist();
      return;
    }
    if (action === "advance-canon") { await advanceCanon(); return; }
    if (action === "enter-entry") { await enterEntry(); return; }
    if (action === "submit-input") { await submitInput(); return; }
    if (action === "confirm-input") { await confirmInput(); return; }
    if (action === "cancel-input") { await cancelInput(); return; }
    if (action === "advance-worldline") { await advanceWorldline(); return; }
    if (action === "seal-worldline") { await sealWorldline(); return; }
    if (action === "open-debrief") { await openDebrief(element.dataset.worldline); return; }
    if (action === "open-branch-lifetime") { await loadLifetime("A"); return; }
    if (action === "load-lifetime") { await loadLifetime(element.dataset.seat); return; }
    if (action === "return-seat") { state.phase = "SEAT_ACTIVE"; state.view = "observe"; render(); return; }
    if (action === "return-observe") { await loadArchivist(); return; }
    if (action === "source") { rememberModalFocus(); await loadSource(element.dataset.source); if (state.drawer) document.querySelector(".drawer-close")?.focus(); else state.modalReturnFocus = null; return; }
    if (action === "close-drawer") { state.drawer = false; state.source = null; render(); restoreModalFocus(); return; }
    if (action === "settings") { rememberModalFocus(); state.settings = true; render(); document.querySelector("#settings-base-url")?.focus(); return; }
    if (action === "close-settings") { state.settings = false; state.settingsMessage = null; render(); restoreModalFocus(); return; }
    if (action === "test-settings") { await testSettings(); return; }
    if (action === "bootstrap-profiles") { await bootstrapProfiles(); return; }
    if (action === "save-settings") { await saveSettings(); return; }
    if (action === "close-notice") { state.notice = null; render(); }
  }));
  const input = document.querySelector("[data-input-draft]");
  if (input) input.addEventListener("input", () => { state.inputDraft = input.value; });
}

render();
boot();
