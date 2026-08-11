import { state } from "./state.js";

const productPages = new Set(["volume", "world", "follow", "desk", "archive", "ending"]);

export function route() {
  const value = location.hash.replace(/^#\/?/, "");
  const [page, resourceId = ""] = value.split("/");
  if (page === "follow" && resourceId) {
    state.page = "follow";
    state.selectedLifetime = decodeURIComponent(resourceId);
    return;
  }
  if (page === "home") {
    state.page = "volume";
    return;
  }
  if (productPages.has(page)) {
    state.page = page;
    return;
  }
  state.page = state.active?.kind === "VOLUME" ? "world" : "volume";
}

export function go(page) {
  location.hash = `#/${page}`;
}

export function goFollow(lifetimeId) {
  location.hash = `#/follow/${encodeURIComponent(lifetimeId)}`;
}
