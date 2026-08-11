import { escapeHtml } from "../components/html.js";

function modeLabel(run) {
  if (run.mode === "TAKEOVER") return run.human_actor ? `成为${run.human_actor}` : "成为关键主体";
  return "旁观这一局";
}

function listMarkup(items, className, empty = "没有进入这份结局的记录。") {
  if (!items?.length) return `<p class="compare-empty">${escapeHtml(empty)}</p>`;
  return `<ul class="${className}">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function outcomeFolio(label, run, outcome) {
  const compatibility = outcome.historical_compatibility?.length
    ? `<ul class="compare-compatibility">${outcome.historical_compatibility
      .map((item) => `<li><span>${escapeHtml(item.title)}</span><strong>${escapeHtml(item.status)}</strong></li>`)
      .join("")}</ul>`
    : "";
  return `<article class="compare-folio">
    <header><span class="column-label">${escapeHtml(label)}</span><span class="compare-run-mode">${escapeHtml(modeLabel(run))}</span><h2>危局已历 ${escapeHtml(run.current_tick)} 日</h2></header>
    <p class="compare-outcome-summary">${escapeHtml(outcome.summary)}</p>
    <p class="compare-settlement">${escapeHtml(outcome.settlement)}</p>
    <section><span class="column-label">进入结果的关键现实</span>${listMarkup(outcome.critical_realities, "compare-realities")}</section>
    ${outcome.agreements?.length ? `<section><span class="column-label">已经作出的约定</span>${listMarkup(outcome.agreements, "compare-agreements")}</section>` : ""}
    ${compatibility ? `<section><span class="column-label">与真实后续相比</span>${compatibility}</section>` : ""}
    <footer><button class="quiet" data-compare-replay-id="${escapeHtml(run.id)}">回看${escapeHtml(label)}</button></footer>
  </article>`;
}

function factColumn(label, facts) {
  if (!facts?.length) return `<section class="compare-fact-column"><span class="column-label">${escapeHtml(label)}</span><p class="compare-empty">这一卷在此刻没有额外世界事实。</p></section>`;
  return `<section class="compare-fact-column"><span class="column-label">${escapeHtml(label)}</span><ol class="compare-facts">${facts
    .map((fact) => `<li><small>${escapeHtml(fact.category)}</small><p>${escapeHtml(fact.text)}</p></li>`)
    .join("")}</ol></section>`;
}

function consequenceColumn(label, path) {
  if (!path.entered_outcome) {
    return `<section class="compare-path-column"><span class="column-label">${escapeHtml(label)}</span><p class="compare-empty">这处差异尚未在 Ledger 中留下可直接压缩到结算的路径；本卷结局仍完整保留在上方。</p></section>`;
  }
  return `<section class="compare-path-column"><span class="column-label">${escapeHtml(label)}</span><ol class="compare-path">${path.steps
    .map((step) => `<li><small>第 ${escapeHtml(step.tick)} 日 · ${escapeHtml(step.category)}</small><p>${escapeHtml(step.text)}</p></li>`)
    .join("")}</ol></section>`;
}

export function comparePage({ chrome, comparison }) {
  if (!comparison) {
    return chrome(`<section class="empty-page"><p class="kicker">两卷对照</p><h1>先从同一危局<br>选择两卷封存记录</h1><p>对照只比较已经进入世界的事实，不把不同措辞当作历史分叉。</p><button class="secondary" data-page="archive">打开封存卷册</button></section>`);
  }
  const fork = comparison.first_material_divergence;
  const forkDocument = fork
    ? `<section class="compare-fork">
      <header><p class="kicker">第一次出现分歧</p><h2>同一危局，从何处开始不同</h2><p>${escapeHtml(fork.summary)}</p></header>
      <div class="compare-columns">${factColumn("左卷", fork.left)}${factColumn("右卷", fork.right)}</div>
    </section>`
    : `<section class="compare-fork no-fork"><p class="kicker">第一次出现分歧</p><h2>这两卷没有出现可建模的世界分歧</h2><p>通信措辞、计划和私下反思不会单独构成世界线分叉。</p></section>`;
  const paths = comparison.consequence_paths;
  return chrome(`
    <section class="compare-page">
      <header class="compare-header"><p class="kicker">两卷对照 · ${escapeHtml(comparison.crisis.title)}</p><h1>同一危局，<br>两种已经兑现的现实</h1><p>${escapeHtml(comparison.crisis.subtitle)}</p></header>
      <p class="compare-outcome-note">${escapeHtml(comparison.outcome_difference.summary)}</p>
      <section class="compare-folios">${outcomeFolio("左卷", comparison.runs.left, comparison.outcome_difference.left)}${outcomeFolio("右卷", comparison.runs.right, comparison.outcome_difference.right)}</section>
      ${forkDocument}
      <section class="compare-consequences"><header><p class="kicker">后续影响</p><h2>${escapeHtml(paths.title)}</h2><p>这里仅保留能够从 Ledger 直接追到结算的世界路径。</p></header><div class="compare-columns">${consequenceColumn("左卷", paths.left)}${consequenceColumn("右卷", paths.right)}</div></section>
      <footer class="compare-actions"><button class="secondary" data-page="archive">回到封存卷册</button></footer>
    </section>
  `, { compact: true });
}
