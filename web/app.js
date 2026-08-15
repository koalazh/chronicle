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
  const payload = item.payload;
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
    || (payload && typeof payload === "object" ? itemText(payload) : "")
    || "一项已知事实。"
  );
}

function listMarkup(items, className = "folio-list") {
  if (!items?.length) return `<p class="empty-copy">暂时没有新的记录。</p>`;
  return `<ul class="${className}">${items.map((item) => `<li>${text(itemText(item))}</li>`).join("")}</ul>`;
}

const CONSEQUENCE_KIND_TEXT = {
  INVESTIGATION: "调查",
  OBSERVATION: "观察",
  REALITY: "现实",
};

function consequenceSource(item) {
  const source = item?.actor?.display_name || item?.actors?.[0]?.display_name || "";
  const invalid = ["none", "null", "undefined"].includes(String(source).trim().toLowerCase());
  const kindValue = item?.kind || item?.type || "之后发生";
  const kind = CONSEQUENCE_KIND_TEXT[kindValue] || kindValue;
  return invalid || source === kind ? "" : source;
}

function consequenceKind(item) {
  const value = item?.kind || item?.type || "之后发生";
  return CONSEQUENCE_KIND_TEXT[value] || value;
}

function consequenceBody(item) {
  const value = itemText(item).trim();
  const source = consequenceSource(item);
  const body = source && value.startsWith(source) ? value.slice(source.length).trim() : value;
  if (item?.type === "INVESTIGATION" && body === "完成了一项调查。") {
    return "调查已经完成；具体所见见下一条观察。";
  }
  return body;
}

function consequenceMarkup(items) {
  if (!items?.length) return "";
  return `<ul class="consequence-list">${items.map((item) => `
    <li><div class="consequence-heading">${consequenceSource(item) ? `<span class="consequence-source">${text(consequenceSource(item))}</span>` : ""}<span class="consequence-kind">${text(consequenceKind(item))}</span></div><p class="consequence-body">${text(consequenceBody(item))}</p></li>
  `).join("")}</ul>`;
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
        ${item.consequences?.length ? `<div class="judgment-note"><span>之后发生</span>${consequenceMarkup(item.consequences)}</div>` : ""}
      </div>
    </li>`).join("")}</ol>`;
}

const ACTIVITY_COPY = {
  start: ["正在展开这一卷", "先把第一幅世界铺到你面前。"],
  continue: ["正在推进世界", "正在处理已经发生的下一处触发；不要重复点击。"],
  decision: ["正在保存这次判断", "正在把它交给当前卷册确认；不要重复提交。"],
  reconsider: ["正在重新打开这份判断", "正在把新的现实带回书案。"],
  leave: ["正在把这段人生交还给世界", "已经发生的事会保留，世界随后继续向前。"],
  inhabit: ["正在把这一段人生交到你面前", "正在把当前需要判断的下一步交到你面前。"],
  follow: ["正在寻找这段人生", "正在打开它可以被看见的公开轨迹。"],
  archive: ["正在打开过去", "正在整理可以公开回看的历史。"],
};

function activityMarkup() {
  const activity = state.activity;
  if (!activity) return "";
  const copy = ACTIVITY_COPY[activity.kind] || ["正在展开这一页", "请稍候，当前操作还没有得到确定回音。"];
  const reconciling = activity.phase === "reconciling";
  const action = reconciling
    ? `<button class="quiet activity-action" data-action="reconcile-activity" ${activity.reconciling ? "disabled" : ""}>${activity.reconciling ? "正在核对" : "重新核对当前卷册"}</button>`
    : `<button class="quiet activity-action" data-action="cancel-activity">停止等待并核对</button>`;
  return `<section class="activity-banner ${reconciling ? "reconciling" : ""}" role="status" aria-live="polite" aria-busy="true">
    <span class="activity-stamp" aria-hidden="true">卷</span>
    <div class="activity-copy"><span class="column-label">正在进行</span><strong>${text(reconciling ? "正在确认这次操作" : copy[0])}</strong><p>${text(activity.pendingText || (reconciling ? "正在自动核对当前卷册；不要重复提交。" : copy[1]))}</p></div>
    ${action}
  </section>`;
}

function noticeMarkup() {
  if (!state.notice && !state.error) return "";
  return `<div class="notice-stack" aria-live="polite">${state.notice ? `<p class="notice">${text(state.notice)}</p>` : ""}${state.error ? `<p class="notice error">${text(state.error)}</p>` : ""}</div>`;
}

