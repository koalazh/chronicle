import { agreementMarkup } from "../components/agreement.js";
import { escapeHtml } from "../components/html.js";
import { arrivalLetterMarkup } from "../components/letter.js";
import { ongoingMarkup } from "../components/ongoing.js";

function unresolvedMarkup(item) {
  const terms = (item.terms || []).length
    ? `<ul class="matter-terms">${item.terms.map((term) => `<li>${escapeHtml(term)}</li>`).join("")}</ul>`
    : "";
  return `<article class="matter-sheet ${item.kind === "RESOLUTION_GATE" ? "due" : ""}">
    <span>${escapeHtml(item.title)}</span>
    <div><p>${escapeHtml(item.content)}</p>${terms}</div>
  </article>`;
}

export function deskPage({
  chrome,
  header,
  view,
  actorDisplayName,
  surfaceMarkup,
  decisionPanel,
}) {
  if (!view) return chrome('<div class="loading-block">正在展开书案……</div>');
  const desk = view.desk || { arrivals: [], unresolved: [], ongoing: [], agreements: [] };
  const arrivals = desk.arrivals.slice(-6).map(arrivalLetterMarkup).join("");
  const unresolved = desk.unresolved.map(unresolvedMarkup).join("");
  const ongoing = desk.ongoing.map((item) => ongoingMarkup(item, view.tick)).join("");
  const agreements = desk.agreements.map(agreementMarkup).join("");
  const knownSituation = (view.known_situation || [])
    .slice(-5)
    .map((item) => `<li>${escapeHtml(item.text)}</li>`)
    .join("");
  return chrome(`
    ${header}
    <section class="desk-layout desk-v4">
      <div class="desk-main">
        <section class="desk-arrivals">
          <div class="section-heading"><span>新到</span><h2>送到案前的消息与结果</h2></div>
          ${arrivals || '<p class="empty-copy">尚无新物抵达。世界仍会在视野之外继续。</p>'}
        </section>
        <section class="unresolved-matters">
          <div class="section-heading"><span>尚未解决</span><h2>此刻真正需要判断的事</h2></div>
          ${unresolved || '<p class="empty-copy">没有必须立刻处置的事项。</p>'}
        </section>
        <section class="ongoing-matters">
          <div class="section-heading"><span>正在进行</span><h2>已经开始、尚未抵达结果的事</h2></div>
          <div class="ongoing-list">${ongoing || '<p class="empty-copy">此刻没有仍在进行的行动、调查或在途文书。</p>'}</div>
        </section>
        <section class="active-agreements">
          <div class="section-heading"><span>已经作出的约定</span><h2>仍会回来约束后续行动的条件</h2></div>
          <div class="agreement-list">${agreements || '<p class="empty-copy">此刻没有仍在生效、并约束你的约定。</p>'}</div>
        </section>
        <section class="desk-surface">
          <div class="section-heading"><span>已知世界</span><h2>${escapeHtml(view.surface?.title || "危局态势")}</h2></div>
          ${surfaceMarkup(view.surface, { ownActor: view.actor.id, actorDisplayName })}
          <p class="corridor-unknown">其它主体的动向，尚未有可靠消息。</p>
          <div class="known-strip"><span>已经知道</span><ul>${knownSituation || '<li class="empty">尚无可确认的新情况。</li>'}</ul></div>
        </section>
      </div>
      ${decisionPanel}
    </section>
  `);
}
