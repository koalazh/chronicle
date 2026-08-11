import { escapeHtml } from "../components/html.js";

function afterTitle(title) {
  return title.endsWith("之前") ? `${title.slice(0, -2)}之后` : `${title}之后`;
}

function settlementStatement(type) {
  if (type === "DEFERRED") return "危局没有被强行写成唯一结局；它留下的是一段需要后来者继续承受的现实。";
  if (type === "SAFETY_HORIZON") return "模型没有替后来的历史编造答案；在可可靠描述的边界处，这场危局以延期现实封存。";
  return "这场危局已经形成一个可以由当前世界事实可靠说明的局部结果。";
}

function agreementSentence(outcome) {
  const terms = (outcome.agreements || [])
    .flatMap((agreement) => agreement.terms || [])
    .map((term) => String(term.description || "").trim())
    .filter(Boolean);
  return terms.length ? `已经形成的条件仍留在结果之中：${terms.slice(0, 2).join("；")}。` : "";
}

function assetSentence(outcome) {
  const names = (outcome.critical_assets || [])
    .map((asset) => String(asset.display_name || "").trim())
    .filter(Boolean);
  return names.length ? `进入结果的关键现实包括：${names.slice(0, 3).join("、")}。` : "";
}

export function settlementPage({ chrome, crisis, run, outcome }) {
  const title = afterTitle(crisis?.summary?.title || "这一危局");
  const paragraphs = [
    String(outcome.summary || run.outcome || "危局已经形成局部结果。"),
    settlementStatement(outcome.settlement_type),
    agreementSentence(outcome),
    assetSentence(outcome),
    "Chronicle 在这里结算能够可靠描述的危局，不替之后的整段历史虚构命运。",
  ].filter(Boolean);
  const cleanup = run.runtime_phase === "CLEANUP_PENDING" && run.runtime_error_code
    ? `<p class="settlement-cleanup">这一局已可回看；本地主体仍在安全收束。<button class="quiet" data-action="retry-cleanup" data-cleanup-id="${escapeHtml(run.id)}">再次收束</button></p>`
    : "";
  return chrome(`
    <section class="settlement-page">
      <header class="settlement-header">
        <p class="kicker">危局已经结算</p>
        <h1>${escapeHtml(title)}</h1>
      </header>
      <div class="settlement-document">
        ${paragraphs.map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`).join("")}
      </div>
      ${cleanup}
      <footer class="settlement-actions">
        <button class="primary" data-action="open-settlement-replay" data-settlement-replay-id="${escapeHtml(run.id)}">回看这一局</button>
        <button class="quiet" data-action="go-home">回到甲申</button>
      </footer>
    </section>
  `, { compact: true });
}
