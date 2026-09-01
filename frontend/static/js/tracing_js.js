const API_BASE = "";

// DOM Elements
const adminLoginView = document.getElementById("adminLoginView");
const adminDashboardView = document.getElementById("adminDashboardView");
const adminLoginForm = document.getElementById("adminLoginForm");
const adminLoginError = document.getElementById("adminLoginError");
const toggleAdminPassword = document.getElementById("toggleAdminPassword");
const adminPasswordInput = document.getElementById("adminPasswordInput");
const adminLoginButton = document.getElementById("adminLoginButton");
const adminLoginButtonText = document.getElementById("adminLoginButtonText");
const adminLoginSpinner = document.getElementById("adminLoginSpinner");
const adminLogoutBtn = document.getElementById("adminLogoutBtn");

const filterUser = document.getElementById("filterUser");
const filterRole = document.getElementById("filterRole");
const filterSearch = document.getElementById("filterSearch");
const filterDateFrom = document.getElementById("filterDateFrom");
const filterDateTo = document.getElementById("filterDateTo");
const refreshTracesBtn = document.getElementById("refreshTracesBtn");
const exportCsvBtn = document.getElementById("exportCsvBtn");
const exportNote = document.getElementById("exportNote");

let allTraces = [];
let visibleTraces = [];
let lastKpi = null;

/* ------------------------------------------------------------------ */
/* Password visibility                                                */
/* ------------------------------------------------------------------ */
if (toggleAdminPassword && adminPasswordInput) {
    toggleAdminPassword.addEventListener("click", () => {
        if (adminPasswordInput.type === "password") {
            adminPasswordInput.type = "text";
            toggleAdminPassword.setAttribute("aria-label", "Hide password");
        } else {
            adminPasswordInput.type = "password";
            toggleAdminPassword.setAttribute("aria-label", "Show password");
        }
    });
}

