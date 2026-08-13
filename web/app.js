import { api } from "./api.js";
import { escapeHtml } from "./components/html.js";
import { route, go, goFollow } from "./router.js";
import { state } from "./state.js";

const root = document.querySelector("#app");

function text(value, fallback = "") {
  return escapeHtml(value ?? fallback);
}

function itemText(item) {
  if (typeof item === "string") return item;
  if (!item || typeof item !== "object") return String(item ?? "");
  return (
    item.content
    || item.observation
    || item.description
    || item.title
    || item.text
    || item.summary
    || item.declaration
    || item.reason
    || item.value?.objective
    || item.value?.content
    || "这一项暂未留下文字说明"
  );
}

function listMarkup(items, className = "folio-list") {
  if (!items?.length) return `<p class="empty-copy">暂时没有新的记录。</p>`;
  return `<ul class="${className}">${items.map((item) => `<li>${text(itemText(item))}</li>`).join("")}</ul>`;
}

function judgmentHistoryMarkup(items) {
  if (!items?.length) return `<p class="empty-copy">这段人生没有留下可回看的判断。</p>`;
  return `<ol class="judgment-history">${items.map((item) => `
    <li class="judgment-entry">
      <div class="judgment-meta"><span>第 ${text(item.tick)} 个时刻</span><strong>${text(item.label)}</strong></div>
      <div class="judgment-copy">
        <p class="judgment-why">${text(item.why_now)}</p>
        <dl class="judgment-fields">
          <div><dt>此前</dt><dd>${text(item.before)}</dd></div>
          <div><dt>这次决定</dt><dd>${text(item.decision)}：${text(item.course)}</dd></div>
        </dl>
        ${item.new_facts?.length ? `<div class="judgment-note"><span>后来知道</span>${listMarkup(item.new_facts, "desk-list")}</div>` : ""}
        ${item.consequences?.length ? `<div class="judgment-note"><span>之后发生</span>${listMarkup(item.consequences, "desk-list")}</div>` : ""}
      </div>
    </li>`).join("")}</ol>`;
}

function chrome(content, { compact = false } = {}) {
  const nav = [
    ["volume", "卷册"],
    ["world", "世界"],
    ["archive", "封存"],
  ];
  return `
    <header class="topbar">
      <button class="brand" data-page="volume" aria-label="返回甲申卷册">
        <span class="brand-seal">甲</span><span>甲申 · 活历史</span>
      </button>
      <nav class="main-nav" aria-label="主要页面">
        ${nav.map(([page, label]) => `<button data-page="${page}" aria-current="${state.page === page ? "page" : "false"}">${label}</button>`).join("")}
      </nav>
    </header>
    <main class="main${compact ? " compact" : ""}">${content}</main>
    ${(state.notice || state.error) ? `<div class="notice-stack" aria-live="polite">${state.notice ? `<p class="notice">${text(state.notice)}</p>` : ""}${state.error ? `<p class="notice error">${text(state.error)}</p>` : ""}</div>` : ""}
  `;
}

function volumeHomePage() {
  const active = state.active?.kind === "VOLUME";
  const volume = state.volume || {};
  return chrome(`
    <section class="volume-hero">
      <div class="hero-mast">
        <p class="kicker">Volume · ${text(volume.native_period || "崇祯十七年")}</p>
        <h1>甲申</h1>
        <p class="hero-subtitle">${text(volume.subtitle || "崇祯十七年")}</p>
      </div>
      <div class="hero-copy">
        <p>几段人生在同一历史中同时向前。你一次只能接过其中一段已经活到这里的人生。</p>
        <p class="runtime-note">世界先行，人生随后；每一次进入，都是把下一步交还给你。</p>
        <div class="hero-actions">
          <button class="primary" data-action="${active ? "continue-volume" : "start-volume"}" ${state.busy ? "disabled" : ""}>${active ? "继续这一卷" : "开始这一卷"}</button>
          ${active ? `<button class="secondary" data-page="world">查看世界</button>` : ""}
        </div>
        ${active ? `<p class="continue-existing">当前卷册已展开至第 ${text(state.active.current_tick)} 个时刻。</p>` : ""}
      </div>
    </section>
    <section class="boundary-note">
      <span>阅读方式</span>
      <p>先看世界，再决定是否进入一段人生。</p>
      <small>你可以整卷不离席，也可以在另一个仍有未决之处时暂时接过别人的下一步。</small>
    </section>
  `);
}

