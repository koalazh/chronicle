import { state } from "./state.js";

const productPages = new Set(["volume", "watch", "desk", "replay", "archive", "history", "setup", "dev"]);

export function route() {
  const value = location.hash.replace(/^#\/?/, "");
  const [page, crisisId = ""] = value.split("/");
  if (page === "crisis" && crisisId) {
    state.page = "crisis";
    state.crisisId = decodeURIComponent(crisisId);
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
  state.page = state.active ? (state.active.mode === "WATCH" ? "watch" : "desk") : "volume";
}

export function go(page) {
  location.hash = `#/${page}`;
}

export function goCrisis(crisisId) {
  location.hash = `#/crisis/${encodeURIComponent(crisisId)}`;
}
