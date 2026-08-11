import { actorListMarkup } from "../components/actors.js";
import { escapeHtml } from "../components/html.js";

export function crisisCoverPage({ crisis, chrome, active, config, interactionLocked, surfaceMarkup }) {
  if (!crisis) return chrome('<div class="loading-block">正在展开这场危局……</div>');
  const playableActors = (crisis.actors || []).filter((actor) => actor.playable);
  const disabled = active || config?.setup_required || interactionLocked();
  const unresolved = (crisis.checkpoint?.unresolved || [])
    .map((item) => `<li>${escapeHtml(item)}</li>`)
    .join("");
  const takeoverActions = playableActors
    .map(
      (actor) => `<button class="secondary" data-action="start-takeover" data-human-actor-id="${escapeHtml(actor.id)}" ${disabled ? "disabled" : ""}>成为${escapeHtml(actor.display_name)}</button>`,
    )
    .join("");
  const activeNotice = active
    ? `<button class="continue-existing" data-action="open-active" ${interactionLocked() ? "disabled" : ""}>已有一局尚未封存，继续进入</button>`
    : "";
  return chrome(`
    <header class="crisis-cover-header">
      <p class="kicker">${escapeHtml(crisis.checkpoint?.native_date_window || "危局检查点")}</p>
      <h1>${escapeHtml(crisis.title)}</h1>
      <p class="hero-subtitle">${escapeHtml(crisis.subtitle)}</p>
      <p>${escapeHtml(crisis.checkpoint?.summary || "这段历史仍在等待主体把有限条件变成现实。")}</p>
    </header>
    <section class="crisis-cover-surface">
      <span class="column-label">此刻的危局</span>
      ${surfaceMarkup(crisis.surface, { preview: true })}
    </section>
    <section class="crisis-cover-grid">
      <article>
        <span class="column-label">真正未决</span>
        <ul>${unresolved || '<li class="empty">仍待主体在有限信息中作出判断。</li>'}</ul>
      </article>
      <article>
        <span class="column-label">谁在其中</span>
        <p>他们各自拥有有限信息、责任和可执行的选择；不是同一份共享剧本。</p>
      </article>
    </section>
    <section class="actor-intros crisis-actors">
      ${actorListMarkup(crisis.actors, { compact: true })}
    </section>
    <section class="crisis-cover-actions" aria-label="开始这场危局">
      <div><span class="column-label">进入方式</span><h2>先旁观，或成为其中一个关键主体</h2></div>
      <div class="hero-actions">
        <button class="primary" data-action="start-watch" ${disabled ? "disabled" : ""}>旁观这场危局</button>
        ${takeoverActions}
      </div>
      ${activeNotice}
    </section>
    <section class="boundary-note">
      <span>Chronicle 的边界</span>
      <p>它会结算本场能够可靠描述的危局，但不会替之后的整段历史编造未来。</p>
    </section>
  `);
}
