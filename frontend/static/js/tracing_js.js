const ADMIN_API_BASE = "";

const adminLoginView = document.getElementById("adminLoginView");
const adminDashboardView = document.getElementById("adminDashboardView");
const adminLoginForm = document.getElementById("adminLoginForm");
const adminLoginError = document.getElementById("adminLoginError");
const adminLoginButton = document.getElementById("adminLoginButton");
const adminLoginButtonText = document.getElementById("adminLoginButtonText");
const adminLoginSpinner = document.getElementById("adminLoginSpinner");
const toggleAdminPassword = document.getElementById("toggleAdminPassword");
const adminPasswordInput = document.getElementById("adminPasswordInput");
const adminStatus = document.getElementById("adminStatus");
const adminTraceList = document.getElementById("adminTraceList");
const filterUser = document.getElementById("filterUser");
const filterRole = document.getElementById("filterRole");
const filterSearch = document.getElementById("filterSearch");
const refreshTracesBtn = document.getElementById("refreshTracesBtn");
const adminLogoutBtn = document.getElementById("adminLogoutBtn");

let allTraces = [];

if (toggleAdminPassword) {
    toggleAdminPassword.addEventListener("click", () => {
        adminPasswordInput.type = adminPasswordInput.type === "password" ? "text" : "password";
    });
}

