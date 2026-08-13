import { state } from "./state.js";

const productPages = new Set(["volume", "world", "follow", "desk", "archive"]);

export function route() {
  const value = location.hash.replace(/^#\/?/, "");
  const [page, resourceId = ""] = value.split("/");
  if (page === "follow" && resourceId) {
    state.page = "follow";
    state.selectedLifetime = decodeURIComponent(resourceId);
    return;
  }
  if (page === "archive" && resourceId) {
    state.page = "archive";
    state.selectedArchive = decodeURIComponent(resourceId);
    return;
  }
  if (page === "home") {
    state.page = "volume";
    return;
  }
  if (page === "world" && state.active?.inhabited_lifetime_id) {
    state.page = "desk";
    state.notice = "请先交还这一生，再回到世界。";
    return;
  }
  if (page === "world" && state.active?.status !== "ACTIVE") {
    state.page = "archive";
    return;
  }
  if (productPages.has(page)) {
    state.page = page;
    return;
  }
  state.page = state.active?.kind === "VOLUME" ? "world" : "volume";
}

export function go(page) {
  if (page === "world" && state.active?.inhabited_lifetime_id) {
    state.notice = "请先交还这一生，再回到世界。";
    page = "desk";
  } else if (page === "world" && state.active?.status !== "ACTIVE") {
    page = "archive";
  }
  location.hash = `#/${page}`;
}

export function goFollow(lifetimeId) {
  location.hash = `#/follow/${encodeURIComponent(lifetimeId)}`;
}
