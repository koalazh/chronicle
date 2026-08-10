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
  replayActor: "wu-sangui",
  busy: false,
  notice: "",
  error: "",
};

const actorNames = {
  "li-zicheng": "李自成",
  "wu-sangui": "吴三桂",
  dorgon: "多尔衮",
};

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
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
    if (!response.ok) throw new Error(payload.detail || `请求失败（${response.status}）`);
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
  if (!state.config) return "正在核对运行环境";
  if (state.config.setup_required) return "尚未连接主体所需的模型服务";
  if (state.config.hermes_ready) return "真实主体运行已就绪";
  return "模型已配置；主体服务尚待启动";
}

function chrome(content, { compact = false } = {}) {
  return `
    <header class="topbar">
      <button class="brand" data-action="go-home" aria-label="回到甲申首页">
        <span class="brand-seal">甲</span><span>Chronicle · 甲申</span>
      </button>
      <nav class="main-nav" aria-label="主导航">
        <button data-page="home" ${state.page === "home" ? 'aria-current="page"' : ""}>首页</button>
        <button data-page="history" ${state.page === "history" ? 'aria-current="page"' : ""}>史实背景</button>
        <button data-page="archive" ${state.page === "archive" ? 'aria-current="page"' : ""}>封存卷册</button>
      </nav>
      <button class="setup-link" data-page="setup">设置</button>
    </header>
    <main class="${compact ? "main compact" : "main"}">${content}</main>
    <div class="notice-stack" aria-live="polite">
      ${state.notice ? `<p class="notice">${escapeHtml(state.notice)}</p>` : ""}
      ${state.error ? `<p class="notice error">${escapeHtml(state.error)}</p>` : ""}
    </div>`;
}

