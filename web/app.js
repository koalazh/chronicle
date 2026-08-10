const root = document.querySelector("#app");

const state = {
  config: null,
  crisis: null,
  active: null,
  page: "home",
  lens: "world",
  perspective: null,
  world: null,
  archive: [],
  history: null,
  replay: null,
  replayLens: "then",
  replayActor: "",
  busy: false,
  activity: null,
  operationSeq: 0,
  viewSeq: 0,
  draftDecision: "",
  notice: "",
  error: "",
};

function actorDisplayName(actorId) {
  const actors = state.crisis?.actors || [];
  return actors.find((actor) => actor.id === actorId)?.display_name || actorId;
}

function defaultPlayableActor() {
  return state.crisis?.actors.find((actor) => actor.playable) || null;
}

function fallbackActorId() {
  return state.active?.human_actor || state.crisis?.actors[0]?.id || "";
}

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function decisionOutcomeMarkup(decision) {
  return (decision.operation_results || [])
    .map((operation) => {
      if (operation.status === "COMMITTED" && operation.tool === "communicate") {
        const arrival = operation.arrival_tick == null ? "" : `，预计第 ${operation.arrival_tick} 日抵达`;
        return `<small class="decision-outcome committed">已发出致${escapeHtml(operation.recipient)}${arrival}</small>`;
      }
      if (operation.status === "REJECTED") {
        const recipient = operation.recipient ? `（致${escapeHtml(operation.recipient)}）` : "";
        return `<small class="decision-outcome rejected">未执行${recipient}：${escapeHtml(operation.reason || "这项请求未执行")}</small>`;
      }
      return "";
    })
    .join("");
}

function decisionResultNotice(result) {
  const rejected = (result?.operations || []).filter((operation) => operation.status === "REJECTED");
  if (!rejected.length) return "";
  const committed = (result?.operations || []).filter((operation) => operation.status === "COMMITTED").length;
  return committed
    ? `决定已入卷，但有 ${rejected.length} 项请求未执行；书案已标出。`
    : "决定已入卷，但没有请求真正执行；书案已标出。";
}

async function api(path, options = {}) {
  const { timeoutMs = 180000, ...requestOptions } = options;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, {
      ...requestOptions,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(requestOptions.headers || {}) },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      const message = typeof detail === "object" && detail !== null ? detail.message : detail;
      const error = new Error(message || `请求失败（${response.status}）`);
      error.status = response.status;
      if (typeof detail === "object" && detail !== null) Object.assign(error, detail);
      throw error;
    }
    return payload;
  } finally {
    clearTimeout(timeout);
  }
}

