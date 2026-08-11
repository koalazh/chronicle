import { escapeHtml } from "../components/html.js";

export function spatialSurfaceMarkup(surface, options = {}) {
  const locations = surface.locations || [];
  const actors = surface.actors || [];
  const messages = surface.messages || [];
  const actorAt = new Map();
  actors.forEach((actor) => {
    const items = actorAt.get(actor.location) || [];
    items.push(actor);
    actorAt.set(actor.location, items);
  });
  const nodes = locations
    .map((location) => {
      const present = actorAt.get(location.id) || [];
      return `<div class="corridor-node" data-location="${escapeHtml(location.id)}">
        <span class="node-mark"></span>
        <strong>${escapeHtml(location.display_name)}</strong>
        <div class="node-actors">
          ${present
            .map(
              (actor) => `<span class="actor-chip ${options.ownActor === actor.id ? "own" : ""}">
                ${options.hideOthers && options.ownActor !== actor.id ? "动向未知" : escapeHtml(actor.display_name)}
              </span>`,
            )
            .join("")}
        </div>
      </div>`;
    })
    .join("");
  const actorName = options.actorDisplayName || ((actorId) => actorId);
  const letters = messages
    .slice(-5)
    .map(
      (message) => `<li>
        <span>${message.status === "delivered" ? "已抵达" : "在途中"}</span>
        <strong>${escapeHtml(actorName(message.sender))} → ${escapeHtml(actorName(message.recipient))}</strong>
        ${options.preview ? "" : `<small>第 ${message.arrival_tick} 日抵达</small>`}
      </li>`,
    )
    .join("");
  return `<section class="corridor ${options.preview ? "preview" : ""}" aria-label="${escapeHtml(surface.title || "空间态势")}">
    <div class="corridor-track">${nodes}</div>
    ${letters ? `<ol class="letters" aria-label="走廊中的书信">${letters}</ol>` : ""}
  </section>`;
}
