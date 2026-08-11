import { escapeHtml } from "../components/html.js";

export function volumePage({ volume, chrome, active, config, interactionLocked }) {
  const crises = (volume?.crises || [])
    .map(
      (crisis, index) => `<article class="crisis-catalog-entry">
        <span class="folio">${String(index + 1).padStart(2, "0")}</span>
        <div class="crisis-catalog-copy">
          <p class="kicker">${escapeHtml(crisis.native_date_window || volume.native_period)}</p>
          <h2>${escapeHtml(crisis.title)}</h2>
          <p>${escapeHtml(crisis.subtitle || "一段尚未形成答案的历史危局。")}</p>
          <small>${escapeHtml(crisis.checkpoint_summary || "从一段仍未定稿的现实开始。")}</small>
        </div>
        <div class="crisis-catalog-action">
          <span>${crisis.surface_kind === "POLITICAL" ? "政治危局" : "空间危局"}</span>
          <button class="secondary" data-crisis-id="${escapeHtml(crisis.id)}" ${interactionLocked() ? "disabled" : ""}>打开危局</button>
        </div>
      </article>`,
    )
    .join("");
  const activeNotice = active
    ? `<button class="continue-existing" data-action="open-active" ${interactionLocked() ? "disabled" : ""}>已有一局尚未封存，继续进入</button>`
    : "";
  const setupNote = config?.setup_required
    ? "模型服务尚未配置；可以先阅读危局，开始前请前往设置。"
    : "每一场危局都从自己的检查点开始，不会继承另一局的结果。";
  return chrome(`
    <section class="volume-hero">
      <div class="hero-mast">
        <p class="kicker">${escapeHtml(volume.native_period)}</p>
        <h1>${escapeHtml(volume.title)}</h1>
        <p class="hero-subtitle">${escapeHtml(volume.subtitle)}</p>
      </div>
      <div class="hero-copy">
        <p>${escapeHtml(volume.description)}</p>
        <p class="runtime-note">${escapeHtml(setupNote)}</p>
        ${activeNotice}
      </div>
    </section>
    <section class="crisis-catalog" aria-label="甲申中的历史危局">
      <div class="section-heading"><span>${(volume.crises || []).length} 场危局</span><h2>各自从尚未形成答案的时刻开始</h2></div>
      ${crises || '<p class="empty-copy">卷册暂未收录可进入的危局。</p>'}
    </section>
  `);
}