function chrome(content, { compact = false } = {}) {
  const inLife = Boolean(state.active?.inhabited_lifetime_id);
  const worldOpen = state.active?.status === "ACTIVE" && !inLife;
  const nav = [
    ...(worldOpen ? [["world", "世界"]] : inLife ? [["desk", "当前人物"]] : []),
    ["archive", "过去"],
  ];
  return `
    <header class="topbar">
      <button class="brand" data-page="volume" aria-label="返回甲申卷册">
        <span class="brand-seal">甲</span><span>甲申</span>
      </button>
      <nav class="main-nav" aria-label="主要页面">
        ${nav.map(([page, label]) => `<button data-page="${page}" aria-current="${state.page === page ? "page" : "false"}">${label}</button>`).join("")}
      </nav>
    </header>
    <main class="main${compact ? " compact" : ""}">${activityMarkup()}${noticeMarkup()}${content}</main>
  `;
}

function volumeHomePage() {
  const active = state.active?.kind === "VOLUME" && state.active.status === "ACTIVE";
  const volume = state.volume || {};
  return chrome(`
    <section class="volume-hero">
      <div class="hero-mast">
        <p class="kicker">甲申 · ${text(volume.native_period || "崇祯十七年")}</p>
        <h1>甲申</h1>
        <p class="hero-subtitle">${text(volume.subtitle || "崇祯十七年")}</p>
      </div>
      <div class="hero-copy">
        <p>几段人生在同一历史中同时向前。你一次只能接过其中一段已经活到这里的人生。</p>
        <p class="runtime-note">世界先行，人生随后；每一次进入，都是把下一步交还给你。</p>
        <div class="hero-actions">
          <button class="primary" data-action="${active ? "continue-volume" : "start-volume"}" ${state.busy ? "disabled" : ""}>${active ? "继续这一卷" : "开始这一卷"}</button>
          ${active ? `<button class="secondary" data-page="${state.active.inhabited_lifetime_id ? "desk" : "world"}">${state.active.inhabited_lifetime_id ? "回到书案" : "查看世界"}</button>` : ""}
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

function archiveKindText(value) {
  return value === "VOLUME" ? "卷册" : "历史记录";
}

function archiveStatusText(value) {
  return { SEALED: "已经成为过去", ACTIVE: "展开中", ARCHIVED: "已经成为过去" }[value] || "已经成为过去";
}

function questionMarkup(question) {
  return `
    <article class="question-entry">
      <div>
        <p class="kicker">尚未定下</p>
        <h3>${text(question.title)}</h3>
        <p>${text(question.subtitle)}</p>
        ${surfaceMarkup(question)}
        <div class="people-inline">${(question.participants || []).map(personMarkup).join("")}</div>
      </div>
    </article>
  `;
}

function realityMarkup(items) {
  if (!items?.length) return `<p class="empty-copy">眼前还没有新的现实需要记下。</p>`;
  return `<ul class="folio-list">${items.map((item) => `<li><strong>${text(item.title)}</strong> · ${text(item.text)}</li>`).join("")}</ul>`;
}

function personMarkup(person) {
  const canEnter = person.available || person.inhabited;
  return `
    <article class="person-entry">
      <div>
        <span class="column-label">${person.inhabited ? "当前在席" : canEnter ? "可以接近" : "暂不适合"}</span>
        <strong>${text(person.display_name)}</strong>
        <p>${text(person.location?.display_name || "位置未明")}</p>
        <small>${text((person.availability_reasons || []).join(" · ") || "这段人生尚未进入可见的未决处")}</small>
      </div>
      <button class="${canEnter ? "secondary" : "quiet"}" data-action="follow" data-lifetime-id="${text(person.id)}" ${canEnter ? "" : "disabled"}>${person.inhabited ? "回到这一生" : "走近"}</button>
    </article>
  `;
}

function traceBody(event) {
  const value = String(event.text || event.declaration || "").trim();
  const sourceValue = event.actor?.display_name;
  const source = ["none", "null", "undefined"].includes(String(sourceValue).trim().toLowerCase())
    ? ""
    : sourceValue;
  return source && value.startsWith(source) ? value.slice(source.length).trim() : value;
}

function traceItemMarkup(event) {
  const sourceValue = event.actor?.display_name;
  const kind = event.kind || event.type || "之后发生";
  const source = ["none", "null", "undefined"].includes(String(sourceValue).trim().toLowerCase()) || sourceValue === kind
    ? ""
    : sourceValue;
  return `<li><span>第 ${text(event.tick)} 个时刻</span><div><div class="trace-heading"><strong>${text(kind)}</strong>${source ? `<span class="trace-source">${text(source)}</span>` : ""}</div><p>${text(traceBody(event))}</p></div></li>`;
}

function corridorPersonMarkup(person, publicPerson) {
  const source = publicPerson || person;
  const canEnter = source.available || source.inhabited;
  return `
    <article class="person-entry corridor-person">
      <div>
        <span class="column-label">${text(person.state_label || "判断尚未落笔")}</span>
        <strong>${text(person.display_name)}</strong>
        <p>${text(person.location?.display_name || "位置未明")}</p>
      </div>
      <button class="${canEnter ? "secondary" : "quiet"}" data-action="follow" data-lifetime-id="${text(person.id)}" ${canEnter ? "" : "disabled"}>${source.inhabited ? "回到这一生" : "走近"}</button>
    </article>
  `;
}

function experienceMarkup(items) {
  if (!items?.length) return `<p class="empty-copy">目前还没有一段过去要求你重新考虑。</p>`;
  return `<ul class="experience-list">${items.map((item) => `
    <li><strong>${text(item.text)}</strong>${item.basis ? `<p><span>因为</span>${text(item.basis)}</p>` : ""}${item.implication ? `<p><span>以后</span>${text(item.implication)}</p>` : ""}</li>
  `).join("")}</ul>`;
}

function corridorMarkup(corridor, publicPeople) {
  const locations = corridor.locations || [];
  const people = corridor.people || [];
  const publicById = Object.fromEntries(publicPeople.map((person) => [person.id, person]));
  return `
    <div class="corridor-track" aria-label="北京到山海关再到辽西的走廊">
      ${locations.map((location, index) => `<span class="corridor-stop"><strong>${text(location.display_name)}</strong>${index < locations.length - 1 ? `<i aria-hidden="true">→</i>` : ""}</span>`).join("")}
    </div>
    <div class="people-inline corridor-people">${people.map((person) => corridorPersonMarkup(person, publicById[person.id])).join("")}</div>
    ${corridor.transit?.length ? `<div class="transit-list">${corridor.transit.map((message) => `<p><strong>${text(message.text || "一封消息正在途中")}</strong><span>${text(message.from?.display_name)} → ${text(message.to?.display_name)}</span><small>还有 ${text(message.days_remaining)} 日抵达</small></p>`).join("")}</div>` : `<p class="empty-copy transit-empty">此刻没有消息停在路上。</p>`}
  `;
}

function recentEventsMarkup(items) {
  if (!items?.length) return `<p class="empty-copy">这一卷刚刚展开，变化还没有留下公共记录。</p>`;
  return `<ol class="trace-list recent-events">${items.map(traceItemMarkup).join("")}</ol>`;
}

function worldPage() {
  if (!state.world) return chrome(`<div class="loading-block">正在展开世界……</div>`);
  const world = state.world;
  const corridor = world.corridor || {};
  const publicPeople = (world.open_questions || []).flatMap((question) => question.participants || []);
  const reality = world.present_reality || [];
  const continuationStatus = world.continuation?.status || state.lastContinueStatus || "";
  const agentFailed = continuationStatus === "agent_failed";
  const stalled = continuationStatus === "no_future_trigger" || agentFailed;
  const worldSections = [
    `
      <section class="world-section">
        <div class="section-heading"><span>现实 · 第 ${text(world.tick)} 个时刻</span><h2>北京 → 山海关 → 辽西</h2></div>
        <p class="world-lede">三段人生共享同一条现实走廊；消息会在路上，判断不会替彼此发生。</p>
        ${corridorMarkup(corridor, publicPeople)}
      </section>`,
    `
      <section class="world-section">
        <div class="section-heading"><span>最近发生</span><h2>世界如何走到这里</h2></div>
        ${recentEventsMarkup(corridor.recent_events)}
      </section>`,
    reality.length ? `
      <section class="world-section">
        <div class="section-heading"><span>已经成为现实</span><h2>世界留下了什么</h2></div>
        ${realityMarkup(reality)}
      </section>` : "",
  ].join("");
  return chrome(`
    <section class="run-header">
      <div>
        <p class="kicker">甲申 · ${text(world.volume?.native_period || "崇祯十七年")}</p>
        <h1>山海关一线正在向前</h1>
        <p>第 ${text(world.tick)} 个时刻 · ${text(world.volume?.subtitle || "崇祯十七年")}</p>
      </div>
    </section>
    ${worldSections || `<p class="empty-copy world-empty">眼前没有新的事情需要你介入。</p>`}
    <div class="continue-bar${stalled ? " paused" : ""}">
      <div><span>${agentFailed ? "这一处回应没有形成判断" : stalled ? "世界暂时停在这里" : "让世界继续"}</span><small>${agentFailed ? "现实没有被改写。走近这段人生，接过下一步；也可以重新检查。" : stalled ? "当前没有下一处已经发生的触发。走近一段人生，在书案主动定一个方向。" : "下一次推进只落在已经存在的真实触发上。"}</small></div>
      ${stalled ? `<div class="continue-actions"><button class="secondary" data-action="focus-people">走近一段人生</button><button class="quiet" data-action="continue-world" ${state.busy ? "disabled" : ""}>重新检查</button></div>` : `<button class="primary" data-action="continue-world" ${state.busy ? "disabled" : ""}>让世界继续</button>`}
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
      <p class="kicker">这一生 · ${text(life.location?.display_name || "位置未明")}</p>
      <h1>${text(life.display_name)}</h1>
      <p>先看这段人生如何走到这里；真正需要判断时，再接过它的下一步。</p>
      <div class="hero-actions">
        ${inhabited ? `<button class="primary" data-page="desk">回到书案</button>` : `<button class="primary" data-action="inhabit" data-lifetime-id="${text(life.id)}" ${life.available && !state.busy ? "" : "disabled"}>接过这一次判断</button>`}
        <button class="secondary" data-page="${inhabited ? "desk" : "world"}">${inhabited ? "回到书案" : "返回世界"}</button>
      </div>
    </section>
    <section class="follow-trace">
      <div class="section-heading"><span>公开轨迹</span><h2>这段人生如何走到这里</h2></div>
      <ol class="trace-list">${(follow.trace || []).map(traceItemMarkup).join("") || `<li class="empty-copy">还没有可见轨迹。</li>`}</ol>
    </section>
  `);
}

function deskPage() {
  if (!state.desk) return chrome(`<div class="empty-page inline"><p class="kicker">这一生</p><h1>还没有接过一段人生。</h1><button class="secondary" data-page="world">回到世界</button></div>`, { compact: true });
  const desk = state.desk.desk || {};
  const life = state.desk.lifetime || {};
  const whyNow = desk.why_now || {};
  const reconsideration = desk.reconsideration || {};
  const decisionState = desk.decision_state || "QUIET_NO_COURSE";
  const agentFailed = decisionState === "AGENT_FAILED";
  const awaitingConfirmation = decisionState === "AWAITING_CONFIRMATION";
  const hasCourse = Boolean(desk.current_course?.length);
  const voluntaryReconsideration = Boolean(reconsideration.voluntary && hasCourse);
  const needsJudgment = decisionState === "NEEDS_FIRST_JUDGMENT" || decisionState === "NEEDS_RECONSIDERATION";
  const firstJudgment = decisionState === "NEEDS_FIRST_JUDGMENT";
  const deskSurfaces = [
    desk.known?.length ? `<div class="desk-surface"><div class="section-heading"><span>我现在知道</span><h2>已经抵达这段人生的现实</h2></div>${listMarkup(desk.known, "desk-list")}</div>` : "",
    desk.current_course?.length ? `<div class="desk-surface"><div class="section-heading"><span>我此前打算</span><h2>仍在生效的方向</h2></div>${listMarkup(desk.current_course, "desk-list")}</div>` : "",
    desk.waiting_for?.length ? `<div class="desk-surface"><div class="section-heading"><span>我正在等</span><h2>还没有抵达的事</h2></div>${listMarkup(desk.waiting_for, "desk-list")}</div>` : "",
    desk.experiences?.length ? `<div class="desk-surface"><div class="section-heading"><span>哪些过去仍影响我</span><h2>留下来的几段经历</h2></div>${experienceMarkup(desk.experiences)}</div>` : "",
  ].join("");
  const decisionCopy = firstJudgment
    ? "这一次还没有形成要继续执行的方向。"
    : agentFailed
      ? "你的判断已经保留，但另一处回应没有形成可执行判断；世界没有继续推进。"
    : awaitingConfirmation
      ? "上一笔判断已经留在当前时刻，正在等世界把它确认。"
    : decisionState === "NEEDS_RECONSIDERATION"
      ? (voluntaryReconsideration ? "你主动重新考虑了这份判断。" : "现实已经改变了此前判断的基础。")
      : decisionState === "COURSE_IN_FORCE"
        ? "这个判断仍在生效。"
        : "此刻还没有事情要求你落笔。";
  const judgmentForm = agentFailed ? `
        <div class="decision-pending decision-failed" role="status">
          <p>你的判断已经保留，不需要重新填写。重新检查只会重试没有形成结果的那一处；成功后世界才会继续。</p>
          <button class="primary wide" data-action="retry-decision" ${state.busy ? "disabled" : ""}>重新检查当前卷册</button>
        </div>
  ` : awaitingConfirmation ? `
        <div class="decision-pending" role="status">
          <p>这次判断已经收到。世界还没有完成核对，请继续确认；不需要重新填写。</p>
          <button class="primary wide" data-action="retry-decision" ${state.busy ? "disabled" : ""}>继续确认这次判断</button>
        </div>
  ` : needsJudgment ? `
        <form id="decision-form">
          <label class="draft-label" for="decision">这次判断</label>
          <textarea id="decision" name="decision" rows="6" placeholder="写下你愿意承担的下一步；如果现在改主意，也可以直接写下新的判断">${text(state.decisionValue ?? "")}</textarea>
          <div class="decision-actions">
            <button class="primary wide" type="submit" data-judgment-action="CHANGE" ${state.busy ? "disabled" : ""}>${firstJudgment ? "留下这个判断" : "改主意"}</button>
            ${firstJudgment ? `<button class="secondary wide" type="submit" data-judgment-action="WAIT" ${state.busy ? "disabled" : ""}>暂时不定</button>` : `<button class="secondary wide" type="submit" data-judgment-action="KEEP" ${state.busy ? "disabled" : ""}>仍照这样办</button>`}
          </div>
        </form>
        <button class="secondary wide" data-action="leave-life" ${state.busy ? "disabled" : ""}>让他自己判断</button>
  ` : decisionState === "COURSE_IN_FORCE" ? `
        <button class="primary wide" data-action="continue-world" ${state.busy ? "disabled" : ""}>让时间继续</button>
        <button class="secondary wide" data-action="reconsider" ${state.busy || !reconsideration.available ? "disabled" : ""}>重新考虑</button>
        <button class="secondary wide" data-action="leave-life" ${state.busy ? "disabled" : ""}>交还给世界</button>
  ` : `
        <button class="primary wide" data-action="continue-world" ${state.busy ? "disabled" : ""}>让时间继续</button>
        <button class="secondary wide" data-action="reconsider" ${state.busy || !reconsideration.available ? "disabled" : ""}>主动定一个方向</button>
        <button class="secondary wide" data-action="leave-life" ${state.busy ? "disabled" : ""}>交还给世界</button>
  `;
  return chrome(`
    <section class="run-header">
      <div><p class="kicker">这一生 · ${text(life.location?.display_name || "位置未明")}</p><h1>${text(life.display_name)}</h1><p>你接过的是这段人生的下一步，不是这个人的全部。</p></div>
    </section>
    <section class="desk-layout">
      <div class="desk-main">
        ${deskSurfaces}
        ${whyNow.open ? `<div class="known-strip"><span>现实已经改变</span><p>${text(whyNow.text || "新的现实已经改变此前判断的基础。")}</p>${listMarkup(whyNow.facts, "desk-list")}</div>` : ""}
      </div>
      <aside class="decision-desk">
        <p class="kicker">下一步</p>
        <h2>${text(reconsideration.prompt || "此刻还没有事情要求你落笔。")}</h2>
        <p>${text(decisionCopy)}</p>
        ${judgmentForm}
      </aside>
    </section>
  `, { compact: false });
}

function archivePage() {
  const rows = state.archive || [];
  const detail = state.archiveDetail;
  if (detail) {
    const history = detail.history || [];
    const ending = detail.ending || {};
    const selectedLife = detail.selected_life;
    const selectedPerson = (detail.lives || []).find((person) => person.id === state.selectedReplayLifetime) || {};
    const replayPeople = (detail.lives || []).map((person) => {
      const selected = state.selectedReplayLifetime === person.id;
      return `<article class="person-entry archive-person${selected ? " selected" : ""}"><div><strong>${text(person.display_name)}</strong><p>${text(person.location?.display_name || "位置未明")}</p></div><button class="secondary" data-action="archive-life" data-lifetime-id="${text(person.id)}" aria-pressed="${selected}">${selected ? "正在回看" : "回看这段人生"}</button></article>`;
    }).join("");
    const replaySelection = state.selectedReplayLifetime && selectedLife ? `
      <div class="replay-selection">
        <div class="replay-context"><span>当前选择</span><strong>${text(selectedLife.display_name)} · ${text(selectedPerson.location?.display_name || "位置未明")}</strong></div>
        <div class="replay-heading"><span>判断回看</span><h3>${text(selectedLife.display_name)}的判断如何变化</h3></div>
        <p class="history-intro">下面只看已经落笔的判断、后来进入所知的事实，以及它们留下的后果。</p>
        ${judgmentHistoryMarkup(selectedLife.judgment_history)}
        ${selectedLife.later_known?.length ? `<div class="known-strip replay-later-known"><span>后来进入所知</span>${listMarkup(selectedLife.later_known, "desk-list")}</div>` : ""}
      </div>
    ` : "";
    return chrome(`
      <section class="actor-title">
        <p class="kicker">过去 · ${text(detail.volume?.native_period || "甲申")}</p>
        <h1>这一卷最后成了什么？</h1>
        <p>${text(ending.message || "卷册已经到达结构边界，公共历史与各段人生都被保留下来。")}</p>
        <div class="hero-actions"><button class="secondary" data-action="clear-archive">返回过去</button></div>
      </section>
      ${detail.final_reality?.length ? `<section class="world-section archive-reality">
        <div class="section-heading"><span>最后成为现实</span><h2>这一卷最后留下了什么</h2></div>
        ${realityMarkup(detail.final_reality)}
      </section>` : ""}
      <section class="world-section archive-replay">
        <div class="section-heading"><span>历史如何走到这里</span><h2>留下的几次变化</h2></div>
        ${history.map((chapter) => `<section class="archive-chapter"><h3>${text(chapter.title)}</h3><ol class="trace-list">${(chapter.beats || []).map(traceItemMarkup).join("")}</ol></section>`).join("") || `<p class="empty-copy">没有可公开回看的历史。</p>`}
      </section>
      <section class="world-section replay-workspace">
        <div class="section-heading"><span>人生回看</span><h2>先选一段人生</h2></div>
        <p class="section-intro">选定之后，下面会展开这段人生已经落下的判断，以及后来发生的变化。</p>
        <div class="people-inline archive-people">${replayPeople}</div>
        ${replaySelection}
      </section>
    `, { compact: true });
  }
  return chrome(`
    <section class="actor-title">
      <p class="kicker">过去</p><h1>已经成为过去的卷册</h1>
      <p>只有整卷历史走到边界，公共现实与各段人生才会在这里留下可回看的过去。</p>
    </section>
    <section class="archive-list">
      ${rows.length ? rows.map((row) => `<article class="archive-row"><div><span>${text(archiveKindText(row.kind))}</span><h2>${text(row.volume_title || state.volume?.title || "甲申")}</h2><p>${text(archiveStatusText(row.status))}</p></div><div><span>时刻</span><p>${text(row.current_tick ?? "—")}</p><button class="secondary" data-action="open-archive" data-worldline-id="${text(row.id)}">打开回看</button></div></article>`).join("") : `<div class="empty-page inline"><p class="empty-copy">当前还没有已经成为过去的卷册。</p>${state.active ? `<button class="secondary" data-page="${state.active.inhabited_lifetime_id ? "desk" : "world"}">${state.active.inhabited_lifetime_id ? "回到这一生" : "返回世界"}</button>` : ""}</div>`}
    </section>
  `, { compact: true });
}

function render() {
  if (!state.volume || !state.config) {
    root.innerHTML = `<div class="boot-state"><span>甲申</span>${state.error ? `<p>卷册暂时打不开</p><small>${text(state.error)}</small><button class="secondary" data-action="retry-boot">重新打开</button>` : `<p>正在打开卷册</p>`}</div>`;
    return;
  }
  const pages = { volume: volumeHomePage, world: worldPage, follow: followPage, desk: deskPage, archive: archivePage };
  root.innerHTML = (pages[state.page] || volumeHomePage)();
}

async function loadWorld() {
  if (!state.active?.id || state.active.kind !== "VOLUME") return;
  if (state.active.inhabited_lifetime_id) {
    state.page = "desk";
    return loadDesk();
  }
  if (state.active.status !== "ACTIVE") {
    state.page = "archive";
    return loadArchive();
  }
  state.world = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/world`);
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
}