function surfaceMarkup(knot) {
  const surface = knot.surface || {};
  if (surface.kind === "SPATIAL") {
    return `<div class="surface-lines">${(surface.actors || []).map((person) => `<span>${text(person.display_name)} · ${text(person.location || "位置未明")}</span>`).join("")}</div>`;
  }
  const entities = [...(surface.subjects || []), ...(surface.context || [])];
  return `<div class="surface-lines">${entities.map((entity) => `<span><strong>${text(entity.display_name || "相关对象")}</strong> · ${text(entity.state_label || "状态未明")}</span>`).join("")}</div>`;
}

function phaseText(value) {
  return { OPEN: "正在收紧", AFTERMATH: "余波仍在", RESOLUTION_PENDING: "结果将至", SETTLED: "已经留下结果" }[value] || "正在收紧";
}

function archiveKindText(value) {
  return value === "VOLUME" ? "卷册" : "历史记录";
}

function archiveStatusText(value) {
  return { SEALED: "已封存", ACTIVE: "展开中", ARCHIVED: "已归档" }[value] || "已封存";
}

function knotMarkup(knot, index) {
  return `
    <article class="knot-card">
      <div class="folio">${String(index + 1).padStart(2, "0")}</div>
      <div>
        <p class="kicker">${text(phaseText(knot.phase))}</p>
        <h3>${text(knot.title)}</h3>
        <p>${text(knot.subtitle)}</p>
        ${surfaceMarkup(knot)}
      </div>
    </article>
  `;
}

function personMarkup(person) {
  const canEnter = person.available || person.inhabited;
  return `
    <article class="person-card">
      <div>
        <span class="column-label">${person.inhabited ? "当前在席" : canEnter ? "可以接近" : "暂不适合"}</span>
        <h3>${text(person.display_name)}</h3>
        <p>${text(person.location?.display_name || "位置未明")}</p>
        <small>${text((person.availability_reasons || []).join(" · ") || "这段人生尚未进入可见的未决处")}</small>
      </div>
      <button class="${canEnter ? "secondary" : "quiet"}" data-action="follow" data-lifetime-id="${text(person.id)}" ${canEnter ? "" : "disabled"}>${person.inhabited ? "回到书案" : "跟随这段人生"}</button>
    </article>
  `;
}

function worldPage() {
  if (!state.world) return chrome(`<div class="loading-block">正在展开世界……</div>`);
  const world = state.world;
  return chrome(`
    <section class="run-header">
      <div>
        <p class="kicker">World · ${text(world.volume?.native_period || "甲申")}</p>
        <h1>此刻哪里值得我去活？</h1>
        <p>第 ${text(world.tick)} 个时刻 · ${text(world.volume?.subtitle || "崇祯十七年")}</p>
      </div>
      <div class="run-actions"><span class="day-count">${text(world.active_knots?.length || 0)}<small>处收紧</small></span></div>
    </section>
    <section class="world-section">
      <div class="section-heading"><span>正在变得重要</span><h2>历史的高密度之处</h2></div>
      <div class="knot-grid">${(world.active_knots || []).map(knotMarkup).join("") || `<p class="empty-copy">此刻没有需要停留的高密度之处。</p>`}</div>
    </section>
    <section class="world-section">
      <div class="section-heading"><span>可见的人</span><h2>几段仍有下一步的人生</h2></div>
      <div class="people-grid">${(world.people || []).map(personMarkup).join("")}</div>
    </section>
    <section class="world-section public-facts">
      <div class="section-heading"><span>公共事实</span><h2>已经进入世界的东西</h2></div>
      ${listMarkup(world.public_facts)}
    </section>
    <div class="continue-bar">
      <div><span>世界还在向前</span><small>下一次推进只落在已有的真实触发上。</small></div>
      <button class="primary" data-action="continue-world" ${state.busy ? "disabled" : ""}>继续看下去</button>
    </div>
  `);
}

