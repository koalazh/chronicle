import { escapeHtml } from "../components/html.js";
import { politicalSurfaceMarkup } from "./political.js";
import { spatialSurfaceMarkup } from "./spatial.js";

export function surfaceMarkup(surface, options = {}) {
  if (!surface) return "";
  if (surface.kind === "SPATIAL") return spatialSurfaceMarkup(surface, options);
  if (surface.kind === "POLITICAL") return politicalSurfaceMarkup(surface);
  return `<section class="surface-unavailable"><p>${escapeHtml(surface.title || "危局态势")}</p></section>`;
}
