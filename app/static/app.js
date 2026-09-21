if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    // Registered from the root (not /static/sw.js) with an explicit scope
    // of "/" so it can actually intercept the dashboard page itself, not
    // just requests for static assets - a service worker's default max
    // scope is the directory it's served from.
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      // Installability/offline support is a nice-to-have, not load-bearing -
      // a failed registration (e.g. running over plain http in local dev)
      // shouldn't be treated as an app error.
    });
  });
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`);
  }
  return data;
}

const PACIFIC_TZ = "America/Los_Angeles";

function relativeTime(iso) {
  if (!iso) return null;
  const then = new Date(iso + "Z"); // stored as naive UTC
  const diffMs = Date.now() - then.getTime();
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function pacificString(iso) {
  const then = new Date(iso + "Z");
  return new Intl.DateTimeFormat("en-US", {
    timeZone: PACIFIC_TZ,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(then);
}

function applyFilters() {
  const query = (document.getElementById("search-input")?.value || "").trim().toLowerCase();
  const activeChip = document.querySelector(".chip.is-active");
  const statusFilter = activeChip ? activeChip.dataset.filter : "all";

  let visibleCount = 0;
  document.querySelectorAll(".manufacturer-group").forEach((group) => {
    let groupHasVisible = false;
    // Desktop table rows and phone cards represent the same items in
    // parallel markup (see dashboard.html) - both carry identical
    // data-id/status/category/search attributes, so one pass over this
    // compound selector filters both layouts at once. Only one is ever
    // visible at a time (CSS), but keeping both in sync means the layout
    // that's on screen is always already correct, with nothing to
    // recompute on resize.
    group.querySelectorAll("tbody tr[data-id], .item-card[data-id]").forEach((row) => {
      const matchesSearch = !query || row.dataset.search.includes(query);
      const matchesStatus = statusFilter === "all" || row.dataset.status === statusFilter;
      const visible = matchesSearch && matchesStatus;
      row.classList.toggle("is-hidden", !visible);

      const errorRow = group.querySelector(`tr.error-row[data-parent-id="${row.dataset.id}"]`);
      if (errorRow) errorRow.classList.toggle("is-hidden", !visible);

      if (visible) {
        groupHasVisible = true;
        // Count once per item, not once per representation - a table row
        // exists for every item (cards don't), so it's the canonical one.
        if (row.tagName === "TR") visibleCount++;
      }
    });

    // A category divider ("Consoles", "I/O Racks", ...) should disappear
    // once every row under it has been filtered out - otherwise it's left
    // floating above nothing. Covers both the table's divider row and the
    // card list's, matched to whichever kind of item element is present.
    group.querySelectorAll("tr.category-row, .card-category-row").forEach((catRow) => {
      const anyVisible = [
        ...group.querySelectorAll(
          `tbody tr[data-id][data-category="${catRow.dataset.category}"], .item-card[data-id][data-category="${catRow.dataset.category}"]`
        ),
      ].some((row) => !row.classList.contains("is-hidden"));
      catRow.classList.toggle("is-hidden", !anyVisible);
    });

    group.hidden = !groupHasVisible;
  });

  const emptyState = document.getElementById("empty-state");
  if (emptyState) emptyState.hidden = visibleCount > 0;
}

document.addEventListener("DOMContentLoaded", () => {
  // Relative "last checked" times, computed client-side so the server doesn't
  // need to re-render on every page load just to keep them fresh-looking.
  document.querySelectorAll(".time-cell[data-utc]").forEach((cell) => {
    const rel = relativeTime(cell.dataset.utc);
    if (rel) {
      cell.title = pacificString(cell.dataset.utc);
      // Only touch the date text span - the cell may also contain a sibling
      // "manual" tag that must survive this update, not get wiped out by it.
      const textSpan = cell.querySelector(".time-text");
      if (textSpan) textSpan.textContent = rel;
    }
  });

  const checkAllBtn = document.getElementById("check-all-btn");
  if (checkAllBtn) {
    checkAllBtn.addEventListener("click", async () => {
      checkAllBtn.disabled = true;
      const label = checkAllBtn.querySelector(".btn-label");
      const original = label.textContent;
      label.textContent = "Checking…";
      try {
        await postJSON("/api/check-now");
        window.location.reload();
      } catch (e) {
        checkAllBtn.disabled = false;
        label.textContent = original;
        alert("Check failed: " + e);
      }
    });
  }

  const searchInput = document.getElementById("search-input");
  if (searchInput) {
    searchInput.addEventListener("input", applyFilters);
  }

  document.querySelectorAll(".chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      document.querySelectorAll(".chip").forEach((c) => c.classList.remove("is-active"));
      chip.classList.add("is-active");
      applyFilters();
    });
  });

  // Phone card list: tap a card's summary to reveal its remaining fields
  // (detected on/previous/last checked/source), tucked away by default so
  // the collapsed list stays compact. Independent per card - not a
  // one-at-a-time accordion, since expanding one card has no reason to
  // affect any other. role="button" (not a real <button>) because the
  // model name inside it is a heading (<h3>), which isn't valid content for
  // a <button>.
  document.querySelectorAll(".card-summary").forEach((summary) => {
    const details = summary.closest(".item-card")?.querySelector(".card-details");
    if (!details) return;
    const toggle = () => {
      const opening = details.hidden;
      details.hidden = !opening;
      summary.setAttribute("aria-expanded", String(opening));
    };
    summary.addEventListener("click", toggle);
    summary.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        toggle();
      }
    });
  });

  // "Updates found" KPI card: click through to just the currently-flagged
  // rows, by reusing the existing filter-chip logic rather than duplicating
  // it.
  const updatesKpi = document.getElementById("updates-kpi");
  if (updatesKpi) {
    const jumpToUpdates = () => {
      document.querySelector(".chip[data-filter='update_detected']")?.click();
      document.querySelector(".toolbar")?.scrollIntoView({ behavior: "smooth", block: "start" });
    };
    updatesKpi.addEventListener("click", jumpToUpdates);
    updatesKpi.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        jumpToUpdates();
      }
    });
  }

  // Click-to-open info popovers (e.g. "what does 'update found' mean?").
  // Reusable for any future .info-icon/.info-popover pair, not just this
  // one. stopPropagation matters here specifically because this icon sits
  // inside the clickable "Updates found" card above - without it, opening
  // the popover would also fire that card's jump-to-filtered-view action.
  const closeAllInfoPopovers = () => {
    document.querySelectorAll(".info-popover").forEach((p) => { p.hidden = true; });
    document.querySelectorAll(".info-icon").forEach((b) => b.setAttribute("aria-expanded", "false"));
  };
  document.querySelectorAll(".info-icon").forEach((btn) => {
    const popover = btn.nextElementSibling;
    if (!popover) return;
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const opening = popover.hidden;
      closeAllInfoPopovers();
      if (opening) {
        popover.hidden = false;
        btn.setAttribute("aria-expanded", "true");
      }
    });
    btn.addEventListener("keydown", (e) => e.stopPropagation());
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".info-wrap")) closeAllInfoPopovers();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllInfoPopovers();
  });
});