function followPage() {
  if (!state.follow) return chrome(`<div class="loading-block">正在寻找这段人生……</div>`);
  const follow = state.follow;
  const life = follow.lifetime;
  const inhabited = state.active?.inhabited_lifetime_id === life.id;
  return chrome(`
    <section class="actor-title">
      <p class="kicker">Follow · ${text(life.location?.display_name || "位置未明")}</p>
      <h1>${text(life.display_name)}</h1>
      <p>这里只记录外部可见的行动、位置与结果，不替你打开这段人生的内里。</p>
      <div class="hero-actions">
        ${inhabited ? `<button class="primary" data-page="desk">回到书案</button>` : `<button class="primary" data-action="inhabit" data-lifetime-id="${text(life.id)}" ${life.available && !state.busy ? "" : "disabled"}>进入这段人生</button>`}
        <button class="secondary" data-page="world">返回世界</button>
      </div>
    </section>
    <section class="follow-trace">
      <div class="section-heading"><span>外部轨迹</span><h2>这段人生如何走到这里</h2></div>
      <ol class="trace-list">${(follow.trace || []).map((event) => `<li><span>第 ${text(event.tick)} 个时刻</span><div><strong>${text(event.kind)}</strong>${event.declaration ? `<p>${text(event.declaration)}</p>` : ""}</div></li>`).join("") || `<li class="empty-copy">还没有可见轨迹。</li>`}</ol>
    </section>
  `);
}

function deskPage() {
  if (!state.desk) return chrome(`<div class="empty-page inline"><p class="kicker">Life Desk</p><h1>还没有接过一段人生。</h1><button class="secondary" data-page="world">回到世界</button></div>`, { compact: true });
  const desk = state.desk.desk || {};
  const life = state.desk.lifetime || {};
  const whyNow = desk.why_now || {};
  const reconsideration = desk.reconsideration || {};
  return chrome(`
    <section class="run-header">
      <div><p class="kicker">Life Desk · ${text(life.location?.display_name || "位置未明")}</p><h1>${text(life.display_name)}</h1><p>你暂时拥有的是这段人生的下一步，不是这个人的全部。</p></div>
      <div class="run-actions"><button class="secondary" data-action="leave-life" ${state.busy ? "disabled" : ""}>离开这段人生</button></div>
    </section>
    <section class="desk-layout v5-desk">
      <div class="desk-main">
        <div class="desk-surface"><div class="section-heading"><span>此前</span><h2>你准备这样办</h2></div>${listMarkup(desk.current_course || desk.current_plan, "desk-list")}</div>
        <div class="desk-surface"><div class="section-heading"><span>自那以后</span><h2>真正进入你所知的变化</h2></div>${listMarkup(desk.since_last_deliberation || desk.arrivals, "desk-list")}</div>
        ${whyNow.open ? `<div class="known-strip"><span>为什么现在重新问你</span><p>${text(whyNow.text || "现实改变了此前判断的基础。")}</p>${listMarkup(whyNow.facts, "desk-list")}</div>` : ""}
        <div class="desk-surface"><div class="section-heading"><span>不能忽略</span><h2>已经不能当作没发生的事</h2></div>${listMarkup(desk.binding_reality || desk.active_obligations, "desk-list")}</div>
        <div class="known-strip"><span>仍然没有答案</span>${listMarkup(desk.uncertainty, "desk-list")}</div>
      </div>
      <aside class="decision-desk">
        <p class="kicker">下一步</p>
        <h2>${text(reconsideration.prompt || "现在还这样办吗？")}</h2>
        <p>${reconsideration.attention_open ? "现实已经改变了此前判断的基础。" : "此前的判断仍在生效；你也可以主动重新看看。"} 可以留下明确的一步，也可以保持等待。</p>
        <form id="decision-form">
          <textarea id="decision" name="decision" rows="6" placeholder="把你愿意承担的下一步写在这里；如果现在改主意，也可以直接写下新的判断"></textarea>
          <button class="primary wide" type="submit" ${state.busy ? "disabled" : ""}>落下这一笔</button>
        </form>
        <button class="secondary wide" data-action="continue-world" ${state.busy ? "disabled" : ""}>等待世界的下一刻</button>
      </aside>
    </section>
  `, { compact: false });
}