function route() {
  const value = location.hash.replace(/^#\/?/, "");
  if (["home", "watch", "desk", "replay", "archive", "history", "setup", "dev"].includes(value)) {
    state.page = value;
  } else {
    state.page = state.active ? (state.active.mode === "WATCH" ? "watch" : "desk") : "home";
  }
}

function go(page) {
  location.hash = `#/${page}`;
}

function runtimeLabel() {
  const phase = state.active?.runtime_mode === "live" ? state.active.runtime_phase : "";
  if (phase === "BOOTSTRAPPING") return "这一局正在建立主体";
  if (phase === "RECONCILING") return "这一局正在恢复主体";
  if (phase === "FAILED") return "这一局尚未准备好";
  if (phase === "SEALING") return "这一局正在封存";
  if (phase === "CLEANUP_PENDING") return "卷册正在收束";
  if (phase === "READY") return "这一局的主体已经就绪";
  if (!state.config) return "正在核对运行环境";
  if (state.config.setup_required) return "尚未连接主体所需的模型服务";
  return "模型已配置；创建危局时会自动建立主体";
}

function interactionLocked() {
  return state.busy || Boolean(state.activity);
}

function runtimePending() {
  return state.active?.runtime_mode === "live" && state.active.runtime_phase !== "READY";
}

function runMutationLocked() {
  return interactionLocked() || runtimePending();
}

function runtimeTransitionLocked() {
  return ["BOOTSTRAPPING", "RECONCILING", "SEALING", "CLEANUP_PENDING"].includes(
    state.active?.runtime_phase,
  );
}

function runtimeFolio() {
  const run = state.active;
  if (!run || run.runtime_mode !== "live" || run.runtime_phase === "READY") return "";
  const copy = {
    BOOTSTRAPPING: ["这一局正在建立主体", "人物、私有视野与第一段行动正在依次入卷。"],
    RECONCILING: ["这一局正在恢复", "正在核对上一段历史留下的主体与运行状态。"],
    FAILED: ["这一局尚未准备好", "这一页暂不能继续；可以重新准备，或将它封存。"],
    SEALING: ["这一局正在封存", "此刻正在结束，暂不能再写入新的行动。"],
    CLEANUP_PENDING: ["卷册已经封存", "历史已经可回看；本地的主体正在安全收束。"],
  };
  const [defaultTitle, defaultDescription] = copy[run.runtime_phase] || ["这一局正在处理", "请稍候。"];
  const [title, description] = run.runtime_error_code === "runtime_wake_unresolved"
    ? ["这一局无法安全恢复", "有一段行动的结果无法确认；可以封存这局，但不能再次投递它。"]
    : [defaultTitle, defaultDescription];
  const retry = run.runtime_phase === "FAILED" && run.runtime_error_code !== "runtime_wake_unresolved"
    ? '<button class="quiet activity-reconcile" data-action="retry-runtime">重新准备</button>'
    : "";
  return `<section class="activity-banner runtime-${escapeHtml(run.runtime_phase.toLowerCase())}" role="status" aria-live="polite" aria-busy="${run.runtime_phase !== "FAILED"}">
    <span class="activity-stamp" aria-hidden="true">卷</span>
    <div class="activity-copy"><span class="column-label">这一局</span><strong>${escapeHtml(title)}</strong><p>${escapeHtml(description)}</p></div>
    ${retry}
  </section>`;
}

function activityText(activity = state.activity) {
  if (!activity) return null;
  const copy = {
    decision: {
      submitting: ["决定已收，正在入卷", "书案暂不接受第二笔落笔。"],
      advancing: ["历史正在向前展开", "正在寻找下一个有意义的时刻。"],
      reconciling: ["正在核对这一笔是否已经入卷", "结果尚未确认，先保留这一页。"],
      failed: ["这一笔需要核对", "暂不重新落笔，先确认这一局的状态。"],
    },
    continue: {
      advancing: ["历史正在向前展开", "正在寻找下一个有意义的时刻。"],
      reconciling: ["正在核对推进结果", "这一页还没有得到确定回音。"],
    },
    seal: {
      sealing: ["正在封存这一卷", "把已经发生的事收进可回看的卷册。"],
      reconciling: ["正在核对封存结果", "封存请求的结果尚未确认。"],
    },
    runtime: {
      bootstrapping: ["正在建立这一局", "人物、私有视野与第一段行动正在依次入卷。"],
      reconciling: ["正在重新准备这一局", "正在核对主体与运行状态。"],
    },
  };
  return copy[activity.kind]?.[activity.phase] || ["正在处理这一页", "请稍候，暂不能再次落笔。"];
}

function activityBanner() {
  const activity = state.activity;
  if (!activity) return "";
  const [title, description] = activityText(activity);
  const pending = activity.pendingText || "";
  const reconcileAction = ["reconciling", "failed"].includes(activity.phase)
    ? `<button class="quiet activity-reconcile" data-action="reconcile-run">核对这一页</button>`
    : "";
  return `<section class="activity-banner ${escapeHtml(activity.phase)}" role="status" aria-live="polite" aria-busy="true">
    <span class="activity-stamp" aria-hidden="true">卷</span>
    <div class="activity-copy"><span class="column-label">正在进行</span><strong>${escapeHtml(title)}</strong><p>${escapeHtml(description)}</p></div>
    ${pending ? `<p class="pending-folio-text">${escapeHtml(pending)}</p>` : ""}
    ${reconcileAction}
  </section>`;
}

function decisionSlotCommitted() {
  return decisionSlotState() === "COMMITTED";
}

function decisionSlotState() {
  const decision = state.active?.human_decision;
  return decision && Number(decision.tick) === Number(state.active.current_tick)
    ? decision.state
    : "NONE";
}

function syncDecisionActivity() {
  if (state.activity || state.active?.mode !== "TAKEOVER") return;
  const decisionState = decisionSlotState();
  if (!["RUNNING", "FAILED"].includes(decisionState)) return;
  state.activity = {
    kind: "decision",
    phase: decisionState === "FAILED" ? "failed" : "reconciling",
    pendingText: "",
    seq: ++state.operationSeq,
    runId: state.active.id,
    tick: state.active.current_tick,
  };
  state.busy = true;
}

function chrome(content, { compact = false } = {}) {
  const locked = interactionLocked();
  const disabled = locked ? "disabled" : "";
  return `
    <header class="topbar">
      <button class="brand" data-action="go-home" aria-label="回到甲申首页" ${disabled}>
        <span class="brand-seal">甲</span><span>Chronicle · 甲申</span>
      </button>
      <nav class="main-nav" aria-label="主导航">
        <button data-page="home" ${state.page === "home" ? 'aria-current="page"' : ""} ${disabled}>首页</button>
        <button data-page="history" ${state.page === "history" ? 'aria-current="page"' : ""} ${disabled}>史实背景</button>
        <button data-page="archive" ${state.page === "archive" ? 'aria-current="page"' : ""} ${disabled}>封存卷册</button>
      </nav>
      <button class="setup-link" data-page="setup" ${disabled}>设置</button>
    </header>
    <main class="${compact ? "main compact" : "main"}">${state.activity && !["watch", "desk"].includes(state.page) ? activityBanner() : ""}${content}</main>
    <div class="notice-stack" aria-live="polite">
      ${state.notice ? `<p class="notice">${escapeHtml(state.notice)}</p>` : ""}
      ${state.error ? `<p class="notice error">${escapeHtml(state.error)}</p>` : ""}
    </div>`;
}

function homePage() {
  const playableActor = defaultPlayableActor();
  const actors = state.crisis.actors
    .map(
      (actor, index) => `
      <article class="actor-intro">
        <span class="folio">0${index + 1}</span>
        <div>
          <h3>${escapeHtml(actor.display_name)}</h3>
          <p>${escapeHtml(actor.role_charter.who)}</p>
          <small>${escapeHtml(actor.role_charter.tensions.join(" · "))}</small>
        </div>
      </article>`,
    )
    .join("");
  return chrome(`
    <section class="home-hero">
      <div class="hero-mast">
        <p class="kicker">一六四四 · 一段仍未决定的时间</p>
        <h1>甲申</h1>
        <p class="hero-subtitle">${escapeHtml(state.crisis.title)}</p>
      </div>
      <div class="hero-copy">
        <p>${escapeHtml(state.crisis.checkpoint.summary)}</p>
        <p class="runtime-note">${escapeHtml(runtimeLabel())}</p>
        <div class="hero-actions">
          <button class="primary" data-action="start-watch" ${state.busy || state.active || state.config.setup_required ? "disabled" : ""}>旁观这场危局</button>
          <button class="secondary" data-action="start-takeover" ${state.busy || state.active || state.config.setup_required || !playableActor ? "disabled" : ""}>${playableActor ? `成为${escapeHtml(playableActor.display_name)}` : "暂无可成为的主体"}</button>
        </div>
        ${
          state.active
            ? `<button class="continue-existing" data-action="open-active">已有一局尚未封存，继续进入</button>`
            : ""
        }
      </div>
    </section>
    <section class="home-corridor" aria-label="危局态势预览">
      ${surfaceMarkup(state.crisis.surface, { preview: true })}
    </section>
    <section class="actor-intros">
      <div class="section-heading"><span>${state.crisis.actors.length} 个主体</span><h2>各自知道一部分，也各自承担选择</h2></div>
      ${actors}
    </section>
    <section class="boundary-note">
      <span>本局止于</span>
      <p>${escapeHtml(state.crisis.boundary.stop_before)}</p>
      <small>${escapeHtml(state.crisis.boundary.reason)}</small>
    </section>
  `);
}

function surfaceMarkup(surface, options = {}) {
  if (!surface) return "";
  if (surface.kind === "SPATIAL") return spatialSurfaceMarkup(surface, options);
  return `<section class="surface-unavailable"><p>${escapeHtml(surface.title || "危局态势")}</p></section>`;
}

function spatialSurfaceMarkup(surface, options = {}) {
  const locations = surface.locations || [];
  const actors = surface.actors || [];
  const messages = surface.messages || [];
  const actorAt = new Map();
  actors.forEach((actor) => {
    const items = actorAt.get(actor.location) || [];
    items.push(actor);
    actorAt.set(actor.location, items);
  });
  const nodes = locations
    .map((location) => {
      const present = actorAt.get(location.id) || [];
      return `<div class="corridor-node" data-location="${escapeHtml(location.id)}">
        <span class="node-mark"></span>
        <strong>${escapeHtml(location.display_name)}</strong>
        <div class="node-actors">
          ${present
            .map(
              (actor) => `<span class="actor-chip ${options.ownActor === actor.id ? "own" : ""}">
                ${options.hideOthers && options.ownActor !== actor.id ? "动向未知" : escapeHtml(actor.display_name)}
              </span>`,
            )
            .join("")}
        </div>
      </div>`;
    })
    .join("");
  const letters = messages
    .slice(-5)
    .map(
      (message) => `<li>
        <span>${message.status === "delivered" ? "已抵达" : "在途中"}</span>
        <strong>${escapeHtml(actorDisplayName(message.sender))} → ${escapeHtml(actorDisplayName(message.recipient))}</strong>
        ${options.preview ? "" : `<small>第 ${message.arrival_tick} 日抵达</small>`}
      </li>`,
    )
    .join("");
  return `<div class="corridor ${options.preview ? "preview" : ""}">
    <div class="corridor-track">${nodes}</div>
    ${letters ? `<ol class="letters" aria-label="走廊中的书信">${letters}</ol>` : ""}
  </div>`;
}

function runHeader(title, lede) {
  const run = state.active;
  const locked = interactionLocked() || runtimeTransitionLocked();
  return `<header class="run-header">
    <div>
      <p class="kicker">${escapeHtml(state.crisis.title)} · 第 ${run.current_tick} 日</p>
      <h1>${escapeHtml(title)}</h1>
      <p>${escapeHtml(lede)}</p>
    </div>
    <div class="run-actions">
      <span class="day-count">${run.current_tick}<small> / ${run.maximum_tick} 日</small></span>
      <button class="quiet" data-action="seal-run" ${locked ? "disabled" : ""}>封存这一局</button>
    </div>
  </header>${runtimeFolio()}${activityBanner()}`;
}

function watchPage() {
  if (!state.active) return homePage();
  const lensButtons = [
    ["world", "世界"],
    ...(state.crisis?.actors || []).map((actor) => [actor.id, actor.display_name]),
  ]
    .map(
      ([id, label]) => `<button data-lens="${id}" ${state.lens === id ? 'aria-current="true"' : ""} ${interactionLocked() ? "disabled" : ""}>${label}</button>`,
    )
    .join("");
  const body = state.lens === "world" ? worldLens() : actorLens();
  return chrome(`
    ${runHeader("旁观这场危局", "世界继续向前，而每个人只活在自己当时能够知道的部分里。")}
    <div class="lens-switcher" role="tablist" aria-label="切换观察视角">${lensButtons}</div>
    ${body}
    <footer class="continue-bar">
      <div><span>下一个有意义的时刻</span><small>送达、约定到期或主体的新行动</small></div>
      <button class="primary" data-action="continue-run" ${runMutationLocked() ? "disabled" : ""}>继续</button>
    </footer>
  `);
}

function worldLens() {
  if (!state.world) return loadingBlock();
  const inTransit = state.world.messages.filter((message) => message.status === "in_transit").length;
  return `<section class="lens-sheet">
    <div class="sheet-heading">
      <div><span>世界视野</span><h2>${escapeHtml(state.world.surface?.title || "危局态势")}</h2></div>
      <p>旁观者可以看见世界事实，但人物的私下打算仍留在各自视角中。</p>
    </div>
    ${surfaceMarkup(state.world.surface)}
    <div class="world-marginalia">
      <article><span>仍在路上</span><strong>${inTransit}</strong><p>消息必须走完路程，收信人才会知道。</p></article>
      <article><span>模拟边界</span><strong>第 ${state.active.maximum_tick} 日前</strong><p>进入大规模交战裁定前，本局停止。</p></article>
    </div>
  </section>`;
}

function actorLens() {
  if (!state.perspective || state.perspective.actor.id !== state.lens) return loadingBlock();
  const view = state.perspective;
  const plan = view.plan[0];
  const commitments = view.commitments.length
    ? view.commitments
        .map(
          (item) => `<li><span>${item.status === "PENDING" ? `第 ${item.due_tick} 日` : item.status === "DUE" ? "等待处置" : "已复查"}</span>${escapeHtml(item.purpose)}</li>`,
        )
        .join("")
    : "<li class=\"empty\">尚未给未来的自己留下约定。</li>";
  const knowledge = view.knowledge
    .slice(-5)
    .map((item) => `<li>${escapeHtml(typeof item === "string" ? item : item.content || item.observation || "一项已知情况")}</li>`)
    .join("");
  return `<section class="lens-sheet actor-sheet">
    <div class="actor-title">
      <span>人物视野</span><h2>${escapeHtml(view.actor.display_name)}</h2>
      <p>${escapeHtml(view.role_charter.who)}</p>
    </div>
    ${surfaceMarkup(view.surface, { ownActor: view.actor.id })}
    <p class="corridor-unknown">其他人物的当前位置与动向，尚未进入这一视野。</p>
    <div class="private-columns">
      <article>
        <span class="column-label">此刻的打算</span>
        <h3>${plan ? escapeHtml(plan.objective) : "尚在辨认局势"}</h3>
        ${plan ? `<ol>${plan.steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ol>` : ""}
      </article>
      <article>
        <span class="column-label">已经知道</span>
        <ul>${knowledge || '<li class="empty">没有新消息。</li>'}</ul>
      </article>
      <article>
        <span class="column-label">留给未来</span>
        <ul>${commitments}</ul>
      </article>
    </div>
  </section>`;
}

function deskPage() {
  if (!state.active) return homePage();
  const view = state.perspective;
  const messages = (view?.knowledge || [])
    .filter((item) => typeof item === "object" && item.kind === "message")
    .slice(-6)
    .map(
      (item) => `<article class="letter-sheet"><span>第 ${item.received_tick} 日抵达 · ${escapeHtml(actorDisplayName(item.sender))}</span><p>${escapeHtml(item.content)}</p></article>`,
    )
    .join("");
  const knownSituation = (view?.known_situation || [])
    .map((item) => `<li>${escapeHtml(item.text)}</li>`)
    .join("");
  const unresolved = (view?.commitments || [])
    .filter((item) => ["PENDING", "DUE"].includes(item.status))
    .map(
      (item) => `<article class="matter-sheet ${item.status === "DUE" ? "due" : ""}"><span>${item.status === "DUE" ? "现在需要处置" : `第 ${item.due_tick} 日重新判断`}</span><p>${escapeHtml(item.purpose)}</p></article>`,
    )
    .join("");
  const decisions = (view?.decisions || [])
    .slice(-5)
    .map(
      (item) => `<li><span>第 ${item.tick} 日</span>${escapeHtml(item.summary)}${decisionOutcomeMarkup(item)}</li>`,
    )
    .join("");
  const outgoing = (view?.outgoing_messages || [])
    .slice(-5)
    .map(
      (item) => `<li><span>${item.source === "checkpoint" ? "场景起始信" : "本局决定"} · ${item.status === "delivered" ? `第 ${item.arrival_tick} 日送达` : `预计第 ${item.arrival_tick} 日抵达`} · 致 ${escapeHtml(actorDisplayName(item.recipient))}</span>${escapeHtml(item.content)}</li>`,
    )
    .join("");
  const resolved = (view?.commitments || [])
    .filter((item) => item.status === "FULFILLED")
    .slice(-3)
    .map((item) => `<li><span>已经处理</span>${escapeHtml(item.purpose)}</li>`)
    .join("");
  const committedDecision = (view?.decisions || [])
    .slice()
    .reverse()
    .find((item) => Number(item.tick) === Number(state.active.current_tick));
  const decisionState = decisionSlotState();
  const decisionLocked = runMutationLocked() || decisionState !== "NONE";
  const busyCopy = activityText() || (runtimePending()
    ? ["这一局正在准备", "请等待这一页恢复为可落笔的状态。"]
    : ["正在处理这一页", "请稍候，暂不能再次落笔。"]);
  const decisionCopy = state.activity?.pendingText || "";
  const settledCopy = committedDecision?.summary || "这一日已经入卷。";
  const summaryTitle = decisionState === "COMMITTED"
    ? "这一日已经入卷"
    : decisionState === "FAILED"
      ? "这一笔需要核对"
      : "正在核对这一笔";
  const summaryCopy = decisionState === "COMMITTED"
    ? settledCopy
    : decisionState === "FAILED"
      ? "这一笔处理失败；请先核对这一局的状态。"
      : "结果尚未确认，先保留这一页。";
  const canContinue = state.active.can_continue !== false;
  const continueCopy = canContinue
    ? "这一日已入卷；可以继续推进下一件有意义的事。"
    : "当前没有可推进事件，可以封存这一局。";
  const decisionDesk = decisionLocked
    ? `<div class="pending-folio ${decisionSlotCommitted() ? "settled" : ""}" role="status" aria-live="polite" aria-busy="${state.activity || runtimePending() ? "true" : "false"}">
        <span class="activity-stamp" aria-hidden="true">卷</span>
        <div><span class="column-label">${decisionSlotCommitted() ? "当前模拟日" : "这一页"}</span><strong>${decisionSlotCommitted() ? summaryTitle : state.activity ? busyCopy[0] : summaryTitle}</strong><p>${escapeHtml(decisionSlotCommitted() ? summaryCopy : decisionCopy || (state.activity ? busyCopy[1] : summaryCopy))}</p>${decisionSlotCommitted() ? `<small>${continueCopy}</small>` : ""}</div>
      </div>`
    : `<label for="decision">命令、回信或等待的理由</label>
        <textarea id="decision" rows="8" placeholder="例如：先向关外追问通行与指挥条件，两日后若仍无北京的可靠答复，再重新比较。">${escapeHtml(state.draftDecision)}</textarea>
        <button class="primary wide" data-action="submit-decision">送入这段历史</button>
        <button class="quiet wide" data-action="silence">暂不追加命令，继续</button>`;
  const deskContinue = decisionSlotCommitted()
    ? `<footer class="continue-bar desk-continue">
        <div><span>下一件有意义的事</span><small>送达、约定到期或主体的新行动</small></div>
        <button class="primary" data-action="continue-run" ${runMutationLocked() || !canContinue ? "disabled" : ""}>${canContinue ? "继续推进" : "暂无可推进事件"}</button>
      </footer>`
    : "";
  return chrome(`
    ${runHeader(`${view?.actor?.display_name || "你的"}书案`, "你只能看见进入自己视野的消息；其它主体仍会在视野之外行动。")}
    <section class="desk-layout">
      <div class="desk-main">
        <div class="desk-corridor">
          <span class="column-label">此刻所见的态势</span>
          ${surfaceMarkup(view?.surface, { ownActor: view?.actor?.id })}
          <p class="corridor-unknown">其它主体的动向，尚未有可靠消息。</p>
          <div class="known-strip"><span>已经知道</span><ul>${knownSituation || '<li class="empty">尚无可确认的新情况。</li>'}</ul></div>
        </div>
        <div class="inbox">
          <div class="section-heading"><span>新到</span><h2>${messages ? "送到案前的来书" : "路上仍有消息"}</h2></div>
          ${messages || '<p class="empty-copy">尚无新信抵达。你可以等待，也可以先送出自己的话。</p>'}
        </div>
        <section class="unresolved-matters">
          <div class="section-heading"><span>尚未解决</span><h2>留给此刻与未来的判断</h2></div>
          ${unresolved || '<p class="empty-copy">没有已经到期或等待复查的事项。</p>'}
        </section>
        <section class="desk-record">
          <div class="section-heading"><span>已经发出</span><h2>你的决定与仍在路上的话</h2></div>
          <div class="desk-record-columns"><article><h3>决定</h3><ul>${decisions || '<li class="empty">尚未写下新的决定。</li>'}${resolved}</ul></article><article><h3>去信</h3><ul>${outgoing || '<li class="empty">尚未发出新的信。</li>'}</ul></article></div>
        </section>
      </div>
      <aside class="decision-desk">
        <p class="kicker">你要如何处置</p>
        <h2>${decisionSlotCommitted() ? "这一日已入卷" : "写下一项决定"}</h2>
        <p>可以在一句话里同时写信、准备行动并约定何时重新判断。世界只接受你有权做的部分。</p>
        ${decisionDesk}
        ${deskContinue}
      </aside>
    </section>
  `);
}

function replayPage() {
  if (!state.replay) return chrome(`<section class="empty-page"><p class="kicker">回看</p><h1>先从封存卷册选择一局</h1><button class="secondary" data-page="archive">打开卷册</button></section>`);
  const visibleItems = state.replay.items.filter(
    (item) => state.replayLens === "after" || item.visible_to.includes(state.replayActor),
  );
  const visibleIds = new Set(visibleItems.map((item) => item.id));
  const items = visibleItems
    .map(
      (item) => {
        const causes = item.causes
          .filter((cause) => visibleIds.has(cause.id))
          .map((cause) => `承接「${escapeHtml(cause.title)}」`)
          .join("、");
        return `<article class="replay-item ${item.private ? "revealed" : ""}" data-event-id="${escapeHtml(item.id)}">
        <span class="replay-day">第 ${item.tick} 日</span>
        <div><small>${item.actor_id ? escapeHtml(actorDisplayName(item.actor_id) || "人物") : "世界"}</small><h3>${escapeHtml(item.title)}</h3>${causes ? `<span class="replay-cause">${causes}</span>` : ""}${item.detail ? `<p>${escapeHtml(item.detail)}</p>` : ""}</div>
      </article>`;
      },
    )
    .join("");
  const actorSwitch = state.replay.actors
    .map((actor) => `<button data-replay-actor="${escapeHtml(actor.id)}" ${state.replayActor === actor.id ? 'aria-current="true"' : ""}>${escapeHtml(actor.display_name)}</button>`)
    .join("");
  const replayTitle =
    state.replay.run.mode === "WATCH" ? "三条人生如何相遇" : "在你看不见的地方";
  const cleanupPending = state.replay.run.runtime_mode === "live"
    && state.replay.run.runtime_phase === "CLEANUP_PENDING"
    && state.replay.run.runtime_error_code;
  const cleanupNotice = cleanupPending
    ? `<section class="activity-banner runtime-cleanup_pending" role="status" aria-live="polite"><span class="activity-stamp" aria-hidden="true">卷</span><div class="activity-copy"><span class="column-label">封存之后</span><strong>卷册已经封存</strong><p>历史可以回看，本地资源还没有完全收束。</p></div><button class="quiet activity-reconcile" data-action="retry-cleanup" data-cleanup-id="${escapeHtml(state.replay.run.id)}">再次收束</button></section>`
    : "";
  return chrome(`
    <header class="replay-header">
      <p class="kicker">回看这一局</p><h1>${replayTitle}</h1>
      <p>封存让你看见：当时的视野，与世界同时发生的事，并不是同一份记录。</p>
      ${cleanupNotice}
      <div class="replay-switch">
        <button data-replay-lens="then" ${state.replayLens === "then" ? 'aria-current="true"' : ""}>当时可见</button>
        <button data-replay-lens="after" ${state.replayLens === "after" ? 'aria-current="true"' : ""}>封存后全景</button>
      </div>
      ${state.replayLens === "then" ? `<div class="replay-switch actor-replay-switch" aria-label="选择当时视角">${actorSwitch}</div>` : ""}
    </header>
    <section class="replay-list">${items}</section>
  `, { compact: true });
}

function archivePage() {
  const runs = state.archive.length
    ? state.archive
        .map(
          (run) => `<article class="archive-row">
            <div><span>${run.mode === "WATCH" ? "旁观" : run.mode === "TAKEOVER" ? "吴三桂" : "旧版留存"}</span><h2>${run.mode === "LEGACY_V2" ? "甲申旧卷" : "山海关之前"}</h2></div>
            <p>封存于第 ${run.current_tick} 日<br><small>${escapeHtml(run.seal_reason || "已经结束")}</small></p>
            ${run.mode !== "LEGACY_V2" ? `<div class="archive-actions"><button class="secondary" data-replay-id="${escapeHtml(run.id)}">打开回看</button>${run.runtime_phase === "CLEANUP_PENDING" && run.runtime_error_code ? `<button class="quiet" data-action="retry-cleanup" data-cleanup-id="${escapeHtml(run.id)}">再次收束</button>` : ""}</div>` : '<span class="legacy-mark">仅作历史留存</span>'}
          </article>`,
        )
        .join("")
    : '<div class="empty-page inline"><h2>卷册仍是空的</h2><p>封存一局后，它会留在这里。</p></div>';
  return chrome(`<header class="page-header"><p class="kicker">卷册</p><h1>封存卷册</h1><p>结束并不抹去当时的未知。每一局都保留自己的路。</p></header><section class="archive-list">${runs}</section>`);
}

function historyPage() {
  if (!state.history) return chrome(loadingBlock());
  const sources = state.history.sources
    .map(
      (source) => `<li><strong>${escapeHtml(source.work)}</strong><span>${escapeHtml(source.title || source.edition || "史料")}</span></li>`,
    )
    .join("");
  const assertions = state.history.assertions
    .map((item) => `<article><span>${item.evidence_status === "disputed" ? "存在争议" : item.provenance === "scenario_assumption" ? "建模假设" : "史料支持"}</span><p>${escapeHtml(item.claim)}</p></article>`)
    .join("");
  return chrome(`
    <header class="page-header"><p class="kicker">史实背景</p><h1>史料告诉我们的，<br>与本局尚未决定的</h1><p>危局从史料可辩护的检查点开始；人物后来的真实行动只供封存后参照，不会被强行注入模拟。</p></header>
    <section class="history-grid">
      <div class="source-register"><span class="column-label">主要来源</span><ol>${sources}</ol></div>
      <div class="assertion-register">${assertions}</div>
    </section>
    <section class="history-boundary"><span>建模边界</span><h2>${escapeHtml(state.history.boundary.stop_before)}</h2><p>${escapeHtml(state.history.boundary.reason)}</p></section>
  `);
}

function setupPage() {
  return chrome(`
    <section class="setup-page">
      <div><p class="kicker">本机设置</p><h1>连接主体所需的模型服务</h1><p>凭据只写入本机私有运行目录，不进入页面、卷册或版本库。</p></div>
      <form id="setup-form" class="setup-form">
        <label>模型服务地址<input name="base_url" type="url" value="${escapeHtml(state.config?.base_url || "")}" placeholder="https://…/v1" required></label>
        <label>API Key<input name="api_key" type="password" autocomplete="off" placeholder="${state.config?.api_key ? "已保存；留空保持不变" : "仅保存在本机"}"></label>
        <label>模型<input name="model" value="${escapeHtml(state.config?.model || "")}" required></label>
        <label>接口<select name="api_mode"><option value="chat_completions" ${state.config?.api_mode !== "responses" ? "selected" : ""}>对话接口</option><option value="responses" ${state.config?.api_mode === "responses" ? "selected" : ""}>响应接口</option></select></label>
        <button class="primary" type="submit" ${state.busy ? "disabled" : ""}>保存并核对</button>
      </form>
      <aside class="setup-status"><span>当前状态</span><strong>${escapeHtml(runtimeLabel())}</strong><p>主体服务由项目私有目录承载；未就绪时不会伪装成真实运行。</p></aside>
    </section>
  `);
}

function devPage() {
  return chrome(`<section class="dev-page"><p class="kicker">开发面</p><h1>当前 Run 的原始记录</h1><pre>${escapeHtml(JSON.stringify(state.dev || { message: "没有 active Run" }, null, 2))}</pre></section>`, { compact: true });
}

function loadingBlock() {
  return '<div class="loading-block">正在展开这一页……</div>';
}

function render() {
  if (!state.crisis || !state.config) {
    const bootMessage = state.error
      ? `<p>观测台暂时打不开</p><small>${escapeHtml(state.error)}</small><button class="secondary" data-action="retry-boot">重新打开</button>`
      : "<p>正在打开这段时间</p>";
    root.innerHTML = `<div class="boot-state${state.error ? " boot-error" : ""}"><span>甲申</span>${bootMessage}</div>`;
    return;
  }
  const pages = {
    home: homePage,
    watch: watchPage,
    desk: deskPage,
    replay: replayPage,
    archive: archivePage,
    history: historyPage,
    setup: setupPage,
    dev: devPage,
  };
  root.innerHTML = (pages[state.page] || homePage)();
}

async function refreshActive(timeoutMs = 180000) {
  const payload = await api("/api/runs/active", { timeoutMs });
  state.active = payload.run;
  syncDecisionActivity();
}

async function loadRunView() {
  const run = state.active;
  if (!run) return;
  const runId = run.id;
  const lens = state.lens;
  const page = state.page;
  const viewSeq = ++state.viewSeq;
  let world = null;
  let perspective = null;
  if (run.mode === "WATCH") {
    if (lens === "world") {
      world = await api(`/api/runs/${runId}/world`);
    } else {
      perspective = await api(`/api/runs/${runId}/perspective/${lens}`);
    }
  } else {
    perspective = await api(`/api/runs/${runId}/perspective/${run.human_actor}`);
  }
  if (viewSeq !== state.viewSeq || state.active?.id !== runId || state.lens !== lens || state.page !== page) {
    return;
  }
  state.world = world;
  state.perspective = perspective;
}

async function loadPageData() {
  if (state.page === "archive") state.archive = (await api("/api/archive")).runs;
  if (state.page === "history") state.history = await api("/api/history");
  if (state.page === "dev" && state.active) state.dev = await api(`/api/dev/runs/${state.active.id}`);
  if (["watch", "desk"].includes(state.page)) await loadRunView();
}

function currentActivity(seq) {
  return state.activity?.seq === seq;
}

function setActivityPhase(seq, phase) {
  if (!currentActivity(seq)) return;
  state.activity.phase = phase;
  state.busy = true;
  render();
}

function finishActivity(seq) {
  if (!currentActivity(seq)) return;
  state.activity = null;
  state.busy = false;
}

function unknownRequest(error) {
  return error?.name === "AbortError" || !error?.status;
}

function errorText(error) {
  return error?.message || "请求没有完成。";
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function runAction(action, activity = null) {
  if (interactionLocked()) return;
  state.error = "";
  state.notice = "";
  state.busy = true;
  const seq = ++state.operationSeq;
  if (activity) {
    state.activity = {
      ...activity,
      seq,
      runId: state.active?.id || "",
      tick: state.active?.current_tick,
    };
  }
  render();
  try {
    await action(seq);
  } catch (error) {
    if (activity && (unknownRequest(error) || error.status >= 500) && currentActivity(seq)) {
      state.activity.phase = "reconciling";
      state.error = "请求结果尚未确认；请先核对这一局的状态。";
    } else {
      state.error = error.name === "AbortError" ? "请求等待过久，请重试。" : errorText(error);
      if (currentActivity(seq)) state.activity = null;
    }
  } finally {
    if (currentActivity(seq) && !["reconciling", "failed"].includes(state.activity.phase)) {
      finishActivity(seq);
    }
    if (!state.activity) syncDecisionActivity();
    state.busy = Boolean(state.activity);
    render();
  }
}

async function startRun(mode) {
  const payload = {
    crisis_id: state.crisis.summary.id,
    mode,
    live: true,
  };
  if (mode === "TAKEOVER") {
    const actor = defaultPlayableActor();
    if (actor) payload.human_actor_id = actor.id;
  }
  const result = await api("/api/runs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  state.active = result.run;
  state.config = await api("/api/config");
  state.lens = "world";
  if (result.start_error) state.notice = result.start_error;
  await loadRunView();
  state.page = mode === "WATCH" ? "watch" : "desk";
  go(mode === "WATCH" ? "watch" : "desk");
}

async function continueRun(seq = state.activity?.seq, resultNotice = "") {
  const previousTick = Number(state.active.current_tick);
  const result = await api(`/api/runs/${state.active.id}/continue`, { method: "POST", body: "{}" });
  state.active = result.run;
  const committed = result.run?.human_decision;
  const currentTick = Number(result.run?.current_tick);
  const tickChanged = currentTick > previousTick;
  if (
    result.advanced ||
    (committed?.state === "COMMITTED" && Number(committed.tick) === Number(result.run.current_tick))
  ) {
    state.draftDecision = "";
  }
  state.notice = result.advanced && tickChanged
    ? "时间向前走到了下一个有意义的时刻。"
    : result.advanced
      ? "这一刻已经处理，可以继续核对下一件事。"
      : result.run?.can_continue !== false
        ? "这一日已经入卷；还有事件可以继续推进。"
        : committed?.state === "COMMITTED" && Number(committed.tick) === Number(result.run.current_tick)
          ? "这一日已经入卷；当前没有可推进事件，可以封存这一局。"
          : "当前没有可推进事件，可以封存这一局。";
  if (resultNotice) state.notice = resultNotice;
  await loadRunView();
  if (seq && currentActivity(seq)) state.activity.tick = state.active.current_tick;
}

async function sealRun() {
  const result = await api(`/api/runs/${state.active.id}/seal`, {
    method: "POST",
    body: JSON.stringify({ reason: "user_exit" }),
  });
  const runId = result.run.id;
  state.notice = result.run.runtime_error_code
    ? "卷册已经封存；本地资源仍在收束，可以稍后再次收束。"
    : "这一局已经封存，可以回看。";
  state.active = null;
  state.replay = await api(`/api/runs/${runId}/replay`);
  state.replayLens = state.replay.run.mode === "WATCH" ? "after" : "then";
  state.replayActor = state.replay.run.human_actor || fallbackActorId();
  state.page = "replay";
  go("replay");
}

async function retryCleanup(runId = state.replay?.run?.id) {
  if (!runId) return;
  const result = await api(`/api/runs/${runId}/runtime/retry`, {
    method: "POST",
    body: "{}",
  });
  if (state.replay?.run?.id === runId) {
    state.replay = await api(`/api/runs/${runId}/replay`);
  }
  if (state.page === "archive") state.archive = (await api("/api/archive")).runs;
  state.notice = result.run.runtime_error_code
    ? "本地资源仍在收束，请稍后再次核对。"
    : "本地资源已经收束。";
}

async function retryRuntime() {
  const result = await api(`/api/runs/${state.active.id}/runtime/retry`, {
    method: "POST",
    body: "{}",
  });
  state.active = result.run;
  state.notice = result.run.runtime_phase === "READY"
    ? "这一局已经恢复，可以继续。"
    : "这一局仍在准备；页面会保留当前状态。";
  await loadRunView();
}

async function submitDecision(silence = false, capturedText = "", seq) {
  const text = silence ? "" : capturedText.trim();
  if (!silence && !text) return;
  const runId = state.active.id;
  const tick = state.active.current_tick;
  let result;
  try {
    result = await api(`/api/runs/${state.active.id}/decision`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
  } catch (error) {
    if (error.code === "decision_already_exists" && error.state === "COMMITTED") {
      state.notice = "这一日已经入卷，正在向前推进。";
      setActivityPhase(seq, "advancing");
      await continueRun(seq);
      return;
    }
    if (error.code === "decision_in_progress" && error.state === "RUNNING") {
      await reconcileDecision(seq, runId, error.tick ?? tick);
      return;
    }
    if (error.code === "decision_failed" && error.state === "FAILED") {
      state.error = "这一笔处理失败；请先核对这一局的状态。";
      setActivityPhase(seq, "failed");
      return;
    }
    throw error;
  }
  state.notice = result.silence ? "你选择沉默，世界仍会继续。" : result.summary;
  setActivityPhase(seq, "advancing");
  await continueRun(seq, decisionResultNotice(result));
}

async function reconcileDecision(seq, runId, tick) {
  setActivityPhase(seq, "reconciling");
  for (let attempt = 0; attempt < 4; attempt += 1) {
    const payload = await api("/api/runs/active", { timeoutMs: 15_000 });
    if (!currentActivity(seq)) return;
    if (!payload.run || payload.run.id !== runId) {
      state.error = "这一局已经不在活动列表中，请打开封存卷册核对。";
      return;
    }
    state.active = payload.run;
    if (Number(payload.run.current_tick) !== Number(tick)) {
      state.notice = "这一日已经被推进；先核对当前书案。";
      state.draftDecision = "";
      await loadRunView();
      finishActivity(seq);
      return;
    }
    const decision = payload.run.human_decision || {};
    if (decision.state === "COMMITTED" && Number(decision.tick) === Number(tick)) {
      setActivityPhase(seq, "advancing");
      await continueRun(seq);
      return;
    }
    if (decision.state === "FAILED") {
      state.error = "这一笔处理失败；请先核对这一局的状态。";
      setActivityPhase(seq, "failed");
      return;
    }
    if (attempt < 3) await wait(1200);
  }
  state.notice = "仍未核对到确定结果；可以稍后再次核对这一页。";
}

async function reconcileActive() {
  const activity = state.activity;
  if (!activity || !["reconciling", "failed"].includes(activity.phase)) return;
  const seq = activity.seq;
  state.error = "";
  setActivityPhase(seq, "reconciling");
  try {
    if (activity.kind === "decision") {
      await reconcileDecision(seq, activity.runId, activity.tick);
    } else if (activity.kind === "seal") {
      await refreshActive(15_000);
      if (!state.active) {
        state.replay = await api(`/api/runs/${activity.runId}/replay`);
        state.replayLens = state.replay.run.mode === "WATCH" ? "after" : "then";
        state.replayActor = state.replay.run.human_actor || fallbackActorId();
        state.page = "replay";
        finishActivity(seq);
      } else {
        state.notice = "卷册仍在处理中；暂不重复封存。";
      }
    } else {
      await refreshActive(15_000);
      await loadRunView();
      finishActivity(seq);
    }
  } catch (error) {
    if (currentActivity(seq)) {
      state.error = "仍未核对到确定结果，请稍后再次核对。";
      state.activity.phase = "reconciling";
    }
  }
  if (currentActivity(seq) && !["reconciling", "failed"].includes(state.activity.phase)) {
    finishActivity(seq);
  }
  state.busy = Boolean(state.activity);
  render();
}

async function openReplay(runId) {
  state.replay = await api(`/api/runs/${runId}/replay`);
  state.replayLens = state.replay.run.mode === "WATCH" ? "after" : "then";
  state.replayActor = state.replay.run.human_actor || fallbackActorId();
  state.page = "replay";
  go("replay");
}

root.addEventListener("click", (event) => {
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (interactionLocked()) {
    if (action === "reconcile-run") return reconcileActive();
    event.preventDefault();
    return;
  }
  const page = event.target.closest("[data-page]")?.dataset.page;
  if (page) return go(page);
  const lens = event.target.closest("[data-lens]")?.dataset.lens;
  if (lens) {
    state.lens = lens;
    return runAction(loadRunView);
  }
  const replayLens = event.target.closest("[data-replay-lens]")?.dataset.replayLens;
  if (replayLens) {
    state.replayLens = replayLens;
    return render();
  }
  const replayActor = event.target.closest("[data-replay-actor]")?.dataset.replayActor;
  if (replayActor) {
    state.replayActor = replayActor;
    return render();
  }
  const replayId = event.target.closest("[data-replay-id]")?.dataset.replayId;
  if (replayId) return runAction(() => openReplay(replayId));
  const cleanupId = event.target.closest("[data-cleanup-id]")?.dataset.cleanupId;
  if (cleanupId) return runAction(() => retryCleanup(cleanupId), { kind: "seal", phase: "reconciling" });
  const capturedDecision = document.querySelector("#decision")?.value || "";
  const actions = {
    "go-home": () => go("home"),
    "retry-boot": () => boot(),
    "start-watch": () => runAction(
      () => startRun("WATCH"),
      { kind: "runtime", phase: "bootstrapping" },
    ),
    "start-takeover": () => runAction(
      () => startRun("TAKEOVER"),
      { kind: "runtime", phase: "bootstrapping" },
    ),
    "open-active": () => go(state.active.mode === "WATCH" ? "watch" : "desk"),
    "retry-runtime": () => runAction(retryRuntime, { kind: "runtime", phase: "reconciling" }),
    "continue-run": () => runAction(continueRun, { kind: "continue", phase: "advancing" }),
    "seal-run": () => runAction(sealRun, { kind: "seal", phase: "sealing" }),
    "submit-decision": () => {
      if (!capturedDecision.trim()) {
        state.error = "请写下决定，或选择暂不追加命令。";
        return render();
      }
      state.draftDecision = capturedDecision;
      return runAction(
        (seq) => submitDecision(false, capturedDecision, seq),
        { kind: "decision", phase: "submitting", pendingText: capturedDecision.trim() },
      );
    },
    silence: () => runAction(
      (seq) => submitDecision(true, "", seq),
      { kind: "decision", phase: "submitting", pendingText: "已选择不追加命令" },
    ),
  };
  if (actions[action]) actions[action]();
});

root.addEventListener("submit", (event) => {
  if (event.target.id !== "setup-form") return;
  event.preventDefault();
  const form = new FormData(event.target);
  runAction(async () => {
    const payload = Object.fromEntries(form.entries());
    payload.reasoning_effort = "";
    const test = await api("/api/setup/test", { method: "POST", body: JSON.stringify(payload) });
    if (!test.ok) throw new Error(test.message);
    await api("/api/setup/configure", { method: "POST", body: JSON.stringify(payload) });
    state.config = await api("/api/config");
    state.notice = "模型服务已经保存。创建新局时会建立真实主体。";
  });
});

root.addEventListener("input", (event) => {
  if (event.target.id === "decision" && !interactionLocked()) {
    state.draftDecision = event.target.value;
  }
});

window.addEventListener("hashchange", () => {
  if (interactionLocked()) {
    history.replaceState(null, "", `#/${state.page}`);
    render();
    return;
  }
  route();
  runAction(loadPageData);
});

async function boot() {
  state.error = "";
  route();
  render();
  try {
    const bootTimeoutMs = 15_000;
    [state.config, state.crisis] = await Promise.all([
      api("/api/config", { timeoutMs: bootTimeoutMs }),
      api("/api/crisis", { timeoutMs: bootTimeoutMs }),
    ]);
    await refreshActive(bootTimeoutMs);
    if (state.active && !location.hash) state.page = state.active.mode === "WATCH" ? "watch" : "desk";
    await loadPageData();
  } catch (error) {
    state.error = error.message;
  }
  render();
}

boot();
