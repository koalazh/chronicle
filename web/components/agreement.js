import { escapeHtml } from "./html.js";

export function agreementMarkup(item) {
  return `<article class="agreement-sheet">
    <span>仍在生效</span>
    <h3>${escapeHtml(item.title)}</h3>
    <p>${escapeHtml(item.content)}</p>
    <ul>${(item.terms || []).map((term) => `<li>${escapeHtml(term)}</li>`).join("")}</ul>
  </article>`;
}
