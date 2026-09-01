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
const refreshTracesBtn = document.getElementById("refreshTracesBtn");

let allTraces = [];

// Password Visibility Toggle
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

// Admin Form Submission Login
if (adminLoginForm) {
    adminLoginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (adminLoginError) adminLoginError.textContent = "";

        const email = document.getElementById("adminEmailInput").value.trim();
        const password = document.getElementById("adminPasswordInput").value;

        if (adminLoginButton) adminLoginButton.disabled = true;
        if (adminLoginButtonText) adminLoginButtonText.textContent = "Logging in...";
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
            if (adminLoginButtonText) adminLoginButtonText.textContent = "Login";
            if (adminLoginSpinner) adminLoginSpinner.hidden = true;
        }
    });
}

// Show Dashboard & Fetch Data
async function showDashboard() {
    if (adminLoginView) adminLoginView.style.display = "none";
    if (adminDashboardView) adminDashboardView.style.display = "block";
    document.body.classList.remove("auth-pending"); // Reveal page
    await fetchDashboardData();
}

// Fetch Traces and KPI data from backend
async function fetchDashboardData() {
    const token = localStorage.getItem("admin_access_token");
    const adminStatus = document.getElementById("adminStatus");
    if (!token) return;

    if (adminStatus) adminStatus.innerHTML = "<b>Loading dashboard data...</b>";

    try {
        const res = await fetch(`${API_BASE}/api/admin/dashboard`, {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (res.status === 401 || res.status === 403) {
            logoutAdmin();
            return;
        }

        const data = await res.json();
        if (data.status === "success") {
            if (adminStatus) adminStatus.innerHTML = "";
            allTraces = data.traces || [];
            updateKPIs(data.kpi, allTraces.length);
            populateFilters(allTraces);
            renderTraceList(allTraces);
        } else {
            if (adminStatus) adminStatus.innerHTML = `<span style="color:#d9534f;">⚠️ Error: ${data.error || 'Failed to fetch data'}</span>`;
        }
    } catch (err) {
        if (adminStatus) adminStatus.innerHTML = `<span style="color:#d9534f;">⚠️ Connection error.</span>`;
    }
}

// KPI Grid Rendering
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
    
    // Formats cost value
    let totalCostVal = parseFloat(kpi.total_cost || 0);
    if (kpiCost) kpiCost.textContent = `$${totalCostVal.toFixed(6)}`;
}

// Populate Filters user_id and user_role list dynamically
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

// Trace List Generation Layout
function renderTraceList(traces) {
    const listContainer = document.getElementById("adminTraceList");
    if (!listContainer) return;

    listContainer.innerHTML = "";

    if (traces.length === 0) {
        listContainer.innerHTML = '<div style="background:#fff;border-radius:12px;padding:24px;text-align:center;color:var(--aou-muted);">No traces match the current filter.</div>';
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
            if (t.timestamp) {
                const date = new Date(t.timestamp);
                timeStr = date.toLocaleString();
            }
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
                <div class="admin-trace-section-label">User Query Sentiment</div>
                <div class="admin-sentiment-row" style="margin-bottom:12px;">
                    <span class="admin-sentiment-chip">${uSentEmoji} User: ${uSent.label} (${Math.round((uSent.confidence || 0) * 100)}%)</span>
                    <span class="admin-sentiment-chip">${aSentEmoji} Assistant: ${aSent.label} (${Math.round((aSent.confidence || 0) * 100)}%)</span>
                </div>
                
                <div class="admin-trace-section-label">Active Agents</div>
                <div style="margin-bottom: 12px;">
                    ${t.agents && t.agents.length > 0
                        ? t.agents.map(a => `<span class="admin-trace-badge" style="margin-right:6px;display:inline-block;margin-bottom:4px;">${escapeHtml(a)}</span>`).join("")
                        : '<span class="admin-trace-badge">None</span>'}
                </div>
                
                ${t.routing_reason ? `
                    <div class="admin-trace-section-label">Routing Reason</div>
                    <div class="admin-trace-box" style="margin-bottom:12px;">${escapeHtml(t.routing_reason)}</div>
                ` : ""}
                
                <div class="admin-trace-section-label">AI Response</div>
                <div class="admin-trace-box" style="margin-bottom:12px;">${escapeHtml(t.response || "No response generated")}</div>
                
                <div style="margin-top:14px;text-align:right;">
                    <a href="${t.url}" target="_blank" class="admin-trace-link" style="color:var(--aou-blue);text-decoration:none;">🔍 View Trace in Langfuse ↗</a>
                </div>
            </div>
        `;

        listContainer.appendChild(card);
    });
}

// Client-side Filters logic
function applyFilters() {
    const userVal = filterUser ? filterUser.value : "All";
    const roleVal = filterRole ? filterRole.value : "All";
    const searchVal = filterSearch ? filterSearch.value.trim().toLowerCase() : "";

    const filtered = allTraces.filter(t => {
        const matchUser = (userVal === "All" || t.user_id === userVal);
        const matchRole = (roleVal === "All" || t.user_role === roleVal);
        const matchSearch = (!searchVal || 
            (t.query && t.query.toLowerCase().includes(searchVal)) || 
            (t.response && t.response.toLowerCase().includes(searchVal)) ||
            (t.routing_reason && t.routing_reason.toLowerCase().includes(searchVal))
        );
        return matchUser && matchRole && matchSearch;
    });

    renderTraceList(filtered);
}

// Register Filter listeners
if (filterUser) filterUser.addEventListener("change", applyFilters);
if (filterRole) filterRole.addEventListener("change", applyFilters);
if (filterSearch) filterSearch.addEventListener("input", applyFilters);
if (refreshTracesBtn) refreshTracesBtn.addEventListener("click", fetchDashboardData);

// Safety escape HTML string
function escapeHtml(text) {
    if (!text) return "";
    return text.toString()
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Admin logout functionality
function logoutAdmin() {
    localStorage.removeItem("admin_access_token");
    if (adminDashboardView) adminDashboardView.style.display = "none";
    if (adminLoginView) adminLoginView.style.display = "block";
    document.body.classList.remove("auth-pending"); // Reveal login form
    if (adminLoginForm) adminLoginForm.reset();
    if (adminLoginError) adminLoginError.textContent = "";
}

if (adminLogoutBtn) {
    adminLogoutBtn.addEventListener("click", logoutAdmin);
}

// Session Restore
async function restoreAdminSession() {
    const token = localStorage.getItem("admin_access_token");
    if (!token) {
        // No session — show login form and reveal the page
        if (adminLoginView) adminLoginView.style.display = "";
        document.body.classList.remove("auth-pending");
        return;
    }
    showDashboard();
}

restoreAdminSession();