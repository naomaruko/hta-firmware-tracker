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
  // Rounds down, not to the nearest unit - rounding made 23h30m read as
  // "1d ago" when a full day hadn't actually passed yet, which looks like a
  // missed daily check when it isn't one.
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
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
      const textSpan = cell.querySelector(".time-text");
      if (textSpan) textSpan.textContent = rel;
    }
  });

  // "Last checked" stat card: same relative phrasing as the table cells
  // above, capitalised since it's a standalone value ("Just now", "2h
  // ago"). Computed here rather than server-side so the static deployed
  // page, which is only rebuilt once a day, doesn't freeze whatever the
  // phrase happened to be at build time. Left as the server-rendered
  // timestamp if there's no last-run time to convert.
  const lastRun = document.getElementById("last-run");
  if (lastRun && lastRun.dataset.utc) {
    const rel = relativeTime(lastRun.dataset.utc);
    if (rel) lastRun.textContent = rel.charAt(0).toUpperCase() + rel.slice(1);
  }

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

  // "Updates" stat card: click through to just the currently-flagged
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
  // inside the clickable "Updates" card above - without it, opening
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

  setupInstallBanner();
});

// "Add to Home Screen" banner. Phone only, and only when there's something
// useful to say: a one-tap install button where the browser offers the
// native beforeinstallprompt flow (Chrome, Edge, Samsung Internet, and
// most other Chromium-based Android browsers), otherwise manual steps for
// iOS Safari or any other mobile browser that never fires that event.
// Stays hidden entirely if the app is already installed or the person has
// dismissed it before (localStorage, so the choice persists across visits
// on this device).
function setupInstallBanner() {
  const STORAGE_KEY = "installBannerDismissed";
  const banner = document.getElementById("install-banner");
  const textEl = document.getElementById("install-banner-text");
  const actionBtn = document.getElementById("install-banner-action");
  const dismissBtn = document.getElementById("install-banner-dismiss");
  if (!banner || !textEl || !actionBtn || !dismissBtn) return;

  const isStandalone = () =>
    window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;

  const isDismissed = () => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch (e) {
      return false; // private browsing / storage blocked - fail open rather than crash
    }
  };

  const dismiss = () => {
    banner.hidden = true;
    try {
      localStorage.setItem(STORAGE_KEY, "1");
    } catch (e) {
      // Can't persist (private browsing, storage disabled, quota) - it's
      // still hidden for this page view, just won't stay dismissed next visit.
    }
  };

  // Already installed, or already dismissed before - nothing to do, and
  // deliberately don't even check the device type below in that case.
  if (isStandalone() || isDismissed()) return;

  const ua = navigator.userAgent;
  // iPadOS 13+ reports as "MacIntel" with no "iPad" in the UA - the
  // touch-points check is the standard way to still catch it. Excluding
  // "Android" guards against non-Apple devices/browsers that also happen to
  // report a MacIntel-like platform with touch points.
  const isIOS =
    /iPad|iPhone|iPod/.test(ua) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1 && !/Android/i.test(ua));
  // Chrome/Firefox/Edge "for iOS" are re-skinned Safari (Apple requires
  // WebKit for all iOS browsers) and don't expose "Add to Home Screen" the
  // same way outside the actual Safari app - showing Safari-specific
  // instructions there would just be wrong, so skip the banner entirely
  // rather than guess.
  const isIOSOtherBrowser = isIOS && /CriOS|FxiOS|EdgiOS|OPiOS/i.test(ua);
  const isMobile = (isIOS || /Android/i.test(ua) || window.innerWidth < 768) && !isIOSOtherBrowser;
  if (!isMobile) return;

  dismissBtn.addEventListener("click", dismiss);

  let deferredPrompt = null;
  let nativePromptOffered = false;

  function showManualInstructions() {
    if (!banner.hidden) return; // native prompt already claimed the banner
    textEl.textContent = isIOS
      ? "Add this app to your home screen: tap Share, then “Add to Home Screen.”"
      : "Add this app to your home screen: open your browser menu, then “Add to Home Screen” or “Install.”";
    actionBtn.hidden = true;
    banner.hidden = false;
  }

  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    deferredPrompt = e;
    nativePromptOffered = true;
    textEl.textContent = "Install this app for quick access from your home screen.";
    actionBtn.hidden = false;
    banner.hidden = false;
  });

  window.addEventListener("appinstalled", dismiss);

  actionBtn.addEventListener("click", async () => {
    if (!deferredPrompt) return;
    actionBtn.disabled = true;
    deferredPrompt.prompt();
    try {
      await deferredPrompt.userChoice;
    } catch (e) {
      // ignore - either way we're done offering it this visit
    }
    deferredPrompt = null;
    // Whether they accepted or declined the native prompt, don't keep
    // asking every visit - accepting also fires "appinstalled" above,
    // which calls dismiss() too, so this covers the decline case.
    dismiss();
  });

  if (isIOS) {
    // beforeinstallprompt never fires on iOS Safari - no reason to wait for it.
    showManualInstructions();
  } else {
    // Give the browser a few seconds to offer the native prompt (Chrome
    // etc.) before assuming this one doesn't support it (Firefox for
    // Android) and falling back to manual steps.
    setTimeout(() => {
      if (!nativePromptOffered) showManualInstructions();
    }, 3000);
  }
}