function homePage() {
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
        <p class="hero-subtitle">山海关之前</p>
      </div>
      <div class="hero-copy">
        <p>${escapeHtml(state.crisis.checkpoint.summary)}</p>
        <p class="runtime-note">${escapeHtml(runtimeLabel())}</p>
        <div class="hero-actions">
          <button class="primary" data-action="start-watch" ${state.busy || state.active || state.config.setup_required ? "disabled" : ""}>旁观这场危局</button>
          <button class="secondary" data-action="start-takeover" ${state.busy || state.active || state.config.setup_required ? "disabled" : ""}>成为吴三桂</button>
        </div>
        ${
          state.active
            ? `<button class="continue-existing" data-action="open-active">已有一局尚未封存，继续进入</button>`
            : ""
        }
      </div>
    </section>
    <section class="home-corridor" aria-label="危局走廊预览">
      ${corridorMarkup(state.crisis.corridor, [], [], { preview: true })}
    </section>
    <section class="actor-intros">
      <div class="section-heading"><span>三个人</span><h2>各自知道一部分，也各自承担选择</h2></div>
      ${actors}
    </section>
    <section class="boundary-note">
      <span>本局止于</span>
      <p>${escapeHtml(state.crisis.boundary.stop_before)}</p>
      <small>${escapeHtml(state.crisis.boundary.reason)}</small>
    </section>
  `);
}

function corridorMarkup(corridor, actors, messages, options = {}) {
  const actorAt = new Map();
  actors.forEach((actor) => {
    const items = actorAt.get(actor.location) || [];
    items.push(actor);
    actorAt.set(actor.location, items);
  });
  const nodes = corridor
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
        <strong>${escapeHtml(actorNames[message.sender] || message.sender)} → ${escapeHtml(actorNames[message.recipient] || message.recipient)}</strong>
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
  return `<header class="run-header">
    <div>
      <p class="kicker">山海关之前 · 第 ${run.current_tick} 日</p>
      <h1>${escapeHtml(title)}</h1>
      <p>${escapeHtml(lede)}</p>
    </div>
    <div class="run-actions">
      <span class="day-count">${run.current_tick}<small> / ${run.maximum_tick} 日</small></span>
      <button class="quiet" data-action="seal-run">封存这一局</button>
    </div>
  </header>`;
}

function watchPage() {
  if (!state.active) return homePage();
  const lensButtons = [
    ["world", "世界"],
    ["li-zicheng", "李自成"],
    ["wu-sangui", "吴三桂"],
    ["dorgon", "多尔衮"],
  ]
    .map(
      ([id, label]) => `<button data-lens="${id}" ${state.lens === id ? 'aria-current="true"' : ""}>${label}</button>`,
    )
    .join("");
  const body = state.lens === "world" ? worldLens() : actorLens();
  return chrome(`
    ${runHeader("旁观这场危局", "世界继续向前，而每个人只活在自己当时能够知道的部分里。")}
    <div class="lens-switcher" role="tablist" aria-label="切换观察视角">${lensButtons}</div>
    ${body}
    <footer class="continue-bar">
      <div><span>下一个有意义的时刻</span><small>送达、约定到期或主体的新行动</small></div>
      <button class="primary" data-action="continue-run" ${state.busy || (state.active.runtime_mode === "live" && !state.config.hermes_ready) ? "disabled" : ""}>继续</button>
    </footer>
  `);
}

function worldLens() {
  if (!state.world) return loadingBlock();
  const inTransit = state.world.messages.filter((message) => message.status === "in_transit").length;
  return `<section class="lens-sheet">
    <div class="sheet-heading">
      <div><span>世界视野</span><h2>同一条走廊，三处不同的现在</h2></div>
      <p>旁观者可以看见世界事实，但人物的私下打算仍留在各自视角中。</p>
    </div>
    ${corridorMarkup(state.world.corridor, state.world.actors, state.world.messages)}
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
  const actors = [
    {
      id: view.actor.id,
      display_name: view.actor.display_name,
      location: view.location,
    },
  ];
  return `<section class="lens-sheet actor-sheet">
    <div class="actor-title">
      <span>人物视野</span><h2>${escapeHtml(view.actor.display_name)}</h2>
      <p>${escapeHtml(view.role_charter.who)}</p>
    </div>
    ${corridorMarkup(state.crisis.corridor, actors, [], { ownActor: view.actor.id })}
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
      (item) => `<article class="letter-sheet"><span>第 ${item.received_tick} 日抵达 · ${escapeHtml(actorNames[item.sender])}</span><p>${escapeHtml(item.content)}</p></article>`,
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
    .map((item) => `<li><span>第 ${item.tick} 日</span>${escapeHtml(item.summary)}</li>`)
    .join("");
  const outgoing = (view?.outgoing_messages || [])
    .slice(-5)
    .map(
      (item) => `<li><span>${item.status === "delivered" ? `第 ${item.arrival_tick} 日送达` : `预计第 ${item.arrival_tick} 日抵达`} · 致 ${escapeHtml(actorNames[item.recipient])}</span>${escapeHtml(item.content)}</li>`,
    )
    .join("");
  const resolved = (view?.commitments || [])
    .filter((item) => item.status === "FULFILLED")
    .slice(-3)
    .map((item) => `<li><span>已经处理</span>${escapeHtml(item.purpose)}</li>`)
    .join("");
  const actors = [
    {
      id: "wu-sangui",
      display_name: "吴三桂",
      location: view?.location || "shanhaiguan",
    },
  ];
  return chrome(`
    ${runHeader("吴三桂的书案", "你只能看见抵达山海关的消息；北京与辽西仍会在视野之外行动。")}
    <section class="desk-layout">
      <div class="desk-main">
        <div class="desk-corridor">
          <span class="column-label">此刻所见的走廊</span>
          ${corridorMarkup(state.crisis.corridor, actors, [], { ownActor: "wu-sangui" })}
          <p class="corridor-unknown">北京与辽西的人物动向，尚未有可靠消息。</p>
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
        <h2>写下一项决定</h2>
        <p>可以在一句话里同时写信、准备行动并约定何时重新判断。世界只接受你有权做的部分。</p>
        <label for="decision">命令、回信或等待的理由</label>
        <textarea id="decision" rows="8" placeholder="例如：先向关外追问通行与指挥条件，两日后若仍无北京的可靠答复，再重新比较。"></textarea>
        <button class="primary wide" data-action="submit-decision" ${state.busy || (state.active.runtime_mode === "live" && !state.config.hermes_ready) ? "disabled" : ""}>送入这段历史</button>
        <button class="quiet wide" data-action="silence" ${state.busy || (state.active.runtime_mode === "live" && !state.config.hermes_ready) ? "disabled" : ""}>暂不追加命令，继续</button>
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
        <div><small>${item.actor_id ? escapeHtml(actorNames[item.actor_id] || "人物") : "世界"}</small><h3>${escapeHtml(item.title)}</h3>${causes ? `<span class="replay-cause">${causes}</span>` : ""}${item.detail ? `<p>${escapeHtml(item.detail)}</p>` : ""}</div>
      </article>`;
      },
    )
    .join("");
  const actorSwitch = state.replay.actors
    .map((actor) => `<button data-replay-actor="${escapeHtml(actor.id)}" ${state.replayActor === actor.id ? 'aria-current="true"' : ""}>${escapeHtml(actor.display_name)}</button>`)
    .join("");
  const replayTitle =
    state.replay.run.mode === "WATCH" ? "三条人生如何相遇" : "在你看不见的地方";
  return chrome(`
    <header class="replay-header">
      <p class="kicker">回看这一局</p><h1>${replayTitle}</h1>
      <p>封存让你看见：当时的视野，与世界同时发生的事，并不是同一份记录。</p>
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
            ${run.mode !== "LEGACY_V2" ? `<button class="secondary" data-replay-id="${escapeHtml(run.id)}">打开回看</button>` : '<span class="legacy-mark">仅作历史留存</span>'}
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
}