async function refreshActive() {
  const payload = await api("/api/worldlines/active", { timeoutMs: 15000 });
  state.active = payload.active;
  state.world = payload.world || null;
  state.desk = null;
  if (state.active?.inhabited_lifetime_id && state.page === "world") {
    state.page = "desk";
  }
  if (state.active?.kind === "VOLUME" && !state.active.inhabited_lifetime_id) await loadWorld();
}

function applyWorldline(result) {
  state.active = result.worldline || result.active || state.active;
  state.world = result.world || state.world;
}

function continueNotice(result) {
  const ticks = Number(result.advanced_ticks || 0);
  if (result.continue_status === "agent_retry") {
    return "这一刻还没有完成回应；现实没有被改写。可以再试一次，也可以接过其中一段人生。";
  }
  if (result.continue_status === "agent_failed") {
    return "这一处回应没有形成有效判断；现实没有被改写。可以重新检查这一处，也可以接过其中一段人生。";
  }
  if (result.continue_status === "no_future_trigger") {
    return ticks > 0
      ? `世界已经向前走了 ${ticks} 个时刻；眼下没有下一处已经发生的触发。走近一段人生，在书案主动定一个方向。`
      : "世界暂时没有下一处已经发生的触发。不是页面卡住；走近一段人生，在书案主动定一个方向。";
  }
  if (result.continue_status === "safety_cap") {
    return `世界已经向前走了 ${ticks || 1} 个时刻，先停在这里整理这一段变化。`;
  }
  if (result.continue_status === "knot_boundary") {
    return ticks > 0
      ? `世界已经向前走了 ${ticks} 个时刻，停在一处仍需被看见的未决处。`
      : "世界停在一处仍需被看见的未决处。";
  }
  return result.advanced ? "世界已经走到下一个有意义的时刻。" : "此刻没有需要推进的新事件。";
}

