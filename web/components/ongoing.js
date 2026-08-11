import { escapeHtml } from "./html.js";

function elapsedLabel(currentTick, startedTick) {
  const elapsed = Math.max(0, Number(currentTick) - Number(startedTick));
  if (elapsed === 0) return "今日开始";
  if (elapsed === 1) return "一日前开始";
  return `${elapsed}日前开始`;
}

function expectedLabel(currentTick, expectedTick) {
  if (expectedTick == null) return "正在等待对方回应";
  const remaining = Number(expectedTick) - Number(currentTick);
  if (remaining <= 0) return "结果正在抵达";
  if (remaining === 1) return "预计明日有结果";
  return `预计${remaining}日后有结果`;
}

export function ongoingMarkup(item, currentTick) {
  const terms = (item.terms || []).length
    ? `<ul class="ongoing-terms">${item.terms.map((term) => `<li>${escapeHtml(term)}</li>`).join("")}</ul>`
    : "";
  return `<article class="ongoing-sheet">
    <div><span>${escapeHtml(elapsedLabel(currentTick, item.started_tick))}</span><strong>${escapeHtml(expectedLabel(currentTick, item.expected_tick))}</strong></div>
    <section><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.content)}</p>${terms}</section>
  </article>`;
}
