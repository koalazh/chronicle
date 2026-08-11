import { escapeHtml } from "../components/html.js";

const entityTypeLabels = {
  CLAIMANT: "候选",
  INSTITUTION: "制度程序",
  ASSET: "现实条件",
  DOCUMENT: "公开文书",
  PERSON: "人物",
  FORCE: "可见力量",
  PLACE: "地点",
};

function stateMarkup(entry) {
  if (entry.knowledge === "KNOWN") {
    return `<strong>${escapeHtml(entry.state_label || entry.state || "尚无定论")}</strong>`;
  }
  const copy = entry.knowledge === "UNCONFIRMED" ? "尚待确证" : "未获所知";
  return `<strong class="political-unknown">${copy}</strong>`;
}

export function politicalSurfaceMarkup(surface) {
  const subjects = (surface.subjects || [])
    .map(
      (subject) => `<article class="political-subject">
        <span>${escapeHtml(entityTypeLabels[subject.type] || "世界事实")}</span>
        <h3>${escapeHtml(subject.display_name)}</h3>
        ${stateMarkup(subject)}
      </article>`,
    )
    .join("");
  const context = (surface.context || [])
    .map(
      (entry) => `<li>
        <span>${escapeHtml(entry.display_name)}</span>
        ${stateMarkup(entry)}
      </li>`,
    )
    .join("");
  return `<section class="political-surface" aria-label="${escapeHtml(surface.title || "政治事实")}">
    <div class="political-subjects">${subjects}</div>
    ${context ? `<div class="political-context"><p>尚未定稿的政治事实</p><ul>${context}</ul></div>` : ""}
  </section>`;
}