if (adminLoginForm) {
    adminLoginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        adminLoginError.textContent = "";

        const email = document.getElementById("adminEmailInput").value.trim();
        const password = adminPasswordInput.value;

        if (!email || !password) {
            adminLoginError.textContent = "من فضلك أدخل الإيميل وكلمة المرور.";
            return;
        }

        adminLoginButton.disabled = true;
        adminLoginButtonText.textContent = "Logging in...";
        adminLoginSpinner.hidden = false;

        try {
            const res = await fetch(`${ADMIN_API_BASE}/api/admin/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email, password }),
            });
            const data = await res.json();

            if (!res.ok) {
                adminLoginError.textContent = data.detail || "Invalid credentials.";
                return;
            }

            localStorage.setItem("admin_token", data.access_token);
            adminLoginView.style.display = "none";
            adminDashboardView.style.display = "block";
            loadDashboard();
        } catch (err) {
            adminLoginError.textContent = "⚠️ تعذر الاتصال بالسيرفر. تأكد أن aou_api.py شغال على port 8000.";
        } finally {
            adminLoginButton.disabled = false;
            adminLoginButtonText.textContent = "Login";
            adminLoginSpinner.hidden = true;
        }
    });
}

async function loadDashboard() {
    const token = localStorage.getItem("admin_token");
    if (!token) {
        adminDashboardView.style.display = "none";
        adminLoginView.style.display = "block";
        return;
    }

    adminStatus.textContent = "🔄 جاري تحميل البيانات من Langfuse...";

    try {
        const res = await fetch(`${ADMIN_API_BASE}/api/admin/dashboard`, {
            method: "GET",
            headers: { "Authorization": `Bearer ${token}` },
        });
        const data = await res.json();

        if (!res.ok) {
            if (res.status === 401 || res.status === 403) {
                localStorage.removeItem("admin_token");
                adminDashboardView.style.display = "none";
                adminLoginView.style.display = "block";
                return;
            }
            adminStatus.textContent = "❌ " + (data.detail || "فشل تحميل البيانات.");
            return;
        }

        allTraces = data.traces || [];
        renderKpi(data.kpi || {});
        populateFilters(allTraces);
        applyFiltersAndRender();
        adminStatus.textContent = `✅ آخر تحديث: ${new Date().toLocaleTimeString()}`;
    } catch (err) {
        console.error("ADMIN DASHBOARD ERROR:", err);
        adminStatus.textContent = "⚠️ تعذر الاتصال بالسيرفر.";
    }
}

function renderKpi(kpi) {
    document.getElementById("kpiTraces").textContent = allTraces.length;
    document.getElementById("kpiUsers").textContent = (kpi.unique_users || []).length;
    document.getElementById("kpiGenerations").textContent = kpi.calls_count ?? "—";
    document.getElementById("kpiTokens").textContent = (kpi.total_tokens ?? 0).toLocaleString();
    document.getElementById("kpiCost").textContent = "$" + (kpi.total_cost ?? 0).toFixed(6);
}

function populateFilters(traces) {
    const users = [...new Set(traces.map(t => t.user_id).filter(Boolean))].sort();
    const roles = [...new Set(traces.map(t => t.user_role).filter(Boolean))].sort();

    filterUser.innerHTML = '<option value="All">All</option>' +
        users.map(u => `<option value="${u}">${u}</option>`).join("");

    filterRole.innerHTML = '<option value="All">All</option>' +
        roles.map(r => `<option value="${r}">${r}</option>`).join("");
}

function applyFiltersAndRender() {
    const userVal = filterUser.value;
    const roleVal = filterRole.value;
    const searchVal = filterSearch.value.trim().toLowerCase();

    const filtered = allTraces.filter(t => {
        if (userVal !== "All" && t.user_id !== userVal) return false;
        if (roleVal !== "All" && t.user_role !== roleVal) return false;
        if (searchVal && !(t.query || "").toLowerCase().includes(searchVal)) return false;
        return true;
    });

    renderTraceList(filtered);
}

[filterUser, filterRole].forEach(el => el.addEventListener("change", applyFiltersAndRender));
filterSearch.addEventListener("input", applyFiltersAndRender);
refreshTracesBtn.addEventListener("click", loadDashboard);

function sentimentChip(sentiment, who) {
    if (!sentiment) return `<span class="admin-sentiment-chip">${who}: —</span>`;
    const label = sentiment.label || "Unknown";
    const confidence = Math.round((sentiment.confidence || 0) * 100);
    let emoji = "⚪";
    if (label.toLowerCase() === "positive") emoji = "🟢";
    else if (label.toLowerCase() === "negative") emoji = "🔴";
    return `<span class="admin-sentiment-chip">${who}: ${emoji} ${label} (${confidence}%)</span>`;
}

function renderTraceList(traces) {
    if (!traces.length) {
        adminTraceList.innerHTML = '<div class="dashboard-status">لا توجد traces مطابقة للفلاتر الحالية.</div>';
        return;
    }

    adminTraceList.innerHTML = traces.map((t, idx) => {
        const query = (t.query || "(no query)").replace(/</g, "&lt;");
        const response = (t.response || "(no response)").replace(/</g, "&lt;");
        const agents = (t.agents || []).join(", ") || "—";

        return `
        <div class="admin-trace-card" data-idx="${idx}">
            <div class="admin-trace-top">
                <div class="admin-trace-query">${query.slice(0, 100)}</div>
                <div class="admin-trace-meta">
                    <span class="admin-trace-badge">👤 ${t.user_id}</span>
                    <span class="admin-trace-badge">🎭 ${t.user_role}</span>
                    <span class="admin-trace-badge">${t.timestamp || ""}</span>
                </div>
            </div>
            <div class="admin-trace-details">
                <div class="admin-trace-section-label">📥 Query</div>
                <div class="admin-trace-box">${query}</div>
                <div class="admin-trace-section-label">📤 Response</div>
                <div class="admin-trace-box">${response}</div>
                <div class="admin-trace-section-label">🔀 Routing</div>
                <div class="admin-trace-box">Agents: ${agents}<br>Reason: ${t.routing_reason || "—"}</div>
                <div class="admin-trace-section-label">❤️ Sentiment</div>
                <div class="admin-sentiment-row">
                    ${sentimentChip(t.user_sentiment, "User")}
                    ${sentimentChip(t.assistant_sentiment, "Assistant")}
                </div>
                ${t.url ? `<div style="margin-top:10px;"><a class="admin-trace-link" href="${t.url}" target="_blank" rel="noopener">🔗 Open in Langfuse</a></div>` : ""}
            </div>
        </div>`;
    }).join("");

    document.querySelectorAll(".admin-trace-card").forEach(card => {
        card.addEventListener("click", () => card.classList.toggle("open"));
    });
}

if (adminLogoutBtn) {
    adminLogoutBtn.addEventListener("click", () => {
        localStorage.removeItem("admin_token");
        adminDashboardView.style.display = "none";
        adminLoginView.style.display = "block";
        adminLoginForm.reset();
    });
}

(function restoreAdminSession() {
    const token = localStorage.getItem("admin_token");
    if (token) {
        adminLoginView.style.display = "none";
        adminDashboardView.style.display = "block";
        loadDashboard();
    }
})();
