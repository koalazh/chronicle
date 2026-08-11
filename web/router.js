import { state } from "./state.js";

const productPages = new Set(["volume", "watch", "desk", "replay", "compare", "archive", "history", "setup", "dev"]);

export function route() {
  const value = location.hash.replace(/^#\/?/, "");
  const [page, resourceId = "", secondaryId = ""] = value.split("/");
  if (page === "crisis" && resourceId) {
    state.page = "crisis";
    state.crisisId = decodeURIComponent(resourceId);
    return;
  }
  if (page === "settlement" && resourceId) {
    state.page = "settlement";
    state.settlementRunId = decodeURIComponent(resourceId);
    return;
  }
  if (page === "compare") {
    state.page = "compare";
    state.compareLeftRunId = resourceId ? decodeURIComponent(resourceId) : "";
    state.compareRightRunId = secondaryId ? decodeURIComponent(secondaryId) : "";
    if (!resourceId || !secondaryId) {
      state.compare = null;
      state.compareLeftRunId = "";
      state.compareRightRunId = "";
      state.compareSelectedRunId = "";
    }
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

export function goSettlement(runId) {
  location.hash = `#/settlement/${encodeURIComponent(runId)}`;
}

export function goCompare(leftRunId, rightRunId) {
  location.hash = `#/compare/${encodeURIComponent(leftRunId)}/${encodeURIComponent(rightRunId)}`;
}