function archivePage() {
  const rows = state.archive || [];
  const detail = state.archiveDetail;
  if (detail) {
    const replay = detail.replay?.public?.items || [];
    const boundary = detail.boundary || {};
    return chrome(`
      <section class="actor-title">
        <p class="kicker">卷册边界 · ${text(detail.volume?.native_period || "甲申")}</p>
        <h1>这一卷已经成为过去。</h1>
        <p>${text(boundary.message || "卷册已经到达结构边界，公共历史与各段人生都被保留下来。")}</p>
        <div class="hero-actions"><button class="secondary" data-action="clear-archive">返回封存卷册</button></div>
      </section>
      <section class="world-section archive-replay">
        <div class="section-heading"><span>公共回看</span><h2>世界留下的轨迹</h2></div>
        <ol class="trace-list">${replay.map((event) => `<li><span>第 ${text(event.tick)} 个时刻</span><div><strong>${text(event.kind)}</strong><p>${text(event.text)}</p></div></li>`).join("") || `<li class="empty-copy">没有可公开回看的事件。</li>`}</ol>
      </section>
      <section class="world-section">
        <div class="section-heading"><span>人生回看</span><h2>从一段人生回看</h2></div>
        <div class="people-grid">${(detail.world?.people || []).map((person) => `<article class="person-card"><div><span class="column-label">${text(person.display_name)}</span><p>${text(person.location?.display_name || "位置未明")}</p></div><button class="secondary" data-action="archive-life" data-lifetime-id="${text(person.id)}">回看这段人生</button></article>`).join("")}</div>
        ${state.selectedReplayLifetime && detail.replay?.lifetime ? `
          <section class="judgment-history-section">
            <div class="section-heading"><span>判断回看</span><h3>${text(detail.replay.lifetime.display_name)} 的判断如何变化</h3></div>
            <p class="history-intro">这里只回看已经落下的判断、后来进入所知的事实，以及它们留下的后果；不展示未落笔的思考。</p>
            ${judgmentHistoryMarkup(detail.replay.lifetime.judgment_history)}
          </section>
          <div class="known-strip"><span>${text(detail.replay.lifetime.display_name)} · 后知事实</span>${listMarkup(detail.replay.lifetime.later_known, "desk-list")}</div>
        ` : ""}
      </section>
    `, { compact: true });
  }
  return chrome(`
    <section class="actor-title">
      <p class="kicker">Archive</p><h1>封存卷册</h1>
      <p>封存只发生在整卷历史到达边界之后。当前卷册仍在展开时，世界与人生都保持可回到的状态。</p>
    </section>
    <section class="archive-list">
      ${rows.length ? rows.map((row) => `<article class="archive-row"><div><span>${text(archiveKindText(row.kind))}</span><h2>${text(row.volume_title || state.volume?.title || "封存卷册")}</h2><p>${text(archiveStatusText(row.status))}</p></div><div><span>时刻</span><p>${text(row.current_tick ?? "—")}</p><button class="secondary" data-action="open-archive" data-worldline-id="${text(row.id)}">打开回看</button></div></article>`).join("") : `<div class="empty-page inline"><p class="empty-copy">当前还没有已经封存的卷册。</p>${state.active ? `<button class="secondary" data-page="world">返回世界</button>` : ""}</div>`}
    </section>
  `, { compact: true });
}

