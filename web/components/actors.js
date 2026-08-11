import { escapeHtml } from "./html.js";

export function actorListMarkup(actors, { compact = false } = {}) {
  return (actors || [])
    .map(
      (actor, index) => `<article class="actor-intro${compact ? " compact" : ""}">
        <span class="folio">${String(index + 1).padStart(2, "0")}</span>
        <div>
          <h3>${escapeHtml(actor.display_name)}</h3>
          <p>${escapeHtml(actor.role_charter.who)}</p>
          ${compact ? "" : `<small>${escapeHtml((actor.role_charter.tensions || []).join(" · "))}</small>`}
        </div>
      </article>`,
    )
    .join("");
}