async function startVolume() {
  const result = await api("/api/worldlines", {
    method: "POST",
    body: JSON.stringify({ live: !state.config?.dev }),
  });
  applyWorldline(result);
  state.lastContinueStatus = "";
  state.lastContinueAdvancedTicks = 0;
  state.notice = "这一卷已经展开。先看世界，或接过其中一段人生。";
  go("world");
  await loadPageData();
}

async function continueWorld() {
  if (!state.active?.id) return go("volume");
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/continue`, { method: "POST", body: "{}" });
  applyWorldline(result);
  state.lastContinueStatus = result.continue_status || "";
  state.lastContinueAdvancedTicks = Number(result.advanced_ticks || 0);
  if (result.worldline?.status === "SEALED") {
    state.selectedArchive = result.worldline.id;
    state.notice = "这一卷已经走到边界。历史从这里进入过去。";
    go("archive");
    state.page = "archive";
    await loadArchive();
    return;
  }
  if (result.pending_moment && result.continue_status === "human_judgment" && state.active.inhabited_lifetime_id) {
    state.notice = "这一刻已经停在你的书案前。";
    go("desk");
    state.page = "desk";
    await loadDesk();
  } else {
    state.notice = continueNotice(result);
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
  state.lastContinueStatus = "";
  state.lastContinueAdvancedTicks = 0;
  state.selectedLifetime = lifetimeId;
  state.notice = "你接过了这段人生的下一步。";
  go("desk");
  await loadDesk();
}

async function leaveLife() {
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/leave`, { method: "POST", body: "{}" });
  applyWorldline(result);
  state.lastContinueStatus = "";
  state.lastContinueAdvancedTicks = 0;
  state.desk = null;
  state.notice = "你已经离开书案，世界继续向前。";
  go("world");
  await loadWorld();
}