async function loadRunView() {
  if (!state.active) return;
  if (state.active.mode === "WATCH") {
    if (state.lens === "world") {
      state.world = await api(`/api/runs/${state.active.id}/world`);
      state.perspective = null;
    } else {
      state.perspective = await api(`/api/runs/${state.active.id}/perspective/${state.lens}`);
    }
  } else {
    state.perspective = await api(`/api/runs/${state.active.id}/perspective/wu-sangui`);
  }
}

async function loadPageData() {
  if (state.page === "archive") state.archive = (await api("/api/archive")).runs;
  if (state.page === "history") state.history = await api("/api/history");
  if (state.page === "dev" && state.active) state.dev = await api(`/api/dev/runs/${state.active.id}`);
  if (["watch", "desk"].includes(state.page)) await loadRunView();
}

async function runAction(action) {
  state.error = "";
  state.notice = "";
  state.busy = true;
  render();
  try {
    await action();
  } catch (error) {
    state.error = error.name === "AbortError" ? "请求等待过久，请重试。" : error.message;
  } finally {
    state.busy = false;
    render();
  }
}

async function startRun(mode) {
  const result = await api("/api/runs", {
    method: "POST",
    body: JSON.stringify({ mode, live: true }),
  });
  state.active = result.run;
  state.config = await api("/api/config");
  state.lens = "world";
  if (result.start_error) state.notice = result.start_error;
  await loadRunView();
  go(mode === "WATCH" ? "watch" : "desk");
}

async function continueRun() {
  const result = await api(`/api/runs/${state.active.id}/continue`, { method: "POST", body: "{}" });
  state.active = result.run;
  state.notice = result.advanced ? "时间向前走到了下一个有意义的时刻。" : "此刻没有新的触发；可以封存这一局。";
  await loadRunView();
}

async function sealRun() {
  const result = await api(`/api/runs/${state.active.id}/seal`, {
    method: "POST",
    body: JSON.stringify({ reason: "user_exit" }),
  });
  const runId = result.run.id;
  state.active = null;
  state.replay = await api(`/api/runs/${runId}/replay`);
  state.replayLens = state.replay.run.mode === "WATCH" ? "after" : "then";
  state.replayActor = state.replay.run.human_actor || "wu-sangui";
  go("replay");
}

async function submitDecision(silence = false, capturedText = "") {
  const text = silence ? "" : capturedText.trim();
  if (!silence && !text) throw new Error("请写下决定，或选择暂不追加命令。 ");
  const result = await api(`/api/runs/${state.active.id}/decision`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  state.notice = result.silence ? "你选择沉默，世界仍会继续。" : result.summary;
  await continueRun();
}

async function openReplay(runId) {
  state.replay = await api(`/api/runs/${runId}/replay`);
  state.replayLens = state.replay.run.mode === "WATCH" ? "after" : "then";
  state.replayActor = state.replay.run.human_actor || "wu-sangui";
  go("replay");
}

root.addEventListener("click", (event) => {
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
  const action = event.target.closest("[data-action]")?.dataset.action;
  const capturedDecision = document.querySelector("#decision")?.value || "";
  const actions = {
    "go-home": () => go("home"),
    "retry-boot": () => boot(),
    "start-watch": () => runAction(() => startRun("WATCH")),
    "start-takeover": () => runAction(() => startRun("TAKEOVER")),
    "open-active": () => go(state.active.mode === "WATCH" ? "watch" : "desk"),
    "continue-run": () => runAction(continueRun),
    "seal-run": () => runAction(sealRun),
    "submit-decision": () => runAction(() => submitDecision(false, capturedDecision)),
    silence: () => runAction(() => submitDecision(true)),
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

window.addEventListener("hashchange", () => {
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