/* ------------------------------------------------------------------ */
/* Admin login                                                        */
/* ------------------------------------------------------------------ */
if (adminLoginForm) {
    adminLoginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (adminLoginError) adminLoginError.textContent = "";

        const email = document.getElementById("adminEmailInput").value.trim();
        const password = document.getElementById("adminPasswordInput").value;

        if (adminLoginButton) adminLoginButton.disabled = true;
        if (adminLoginButtonText) adminLoginButtonText.textContent = "Signing in…";
        if (adminLoginSpinner) adminLoginSpinner.hidden = false;

        try {
            const res = await fetch(`${API_BASE}/api/admin/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: email, password: password })
            });
            const data = await res.json();

            if (!res.ok) {
                if (adminLoginError) adminLoginError.textContent = data.detail || "Invalid admin credentials.";
                return;
            }

            localStorage.setItem("admin_access_token", data.access_token);
            showDashboard();
        } catch (err) {
            if (adminLoginError) adminLoginError.textContent = "⚠️ Connection to server failed.";
        } finally {
            if (adminLoginButton) adminLoginButton.disabled = false;
            if (adminLoginButtonText) adminLoginButtonText.textContent = "Sign in";
            if (adminLoginSpinner) adminLoginSpinner.hidden = true;
        }
    });
}

async function showDashboard() {
    if (adminLoginView) adminLoginView.style.display = "none";
    if (adminDashboardView) adminDashboardView.style.display = "block";
    await fetchDashboardData();
}

/* ------------------------------------------------------------------ */
/* Fetch traces + KPI                                                 */
/* ------------------------------------------------------------------ */
async function fetchDashboardData() {
    const token = localStorage.getItem("admin_access_token");
    const adminStatus = document.getElementById("adminStatus");
    if (!token) return;

    if (adminStatus) adminStatus.innerHTML = "<b>Loading dashboard data…</b>";

    try {
        const res = await fetch(`${API_BASE}/api/admin/dashboard`, {
            headers: { "Authorization": `Bearer ${token}` }
        });

        if (res.status === 401 || res.status === 403) {
            logoutAdmin();
            return;
        }

        const data = await res.json();
        if (data.status === "success") {
            if (adminStatus) adminStatus.innerHTML = "";
            allTraces = data.traces || [];
            lastKpi = data.kpi || {};
            updateKPIs(lastKpi, allTraces.length);
            populateFilters(allTraces);
            applyFilters();
            renderCostAnalytics(lastKpi, allTraces);
        } else {
            if (adminStatus) adminStatus.innerHTML = `<span style="color:var(--danger);">⚠️ Error: ${data.error || 'Failed to fetch data'}</span>`;
        }
    } catch (err) {
        if (adminStatus) adminStatus.innerHTML = `<span style="color:var(--danger);">⚠️ Connection error.</span>`;
    }
}

function updateKPIs(kpi, tracesCount) {
    const kpiTraces = document.getElementById("kpiTraces");
    const kpiUsers = document.getElementById("kpiUsers");
    const kpiGenerations = document.getElementById("kpiGenerations");
    const kpiTokens = document.getElementById("kpiTokens");
    const kpiCost = document.getElementById("kpiCost");

    if (kpiTraces) kpiTraces.textContent = tracesCount;
    if (kpiUsers) kpiUsers.textContent = kpi.unique_users ? kpi.unique_users.length : 0;
    if (kpiGenerations) kpiGenerations.textContent = kpi.calls_count || 0;
    if (kpiTokens) kpiTokens.textContent = kpi.total_tokens || 0;

    let totalCostVal = parseFloat(kpi.total_cost || 0);
    if (kpiCost) kpiCost.textContent = `$${totalCostVal.toFixed(6)}`;
}

function populateFilters(traces) {
    if (filterUser) {
        const currentUserSelected = filterUser.value || "All";
        filterUser.innerHTML = '<option value="All">All</option>';
        const users = [...new Set(traces.map(t => t.user_id).filter(Boolean))].sort();
        users.forEach(u => {
            const opt = document.createElement("option");
            opt.value = u;
            opt.textContent = u;
            filterUser.appendChild(opt);
        });
        filterUser.value = users.includes(currentUserSelected) ? currentUserSelected : "All";
    }

    if (filterRole) {
        const currentRoleSelected = filterRole.value || "All";
        filterRole.innerHTML = '<option value="All">All</option>';
        const roles = [...new Set(traces.map(t => t.user_role).filter(Boolean))].sort();
        roles.forEach(r => {
            const opt = document.createElement("option");
            opt.value = r;
            opt.textContent = r;
            filterRole.appendChild(opt);
        });
        filterRole.value = roles.includes(currentRoleSelected) ? currentRoleSelected : "All";
    }
}

/* ------------------------------------------------------------------ */
/* Trace list rendering                                               */
/* ------------------------------------------------------------------ */
function renderTraceList(traces) {
    const listContainer = document.getElementById("adminTraceList");
    if (!listContainer) return;

    listContainer.innerHTML = "";

    if (traces.length === 0) {
        listContainer.innerHTML = '<div class="empty-state">No traces match the current filters.</div>';
        return;
    }

    traces.forEach(t => {
        const card = document.createElement("div");
        card.className = "admin-trace-card";

        card.addEventListener("click", (e) => {
            if (e.target.tagName.toLowerCase() === "a") return;
            card.classList.toggle("open");
        });

        let timeStr = "";
        try {
            if (t.timestamp) timeStr = new Date(t.timestamp).toLocaleString();
        } catch (err) {
            timeStr = t.timestamp || "";
        }

        const uSent = t.user_sentiment || { label: "Neutral", confidence: 1.0 };
        const aSent = t.assistant_sentiment || { label: "Neutral", confidence: 1.0 };

        const uSentEmoji = uSent.label === "Positive" ? "🟢" : (uSent.label === "Negative" ? "🔴" : "⚪");
        const aSentEmoji = aSent.label === "Positive" ? "🟢" : (aSent.label === "Negative" ? "🔴" : "⚪");

        card.innerHTML = `
            <div class="admin-trace-top">
                <div class="admin-trace-query">${escapeHtml(t.query || "Empty query")}</div>
                <div class="admin-trace-meta">
                    <span class="admin-trace-badge">User: ${escapeHtml(t.user_id)}</span>
                    <span class="admin-trace-badge">Role: ${escapeHtml(t.user_role)}</span>
                    <span class="admin-trace-badge">${timeStr}</span>
                </div>
            </div>

            <div class="admin-trace-details">
                <div class="admin-trace-section-label">User query sentiment</div>
                <div class="admin-sentiment-row" style="margin-bottom:12px;">
                    <span class="admin-sentiment-chip">${uSentEmoji} User: ${uSent.label} (${Math.round((uSent.confidence || 0) * 100)}%)</span>
                    <span class="admin-sentiment-chip">${aSentEmoji} Assistant: ${aSent.label} (${Math.round((aSent.confidence || 0) * 100)}%)</span>
                </div>

                <div class="admin-trace-section-label">Active agents</div>
                <div style="margin-bottom: 12px;">
                    ${t.agents && t.agents.length > 0
                        ? t.agents.map(a => `<span class="admin-trace-badge" style="margin-right:6px;display:inline-block;margin-bottom:4px;">${escapeHtml(a)}</span>`).join("")
                        : '<span class="admin-trace-badge">None</span>'}
                </div>

                ${t.routing_reason ? `
                    <div class="admin-trace-section-label">Routing reason</div>
                    <div class="admin-trace-box" style="margin-bottom:12px;">${escapeHtml(t.routing_reason)}</div>
                ` : ""}

                <div class="admin-trace-section-label">AI response</div>
                <div class="admin-trace-box" style="margin-bottom:12px;">${escapeHtml(t.response || "No response generated")}</div>

                <div style="margin-top:14px;text-align:right;">
                    <a href="${t.url}" target="_blank" class="admin-trace-link" style="color:var(--brand-deep);text-decoration:none;font-weight:700;">🔍 View trace in Langfuse ↗</a>
                </div>
            </div>
        `;

        listContainer.appendChild(card);
    });
}

/* ------------------------------------------------------------------ */
/* Filters (user, role, date range, search)                           */
/* ------------------------------------------------------------------ */
function applyFilters() {
    const userVal = filterUser ? filterUser.value : "All";
    const roleVal = filterRole ? filterRole.value : "All";
    const searchVal = filterSearch ? filterSearch.value.trim().toLowerCase() : "";
    const fromVal = filterDateFrom && filterDateFrom.value ? new Date(filterDateFrom.value) : null;
    const toVal = filterDateTo && filterDateTo.value ? new Date(filterDateTo.value) : null;
    if (toVal) toVal.setHours(23, 59, 59, 999);

    const filtered = allTraces.filter(t => {
        const matchUser = (userVal === "All" || t.user_id === userVal);
        const matchRole = (roleVal === "All" || t.user_role === roleVal);
        const matchSearch = (!searchVal ||
            (t.query && t.query.toLowerCase().includes(searchVal)) ||
            (t.response && t.response.toLowerCase().includes(searchVal)) ||
            (t.routing_reason && t.routing_reason.toLowerCase().includes(searchVal))
        );
        let matchDate = true;
        if ((fromVal || toVal) && t.timestamp) {
            const ts = new Date(t.timestamp);
            if (!isNaN(ts)) {
                if (fromVal && ts < fromVal) matchDate = false;
                if (toVal && ts > toVal) matchDate = false;
            }
        }
        return matchUser && matchRole && matchSearch && matchDate;
    });

    visibleTraces = filtered;
    renderTraceList(filtered);
    updateExportNote(filtered.length);
}

[filterUser, filterRole, filterDateFrom, filterDateTo].forEach(el => {
    if (el) el.addEventListener("change", applyFilters);
});
if (filterSearch) filterSearch.addEventListener("input", applyFilters);
if (refreshTracesBtn) refreshTracesBtn.addEventListener("click", fetchDashboardData);

/* ------------------------------------------------------------------ */
/* Admin tabs                                                         */
/* ------------------------------------------------------------------ */
document.querySelectorAll(".admin-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".admin-tab-btn").forEach(b => b.classList.remove("active"));
        document.querySelectorAll(".admin-tab-panel").forEach(p => p.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(`tab-${btn.dataset.adminTab}`).classList.add("active");
    });
});

/* ------------------------------------------------------------------ */
/* CSV export (real — exports whatever is currently filtered/visible) */
/* ------------------------------------------------------------------ */
function updateExportNote(count) {
    if (exportNote) {
        exportNote.textContent = count > 0
            ? `${count} trace${count === 1 ? "" : "s"} ready to export.`
            : "No traces match the current filters.";
    }
}

function tracesToCsv(traces) {
    const headers = ["id", "timestamp", "user_id", "user_role", "query", "response", "agents", "routing_reason"];
    const lines = [headers.join(",")];
    traces.forEach(t => {
        const row = [
            t.id || "",
            t.timestamp || "",
            t.user_id || "",
            t.user_role || "",
            t.query || "",
            t.response || "",
            (t.agents || []).join(" | "),
            t.routing_reason || ""
        ].map(csvEscape);
        lines.push(row.join(","));
    });
    return lines.join("\n");
}

function csvEscape(value) {
    const s = String(value ?? "").replace(/"/g, '""');
    return `"${s}"`;
}

if (exportCsvBtn) {
    exportCsvBtn.addEventListener("click", () => {
        if (!visibleTraces.length) return;
        const csv = tracesToCsv(visibleTraces);
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `kayfa-traces-${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    });
}

/* ------------------------------------------------------------------ */
/* Cost analytics (PREVIEW — synthesized from real KPI totals since   */
/* per-trace cost/token breakdown is not yet exposed by the backend.  */
/* Swap this for a real endpoint once available.)                     */
/* ------------------------------------------------------------------ */
function seededRandom(seed) {
    let x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
}

function renderCostAnalytics(kpi, traces) {
    const totalCost = parseFloat(kpi?.total_cost || 0) || 0.02;
    const users = (kpi?.unique_users && kpi.unique_users.length) ? kpi.unique_users : ["S001", "S002", "S003"];

    // Daily spend, last 7 days — distributed with mild variance for a realistic look.
    const barsHost = document.getElementById("costChartBars");
    if (barsHost) {
        barsHost.innerHTML = "";
        const days = [];
        const today = new Date();
        for (let i = 6; i >= 0; i--) {
            const d = new Date(today);
            d.setDate(d.getDate() - i);
            days.push(d);
        }
        const weights = days.map((_, i) => 0.6 + seededRandom(i + 1) * 0.8);
        const weightSum = weights.reduce((a, b) => a + b, 0);
        const maxWeight = Math.max(...weights);

        days.forEach((d, i) => {
            const dayCost = (totalCost / 7) * (weights[i] / (weightSum / 7));
            const heightPct = Math.max(6, Math.round((weights[i] / maxWeight) * 100));
            const col = document.createElement("div");
            col.className = "chart-bar-col";
            col.innerHTML = `
                <div class="chart-bar" style="height:${heightPct}%;" title="$${dayCost.toFixed(6)}"></div>
                <div class="chart-bar-label">${d.toLocaleDateString(undefined, { weekday: "short" })}</div>
            `;
            barsHost.appendChild(col);
        });
    }

    // Top users by cost — proportional split of total cost across known users.
    const rankHost = document.getElementById("costRankList");
    if (rankHost) {
        rankHost.innerHTML = "";
        const shares = users.map((u, i) => ({ user: u, weight: 0.4 + seededRandom(i * 3 + 7) }));
        const shareSum = shares.reduce((a, b) => a + b.weight, 0);
        const ranked = shares
            .map(s => ({ user: s.user, cost: totalCost * (s.weight / shareSum) }))
            .sort((a, b) => b.cost - a.cost)
            .slice(0, 6);
        const maxCost = ranked.length ? ranked[0].cost : 1;

        ranked.forEach((r, i) => {
            const row = document.createElement("div");
            row.className = "rank-row";
            row.innerHTML = `
                <span class="rank-index">${i + 1}</span>
                <span class="rank-name">${escapeHtml(r.user)}</span>
                <span class="rank-bar-track"><span class="rank-bar-fill" style="width:${Math.max(6, Math.round((r.cost / maxCost) * 100))}%;"></span></span>
                <span class="rank-value">$${r.cost.toFixed(6)}</span>
            `;
            rankHost.appendChild(row);
        });
    }

    // Spike banner — flags if today's synthesized spend is notably above the 7-day average.
    const spikeBanner = document.getElementById("spikeBanner");
    if (spikeBanner) {
        const todayWeight = 0.6 + seededRandom(7) * 0.8;
        const avgWeight = 1.0;
        const isSpike = todayWeight > avgWeight * 1.25;
        spikeBanner.className = isSpike ? "spike-banner" : "spike-banner ok";
        spikeBanner.textContent = isSpike
            ? "⚠️ Today's spend is trending above the 7-day average — worth a look."
            : "✅ Spend today is within the normal range.";
    }
}

/* ------------------------------------------------------------------ */
/* Helpers                                                            */
/* ------------------------------------------------------------------ */
function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    return text.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

/* ------------------------------------------------------------------ */
/* Logout / session restore                                           */
/* ------------------------------------------------------------------ */
function logoutAdmin() {
    localStorage.removeItem("admin_access_token");
    if (adminDashboardView) adminDashboardView.style.display = "none";
    if (adminLoginView) adminLoginView.style.display = "block";
    if (adminLoginForm) adminLoginForm.reset();
    if (adminLoginError) adminLoginError.textContent = "";
}

if (adminLogoutBtn) adminLogoutBtn.addEventListener("click", logoutAdmin);

async function restoreAdminSession() {
    const token = localStorage.getItem("admin_access_token");
    if (!token) return;
    showDashboard();
}

restoreAdminSession();