function endingPage() {
  if (state.archiveDetail) {
    return chrome(`<section class="empty-page inline"><p class="kicker">卷册边界</p><h1>这一卷已经走到边界。</h1><p class="empty-copy">${text(state.archiveDetail.boundary?.message || "公共历史与各段人生已经被封存。")}</p><button class="secondary" data-page="archive">打开 Archive</button></section>`, { compact: true });
  }
  return chrome(`
    <section class="empty-page inline"><p class="kicker">卷册边界</p><h1>这一卷仍未走到边界。</h1><p class="empty-copy">局部结果会先留在世界中；整卷封存与后知事实将在卷册真正结束时出现。</p><button class="secondary" data-page="world">返回世界</button></section>
  `, { compact: true });
}

function render() {
  if (!state.volume || !state.config) {
    root.innerHTML = `<div class="boot-state"><span>甲申</span>${state.error ? `<p>卷册暂时打不开</p><small>${text(state.error)}</small><button class="secondary" data-action="retry-boot">重新打开</button>` : `<p>正在打开卷册</p>`}</div>`;
    return;
  }
  const pages = { volume: volumeHomePage, world: worldPage, follow: followPage, desk: deskPage, archive: archivePage, ending: endingPage };
  root.innerHTML = (pages[state.page] || volumeHomePage)();
}

async function loadWorld() {
  if (!state.active?.id || state.active.kind !== "VOLUME") return;
  const [world, lifetimes] = await Promise.all([
    api(`/api/worldlines/${encodeURIComponent(state.active.id)}/world`),
    api(`/api/worldlines/${encodeURIComponent(state.active.id)}/lifetimes`),
  ]);
  state.world = world;
  state.lifetimes = lifetimes;
}

async function loadFollow() {
  if (!state.active?.id || !state.selectedLifetime) return;
  state.follow = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/follow/${encodeURIComponent(state.selectedLifetime)}`);
}

async function loadDesk() {
  if (!state.active?.id || state.active.kind !== "VOLUME") return;
  state.desk = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/desk`);
}

async function loadArchive() {
  state.archive = (await api("/api/worldlines")).worldlines || [];
  if (state.selectedArchive) {
    state.archiveDetail = await api(`/api/worldlines/${encodeURIComponent(state.selectedArchive)}/archive`);
  }
}

async function loadPageData() {
  if (state.page === "world") await loadWorld();
  if (state.page === "follow") await loadFollow();
  if (state.page === "desk") await loadDesk();
  if (state.page === "archive") await loadArchive();
  if (state.page === "ending" && state.selectedArchive) await loadArchive();
}

async function refreshActive() {
  const payload = await api("/api/worldlines/active", { timeoutMs: 15000 });
  state.active = payload.active;
  state.world = payload.world || null;
  state.desk = null;
  if (state.active?.kind === "VOLUME") await loadWorld();
}

function applyWorldline(result) {
  state.active = result.worldline || result.active || state.active;
  state.world = result.world || state.world;
  if (result.lifetimes) state.lifetimes = result.lifetimes;
}

async function startVolume() {
  const result = await api("/api/worldlines", {
    method: "POST",
    body: JSON.stringify({ live: !state.config?.dev }),
  });
  applyWorldline(result);
  state.notice = "这一卷已经展开。先看世界，或接过其中一段人生。";
  go("world");
  await loadPageData();
}

async function continueWorld() {
  if (!state.active?.id) return go("volume");
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/continue`, { method: "POST", body: "{}" });
  applyWorldline(result);
  if (result.pending_moment && result.continue_status === "human_judgment" && state.active.inhabited_lifetime_id) {
    state.notice = "这一刻已经停在你的书案前。";
    go("desk");
    await loadDesk();
  } else {
    state.notice = result.advanced ? "世界已经走到下一个有意义的时刻。" : "此刻没有需要推进的新事件。";
    if (state.page === "desk") await loadDesk();
    else await loadWorld();
  }
}

async function inhabit(lifetimeId) {
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/inhabit`, {
    method: "POST",
    body: JSON.stringify({ lifetime_id: lifetimeId }),
  });
  applyWorldline(result);
  state.selectedLifetime = lifetimeId;
  state.notice = "你接过了这段人生的下一步。";
  go("desk");
  await loadDesk();
}

