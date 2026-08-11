import { escapeHtml } from "./html.js";

function reliabilityLabel(value) {
  return { HIGH: "高", MEDIUM: "中等", LOW: "低" }[value] || value;
}

export function arrivalLetterMarkup(item) {
  const terms = (item.terms || []).length
    ? `<div class="letter-terms"><span>${item.kind === "OFFER" ? "对方希望你明确" : "涉及的约定"}</span><ul>${item.terms.map((term) => `<li>${escapeHtml(term)}</li>`).join("")}</ul></div>`
    : "";
  const evidence = item.source || item.reliability
    ? `<footer class="letter-evidence">${item.source ? `<span>来源：${escapeHtml(item.source)}</span>` : ""}${item.reliability ? `<span>可靠性：${escapeHtml(reliabilityLabel(item.reliability))}</span>` : ""}</footer>`
    : "";
  const seal = item.kind === "MESSAGE" || item.kind === "OFFER" ? "书" : "闻";
  return `<article class="letter-sheet arrival-sheet">
    <span class="arrival-seal" aria-hidden="true">${seal}</span>
    <span>${escapeHtml(item.title)}</span>
    <p>${escapeHtml(item.content)}</p>
    ${terms}
    ${evidence}
  </article>`;
}
