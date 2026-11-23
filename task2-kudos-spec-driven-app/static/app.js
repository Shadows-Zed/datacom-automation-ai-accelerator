(() => {
  const state = {
    token: localStorage.getItem("kudos_token") || "",
    user: null,
    page: 1,
    pageSize: 10,
    total: 0,
    hasMore: false,
  };

  const el = {
    toast: document.getElementById("toast"),
    loginCard: document.getElementById("login-card"),
    loginForm: document.getElementById("login-form"),
    loginUsername: document.getElementById("login-username"),
    loginPassword: document.getElementById("login-password"),
    quickEmployeeBtn: document.getElementById("quick-employee-btn"),
    quickAdminBtn: document.getElementById("quick-admin-btn"),
    openLoginBtn: document.getElementById("open-login-btn"),
    logoutBtn: document.getElementById("logout-btn"),
    userBadge: document.getElementById("user-badge"),
    composerLockMsg: document.getElementById("composer-lock-msg"),
    kudosForm: document.getElementById("kudos-form"),
    recipientSelect: document.getElementById("recipient-select"),
    categorySelect: document.getElementById("category-select"),
    messageInput: document.getElementById("message-input"),
    charCounter: document.getElementById("char-counter"),
    formError: document.getElementById("form-error"),
    searchInput: document.getElementById("search-input"),
    filterCategory: document.getElementById("filter-category"),
    adminHiddenWrap: document.getElementById("admin-hidden-toggle-wrap"),
    showHiddenCheckbox: document.getElementById("show-hidden-checkbox"),
    kudosList: document.getElementById("kudos-list"),
    prevPageBtn: document.getElementById("prev-page-btn"),
    nextPageBtn: document.getElementById("next-page-btn"),
    pageIndicator: document.getElementById("page-indicator"),
    auditSection: document.getElementById("audit-section"),
    auditList: document.getElementById("audit-list"),
    refreshAuditBtn: document.getElementById("refresh-audit-btn"),
  };

  function showToast(message, type = "success") {
    el.toast.textContent = message;
    el.toast.className = `toast ${type}`;
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
      el.toast.className = "toast hidden";
    }, 4000);
  }

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (state.token) {
      headers.Authorization = `Bearer ${state.token}`;
    }
    if (options.body && !headers["Content-Type"]) {
      headers["Content-Type"] = "application/json";
    }
    const res = await fetch(path, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = (data.error && data.error.message) || `Request failed (${res.status})`;
      throw new Error(msg);
    }
    return data;
  }

  function updateAuthUI() {
    const loggedIn = Boolean(state.user);
    const isAdmin = loggedIn && state.user.role === "admin";

    el.loginCard.classList.toggle("hidden", loggedIn);
    el.openLoginBtn.classList.toggle("hidden", loggedIn);
    el.logoutBtn.classList.toggle("hidden", !loggedIn);
    el.userBadge.classList.toggle("hidden", !loggedIn);
    el.composerLockMsg.classList.toggle("hidden", loggedIn);
    el.kudosForm.classList.toggle("hidden", !loggedIn);
    el.adminHiddenWrap.classList.toggle("hidden", !isAdmin);
    el.auditSection.classList.toggle("hidden", !isAdmin);

    if (loggedIn) {
      el.userBadge.textContent = `${state.user.full_name} (${state.user.role})`;
    } else {
      el.showHiddenCheckbox.checked = false;
    }
  }

  async function loadColleagues() {
    if (!state.user) return;
    const data = await api("/api/users?exclude_self=true");
    el.recipientSelect.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select a colleague...";
    el.recipientSelect.appendChild(placeholder);

    for (const u of data.users) {
      const opt = document.createElement("option");
      opt.value = String(u.id);
      opt.textContent = `${u.full_name} — ${u.department}`;
      el.recipientSelect.appendChild(opt);
    }
  }

  async function loadFeed() {
    const params = new URLSearchParams({
      page: String(state.page),
      page_size: String(state.pageSize),
    });
    if (el.filterCategory.value) params.set("category", el.filterCategory.value);
    if (el.searchInput.value.trim()) params.set("search", el.searchInput.value.trim());
    if (state.user && state.user.role === "admin" && el.showHiddenCheckbox.checked) {
      params.set("include_hidden", "true");
    }

    const data = await api(`/api/kudos?${params.toString()}`);
    state.total = data.total;
    state.hasMore = data.has_more;
    renderFeed(data.items);
  }

  function renderFeed(items) {
    el.kudosList.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "No kudos match your current filter yet.";
      el.kudosList.appendChild(empty);
    }

    const isAdmin = state.user && state.user.role === "admin";

    for (const item of items) {
      const card = document.createElement("article");
      card.className = `kudos-item${item.is_visible ? "" : " hidden-item"}`;

      const meta = document.createElement("div");
      meta.className = "kudos-meta";

      const people = document.createElement("div");
      people.className = "kudos-people";
      people.textContent = `${item.sender.full_name} → ${item.recipient.full_name}`;

      const badges = document.createElement("div");
      const catPill = document.createElement("span");
      catPill.className = "pill";
      catPill.textContent = item.category;
      badges.appendChild(catPill);

      if (!item.is_visible) {
        const hiddenPill = document.createElement("span");
        hiddenPill.className = "pill pill-hidden";
        hiddenPill.style.marginLeft = "0.4rem";
        hiddenPill.textContent = "Hidden";
        badges.appendChild(hiddenPill);
      }

      meta.appendChild(people);
      meta.appendChild(badges);

      const msg = document.createElement("p");
      msg.className = "kudos-message";
      msg.textContent = item.message;

      const footer = document.createElement("div");
      footer.className = "kudos-footer";

      const timestamp = document.createElement("span");
      timestamp.textContent = new Date(item.created_at).toLocaleString();
      footer.appendChild(timestamp);

      if (!item.is_visible && item.moderation) {
        const modNote = document.createElement("span");
        modNote.textContent = `Reason: ${item.moderation.reason_for_moderation}`;
        footer.appendChild(modNote);
      }

      if (isAdmin) {
        const actions = document.createElement("div");
        actions.className = "admin-actions";

        const toggleBtn = document.createElement("button");
        toggleBtn.type = "button";
        toggleBtn.className = "btn btn-ghost";
        toggleBtn.textContent = item.is_visible ? "Hide" : "Restore";
        toggleBtn.addEventListener("click", () => handleToggleVisibility(item));

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.className = "btn btn-danger";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", () => handleDelete(item));

        actions.appendChild(toggleBtn);
        actions.appendChild(delBtn);
        footer.appendChild(actions);
      }

      card.appendChild(meta);
      card.appendChild(msg);
      card.appendChild(footer);
      el.kudosList.appendChild(card);
    }

    const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));
    el.pageIndicator.textContent = `Page ${state.page} of ${totalPages} (${state.total} total)`;
    el.prevPageBtn.disabled = state.page <= 1;
    el.nextPageBtn.disabled = !state.hasMore;
  }

  async function loadAuditLogs() {
    if (!state.user || state.user.role !== "admin") return;
    const data = await api("/api/admin/audit-logs?limit=25");
    el.auditList.innerHTML = "";
    if (!data.logs.length) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "No moderation actions recorded yet.";
      el.auditList.appendChild(empty);
      return;
    }
    for (const log of data.logs) {
      const row = document.createElement("div");
      row.className = "audit-row";
      row.textContent = `[${log.action}] Kudos #${log.kudos_id} by ${log.admin_name} — "${log.reason}" (${new Date(log.created_at).toLocaleString()})`;
      el.auditList.appendChild(row);
    }
  }

  async function handleToggleVisibility(item) {
    const nextVisible = !item.is_visible;
    let reason = "";
    if (!nextVisible) {
      reason = window.prompt("Enter moderation reason for hiding this kudos:") || "";
      if (reason.trim().length < 3) {
        showToast("Moderation reason must be at least 3 characters.", "error");
        return;
      }
    }
    try {
      await api(`/api/admin/kudos/${item.id}/visibility`, {
        method: "PATCH",
        body: JSON.stringify({ is_visible: nextVisible, reason }),
      });
      showToast(nextVisible ? "Kudos restored to public feed." : "Kudos hidden from public feed.");
      await Promise.all([loadFeed(), loadAuditLogs()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function handleDelete(item) {
    if (!window.confirm(`Permanently delete Kudos #${item.id}?`)) return;
    const reason = window.prompt("Reason for permanent deletion:", "Policy violation") || "Policy violation";
    try {
      await api(`/api/admin/kudos/${item.id}`, {
        method: "DELETE",
        body: JSON.stringify({ reason }),
      });
      showToast(`Kudos #${item.id} permanently deleted.`);
      await Promise.all([loadFeed(), loadAuditLogs()]);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  async function performLogin(username, password) {
    try {
      const data = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      state.token = data.token;
      state.user = data.user;
      localStorage.setItem("kudos_token", state.token);
      updateAuthUI();
      await Promise.all([loadColleagues(), loadFeed(), loadAuditLogs()]);
      showToast(`Signed in as ${state.user.full_name}.`);
    } catch (err) {
      showToast(err.message, "error");
    }
  }

  el.loginForm.addEventListener("submit", (e) => {
    e.preventDefault();
    performLogin(el.loginUsername.value, el.loginPassword.value);
  });

  el.quickEmployeeBtn.addEventListener("click", () => performLogin("alice", "demo123"));
  el.quickAdminBtn.addEventListener("click", () => performLogin("admin", "admin123"));
  el.openLoginBtn.addEventListener("click", () => el.loginUsername.focus());

  el.logoutBtn.addEventListener("click", async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } catch (_) {
      // ignore session expiration on logout
    }
    state.token = "";
    state.user = null;
    localStorage.removeItem("kudos_token");
    updateAuthUI();
    state.page = 1;
    await loadFeed();
    showToast("Signed out.");
  });

  el.messageInput.addEventListener("input", () => {
    el.charCounter.textContent = `${el.messageInput.value.length} / 500`;
  });

  el.kudosForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    el.formError.classList.add("hidden");

    const recipientId = el.recipientSelect.value;
    const message = el.messageInput.value.trim();
    if (!recipientId) {
      el.formError.textContent = "Please select a colleague.";
      el.formError.classList.remove("hidden");
      return;
    }
    if (!message || message.length > 500) {
      el.formError.textContent = "Message must be between 1 and 500 characters.";
      el.formError.classList.remove("hidden");
      return;
    }

    try {
      await api("/api/kudos", {
        method: "POST",
        body: JSON.stringify({
          recipient_id: Number(recipientId),
          category: el.categorySelect.value,
          message,
        }),
      });
      el.messageInput.value = "";
      el.charCounter.textContent = "0 / 500";
      state.page = 1;
      await loadFeed();
      showToast("Kudos submitted!");
    } catch (err) {
      el.formError.textContent = err.message;
      el.formError.classList.remove("hidden");
    }
  });

  el.filterCategory.addEventListener("change", () => {
    state.page = 1;
    loadFeed().catch((err) => showToast(err.message, "error"));
  });

  el.showHiddenCheckbox.addEventListener("change", () => {
    state.page = 1;
    loadFeed().catch((err) => showToast(err.message, "error"));
  });

  let searchDebounce = null;
  el.searchInput.addEventListener("input", () => {
    clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      state.page = 1;
      loadFeed().catch((err) => showToast(err.message, "error"));
    }, 250);
  });

  el.prevPageBtn.addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      loadFeed().catch((err) => showToast(err.message, "error"));
    }
  });

  el.nextPageBtn.addEventListener("click", () => {
    if (state.hasMore) {
      state.page += 1;
      loadFeed().catch((err) => showToast(err.message, "error"));
    }
  });

  el.refreshAuditBtn.addEventListener("click", () => {
    loadAuditLogs().catch((err) => showToast(err.message, "error"));
  });

  async function bootstrap() {
    if (state.token) {
      try {
        const data = await api("/api/auth/me");
        state.user = data.user;
      } catch (_) {
        state.token = "";
        localStorage.removeItem("kudos_token");
      }
    }
    updateAuthUI();
    await Promise.all([loadColleagues(), loadFeed(), loadAuditLogs()]);
  }

  bootstrap().catch((err) => showToast(err.message, "error"));
})();