async function leaveLife() {
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/leave`, { method: "POST", body: "{}" });
  applyWorldline(result);
  state.desk = null;
  state.notice = "你已经离开书案，世界继续向前。";
  go("world");
  await loadWorld();
}

async function submitDecision(value) {
  const payload = value ? { text: value } : { intent: { type: "wait" } };
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/decision`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  applyWorldline(result);
  state.desk = result.desk || state.desk;
  state.notice = value ? "这一笔已经落入当前时刻。" : "你选择等待；这一笔已经落入当前时刻。";
  await loadDesk();
}

async function openArchive(worldlineId) {
  state.selectedArchive = worldlineId;
  state.selectedReplayLifetime = "";
  state.archiveDetail = await api(`/api/worldlines/${encodeURIComponent(worldlineId)}/archive`);
  render();
}

async function openLifetimeReplay(lifetimeId) {
  if (!state.selectedArchive) return;
  state.selectedReplayLifetime = lifetimeId;
  state.archiveDetail = await api(`/api/worldlines/${encodeURIComponent(state.selectedArchive)}/archive?lifetime_id=${encodeURIComponent(lifetimeId)}`);
  render();
}

function clearArchive() {
  state.selectedArchive = "";
  state.selectedReplayLifetime = "";
  state.archiveDetail = null;
  render();
}

async function run(action) {
  if (state.busy) return;
  state.busy = true;
  state.error = "";
  render();
  try {
    await action();
  } catch (error) {
    state.error = error?.name === "AbortError" ? "请求等待过久，请稍后重试。" : (error?.message || "这一页暂时没有回应。 ");
  } finally {
    state.busy = false;
    render();
  }
}

root.addEventListener("click", (event) => {
  const page = event.target.closest("[data-page]")?.dataset.page;
  if (page) return go(page);
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (!action || state.busy) return;
  if (action === "retry-boot") return run(boot);
  if (action === "start-volume") return run(startVolume);
  if (action === "continue-volume") return run(() => { go("world"); return loadPageData(); });
  if (action === "continue-world") return run(continueWorld);
  if (action === "leave-life") return run(leaveLife);
  if (action === "open-archive") return run(() => openArchive(event.target.closest("[data-worldline-id]").dataset.worldlineId));
  if (action === "archive-life") return run(() => openLifetimeReplay(event.target.closest("[data-lifetime-id]").dataset.lifetimeId));
  if (action === "clear-archive") return clearArchive();
  if (action === "follow") {
    state.selectedLifetime = event.target.closest("[data-lifetime-id]").dataset.lifetimeId;
    return run(() => { goFollow(state.selectedLifetime); return loadFollow(); });
  }
  if (action === "inhabit") return run(() => inhabit(event.target.closest("[data-lifetime-id]").dataset.lifetimeId));
});

root.addEventListener("submit", (event) => {
  if (event.target.id !== "decision-form") return;
  event.preventDefault();
  const value = event.target.querySelector("#decision")?.value.trim() || "";
  run(() => submitDecision(value));
});

window.addEventListener("hashchange", () => {
  route();
  run(loadPageData);
});

async function boot() {
  state.error = "";
  render();
  try {
    state.config = await api("/api/config", { timeoutMs: 15000 });
    state.volume = await api("/api/volume", { timeoutMs: 15000 });
    route();
    await refreshActive();
    await loadPageData();
  } catch (error) {
    state.error = error?.name === "AbortError" ? "打开卷册等待过久。" : (error?.message || "卷册暂时打不开。");
  }
  render();
}

route();
boot();