async function submitDecision(action, value) {
  const payload = { action, text: value };
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/decision`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  applyWorldline(result);
  state.lastContinueStatus = "";
  state.lastContinueAdvancedTicks = 0;
  state.desk = result.desk || state.desk;
  state.decisionValue = null;
  state.notice = action === "WAIT" ? "你选择暂时不定；这一笔已经落入当前时刻。" : "这一笔已经落入当前时刻。";
  await loadDesk();
}

async function retryDecision() {
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/decision/retry`, {
    method: "POST",
    body: "{}",
  });
  applyWorldline(result);
  state.lastContinueStatus = "";
  state.lastContinueAdvancedTicks = 0;
  const decisionState = result.desk?.desk?.decision_state;
  state.notice = decisionState === "AGENT_FAILED"
    ? "你的判断已经保留，但另一处回应仍未形成有效判断；可以再次重新检查。"
    : decisionState === "AWAITING_CONFIRMATION"
      ? "上一笔判断已经留在当前时刻，世界尚未确认；可以继续确认这次判断。"
      : "上一笔判断已经完成核对。";
  await loadDesk();
}

async function reconsider() {
  const result = await api(`/api/worldlines/${encodeURIComponent(state.active.id)}/reconsider`, {
    method: "POST",
    body: "{}",
  });
  applyWorldline(result);
  state.lastContinueStatus = "";
  state.lastContinueAdvancedTicks = 0;
  state.desk = result.desk || state.desk;
  state.notice = "你主动重新考虑了这份判断。";
  go("desk");
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

function unknownRequest(error) {
  return error?.name === "AbortError" || !error?.status || error.status >= 500;
}

function scrollToActivity() {
  if (typeof window !== "undefined" && typeof window.scrollTo === "function") {
    window.scrollTo({ top: 0, behavior: "auto" });
  }
}

function cancelActivity() {
  const activity = state.activity;
  if (!activity) return;
  activity.phase = "reconciling";
  activity.pendingText = "已停止等待，正在自动核对当前卷册；这次请求可能已经留下了变化。";
  if (activity.controller) {
    activity.controller.abort();
    activity.controller = null;
  }
  render();
  scrollToActivity();
  void reconcileActivity();
}

async function reconcileActivity() {
  if (!state.activity || state.activity.reconciling) return;
  state.activity.phase = "reconciling";
  state.activity.reconciling = true;
  state.activity.pendingText = "正在自动核对当前卷册，请以确认后的页面为准。";
  state.error = "";
  state.busy = true;
  render();
  scrollToActivity();
  try {
    await refreshActive();
    if (state.active?.status === "SEALED") {
      state.selectedArchive = state.active.id;
      state.page = "archive";
    } else if (!state.active) {
      state.page = "volume";
    } else {
      route();
    }
    await loadPageData();
    const decisionState = state.desk?.desk?.decision_state;
    state.notice = decisionState === "AGENT_FAILED"
      ? "你的判断已经保留，但另一处回应没有形成有效判断；可以重新检查当前卷册。"
      : decisionState === "AWAITING_CONFIRMATION"
        ? "上一笔判断已经留在当前时刻，世界尚未确认；可以继续确认这次判断。"
        : "这次操作已经完成核对；当前页面已按最新状态恢复。";
    state.activity = null;
  } catch (error) {
    state.activity.reconciling = false;
    state.error = error?.name === "AbortError" ? "核对当前卷册等待过久，请稍后再试。" : (error?.message || "当前卷册暂时无法核对。 ");
  } finally {
    state.busy = Boolean(state.activity);
    render();
  }
}

async function run(action, activity = null) {
  if (state.busy) return;
  state.busy = true;
  state.error = "";
  state.activity = activity ? { ...activity, phase: "running", pendingText: "" } : null;
  render();
  if (state.activity) scrollToActivity();
  let keepActivity = false;
  let reconcileAfterRun = false;
  try {
    await action();
  } catch (error) {
    if (state.activity && unknownRequest(error)) {
      state.activity.phase = "reconciling";
      state.activity.pendingText = "请求没有直接返回结果，正在自动核对当前卷册；不要重复提交。";
      keepActivity = true;
      reconcileAfterRun = true;
      state.error = "";
    } else {
      state.error = error?.name === "AbortError" ? "请求等待过久，请稍后重试。" : (error?.message || "这一页暂时没有回应。 ");
    }
  } finally {
    if (!keepActivity) state.activity = null;
    state.busy = false;
    if (state.activity) state.busy = true;
    render();
    if (state.activity) scrollToActivity();
    if (reconcileAfterRun) void reconcileActivity();
  }
}

root.addEventListener("click", (event) => {
  const page = event.target.closest("[data-page]")?.dataset.page;
  if (page) return go(page);
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (!action) return;
  if (action === "cancel-activity") return cancelActivity();
  if (action === "reconcile-activity") return void reconcileActivity();
  if (action === "focus-people") {
    document.querySelector(".people-inline")?.scrollIntoView({ behavior: "smooth", block: "center" });
    return;
  }
  if (state.busy) return;
  if (action === "retry-boot") return run(boot);
  if (action === "start-volume") return run(startVolume, { kind: "start" });
  if (action === "continue-volume") return run(() => { go("world"); return loadPageData(); }, { kind: "continue" });
  if (action === "continue-world") return run(continueWorld, { kind: "continue" });
  if (action === "leave-life") return run(leaveLife, { kind: "leave" });
  if (action === "reconsider") return run(reconsider, { kind: "reconsider" });
  if (action === "retry-decision") return run(retryDecision, { kind: "decision" });
  if (action === "open-archive") return run(() => openArchive(event.target.closest("[data-worldline-id]").dataset.worldlineId), { kind: "archive" });
  if (action === "archive-life") return run(() => openLifetimeReplay(event.target.closest("[data-lifetime-id]").dataset.lifetimeId), { kind: "archive" });
  if (action === "clear-archive") return clearArchive();
  if (action === "follow") {
    state.selectedLifetime = event.target.closest("[data-lifetime-id]").dataset.lifetimeId;
    return run(() => { goFollow(state.selectedLifetime); return loadFollow(); }, { kind: "follow" });
  }
  if (action === "inhabit") return run(() => inhabit(event.target.closest("[data-lifetime-id]").dataset.lifetimeId), { kind: "inhabit" });
});

root.addEventListener("submit", (event) => {
  if (event.target.id !== "decision-form") return;
  event.preventDefault();
  const value = event.target.querySelector("#decision")?.value.trim() || "";
  const action = event.submitter?.dataset.judgmentAction || "CHANGE";
  run(() => submitDecision(action, value), { kind: "decision" });
});

root.addEventListener("input", (event) => {
  if (event.target.id !== "decision") return;
  state.decisionValue = event.target.value;
});

window.addEventListener("hashchange", () => {
  route();
  render();
  run(loadPageData);
});

async function boot() {
  state.error = "";
  render();
  try {
    state.config = await api("/api/config", { timeoutMs: 15000 });
    state.volume = await api("/api/volume", { timeoutMs: 15000 });
    await refreshActive();
    route();
    await loadPageData();
  } catch (error) {
    state.error = error?.name === "AbortError" ? "打开卷册等待过久。" : (error?.message || "卷册暂时打不开。");
  }
  render();
}

route();
boot();
