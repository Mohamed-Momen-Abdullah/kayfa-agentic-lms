const API_BASE = "";
const loginView = document.getElementById("loginView");
const dashboardView = document.getElementById("dashboardView");
const loginForm = document.getElementById("loginForm");
const loginError = document.getElementById("loginError");
const togglePassword = document.getElementById("togglePassword");
const passwordInput = document.getElementById("passwordInput");
const loginButton = document.getElementById("loginButton");
const loginButtonText = document.getElementById("loginButtonText");
const loginSpinner = document.getElementById("loginSpinner");
const roleContent = document.getElementById("roleContent");
const dashboardStatus = document.getElementById("dashboardStatus");

let currentUser = { id: null, role: null, name: null };
let chatHistory = [];

function authHeaders() {
    const token = localStorage.getItem("access_token");
    return token ? { "Authorization": `Bearer ${token}` } : {};
}

if (togglePassword) {
    togglePassword.addEventListener("click", () => {
        if (passwordInput.type === "password") {
            passwordInput.type = "text";
            togglePassword.setAttribute("aria-label", "Hide password");
        } else {
            passwordInput.type = "password";
            togglePassword.setAttribute("aria-label", "Show password");
        }
    });
}

if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        loginError.textContent = "";

        const username = document.getElementById("usernameInput").value.trim();
        const role = document.getElementById("roleInput").value;
        const password = document.getElementById("passwordInput").value;

        if (!username) { loginError.textContent = "Please enter your username."; return; }
        if (!role) { loginError.textContent = "Please select your account type."; return; }
        if (!password) { loginError.textContent = "Please enter your password."; return; }

        loginButton.disabled = true;
        if (loginButtonText) loginButtonText.textContent = "Logging in...";
        if (loginSpinner) loginSpinner.hidden = false;

        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: username, role: role, password: password })
            });
            const data = await res.json();

            if (!res.ok) {
                loginError.textContent = data.detail || "Invalid credentials.";
                return;
            }

            localStorage.setItem("access_token", data.access_token);
            localStorage.setItem("current_user", JSON.stringify(data.user));

            currentUser = { id: data.user.id, role: data.user.role, name: data.user.name };

            populateNav(data.user);
            loginView.style.display = "none";
            dashboardView.style.display = "block";
            loadReport();
        } catch (err) {
            loginError.textContent = "⚠️ Could not reach the server. Make sure the API is running.";
        } finally {
            loginButton.disabled = false;
            if (loginButtonText) loginButtonText.textContent = "Login";
            if (loginSpinner) loginSpinner.hidden = true;
        }
    });
}

function populateNav(userData) {
    const navUserId = document.getElementById("navUserId");
    const navUserName = document.getElementById("navUserName");
    const navUserRole = document.getElementById("navUserRole");
    if (navUserId) navUserId.textContent = userData.id || "—";
    if (navUserName) navUserName.textContent = userData.name || "—";
    if (navUserRole) navUserRole.textContent = userData.role || "—";
}

async function loadReport() {
    dashboardStatus.textContent = "Loading your dashboard...";
    roleContent.innerHTML = "";
    try {
        const res = await fetch(`${API_BASE}/api/report`, { headers: authHeaders() });
        if (!res.ok) {
            if (res.status === 401) return handleUnauthorized();
            dashboardStatus.textContent = "Could not load your report.";
            return;
        }
        const data = await res.json();
        dashboardStatus.textContent = "";
        if (currentUser.role === "Student") renderStudent(data);
        else if (currentUser.role === "Instructor") renderInstructor(data);
        else if (currentUser.role === "Admin") renderAdmin(data);
    } catch (err) {
        dashboardStatus.textContent = "⚠️ Could not reach the server.";
    }
}

function renderStudent(data) {
    const courses = data.courses || [];
    let html = `
    <section class="info-card">
        <div class="info-left">
            <h2>👤 ${data.full_name || "—"}</h2>
            <div class="info-stats">
                <div class="stat-item"><span class="stat-label">Department:</span><span class="stat-value">${data.department || "—"}</span></div>
                <div class="stat-item"><span class="stat-label">Enrolled Courses:</span><span class="stat-value">${data.enrolled_courses_count || 0}</span></div>
                <div class="stat-item"><span class="stat-label">Average Grade:</span><span class="stat-value">${data.average_grade || 0}/100</span></div>
                <div class="stat-item"><span class="stat-label">Average Attendance:</span><span class="stat-value">${data.average_attendance || 0}%</span></div>
            </div>
        </div>
    </section>
    <h3 class="section-title">My Courses</h3>
    <div class="course-list">`;
    courses.forEach(c => {
        html += `
        <div class="course-card">
            <div class="course-card-top">
                <b>${c.code} - ${c.title}</b>
                <span class="course-grade">${c.final_grade != null ? c.final_grade + "/100" : "No grade yet"}</span>
            </div>
            <p class="course-desc">${c.description || ""}</p>
            <div class="progress-bar-outer"><div class="progress-bar-inner" style="width:${c.progress_percent || 0}%"></div></div>
            <span class="course-progress-label">${c.progress_percent || 0}% complete</span>
        </div>`;
    });
    html += `</div>`;

    html += `
    <h3 class="section-title">Practice Quiz</h3>
    <div class="quiz-box">
        <div class="quiz-controls">
            <select id="quizCourseSelect" class="admin-select">
                ${courses.map(c => `<option value="${c.id}">${c.code} - ${c.title}</option>`).join("")}
            </select>
            <button type="button" class="btn-login" id="generateQuizBtn" style="width:auto;padding:10px 18px;">Generate Practice Quiz</button>
        </div>
        <div id="quizArea"></div>
    </div>`;

    roleContent.innerHTML = html;

    const generateBtn = document.getElementById("generateQuizBtn");
    if (generateBtn) generateBtn.addEventListener("click", generateQuiz);
}

let currentQuiz = { course_id: null, questions: [], answers: {} };

async function generateQuiz() {
    const courseId = document.getElementById("quizCourseSelect").value;
    const quizArea = document.getElementById("quizArea");
    quizArea.innerHTML = `<p class="quiz-status">Generating questions...</p>`;
    try {
        const res = await fetch(`${API_BASE}/api/quiz/generate`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ course_id: courseId })
        });
        const data = await res.json();
        if (!res.ok) {
            quizArea.innerHTML = `<p class="quiz-status error">${data.detail || "Could not generate quiz."}</p>`;
            return;
        }
        currentQuiz = { course_id: courseId, questions: data.questions, answers: {} };
        renderQuiz();
    } catch (err) {
        quizArea.innerHTML = `<p class="quiz-status error">⚠️ Could not reach the server.</p>`;
    }
}

function renderQuiz() {
    const quizArea = document.getElementById("quizArea");
    let html = "";
    currentQuiz.questions.forEach((q, i) => {
        html += `<div class="quiz-question"><p class="quiz-question-text">${i + 1}. ${q.question}</p>`;
        q.options.forEach((opt, j) => {
            html += `
            <label class="quiz-option">
                <input type="radio" name="q${i}" value="${j}">
                ${opt}
            </label>`;
        });
        html += `</div>`;
    });
    html += `<button type="button" class="btn-login" id="submitQuizBtn" style="width:auto;padding:10px 18px;">Submit Quiz</button>`;
    quizArea.innerHTML = html;

    currentQuiz.questions.forEach((_, i) => {
        document.querySelectorAll(`input[name="q${i}"]`).forEach(radio => {
            radio.addEventListener("change", (e) => {
                currentQuiz.answers[i] = e.target.value;
            });
        });
    });

    document.getElementById("submitQuizBtn").addEventListener("click", submitQuiz);
}

async function submitQuiz() {
    const quizArea = document.getElementById("quizArea");
    try {
        const res = await fetch(`${API_BASE}/api/quiz/submit`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ course_id: currentQuiz.course_id, answers: currentQuiz.answers })
        });
        const data = await res.json();
        if (!res.ok) {
            quizArea.innerHTML += `<p class="quiz-status error">${data.detail || "Could not submit quiz."}</p>`;
            return;
        }
        quizArea.innerHTML = `<p class="quiz-status success">You scored ${data.correct}/${data.total} (${data.score}/10). This has been added to your grades.</p>`;
        loadReport();
    } catch (err) {
        quizArea.innerHTML += `<p class="quiz-status error">⚠️ Could not reach the server.</p>`;
    }
}

function renderInstructor(data) {
    const courses = data.courses || [];
    let html = `
    <section class="info-card">
        <div class="info-left">
            <h2>👤 ${data.full_name || "—"}</h2>
            <div class="info-stats">
                <div class="stat-item"><span class="stat-label">Department:</span><span class="stat-value">${data.department || "—"}</span></div>
                <div class="stat-item"><span class="stat-label">Courses Teaching:</span><span class="stat-value">${data.courses_teaching || 0}</span></div>
                <div class="stat-item"><span class="stat-label">Total Students:</span><span class="stat-value">${data.total_students || 0}</span></div>
                <div class="stat-item"><span class="stat-label">Average Class Grade:</span><span class="stat-value">${data.average_class_grade || 0}/100</span></div>
            </div>
        </div>
    </section>
    <h3 class="section-title">My Courses & Rosters</h3>`;

    courses.forEach(c => {
        html += `
        <div class="course-card">
            <div class="course-card-top">
                <b>${c.code} - ${c.title}</b>
                <span class="course-grade">${c.enrolled_count} students | avg ${c.average_grade}/100</span>
            </div>
            <table class="roster-table">
                <thead><tr><th>Student</th><th>Final Grade</th></tr></thead>
                <tbody>
                    ${(c.roster || []).map(r => `<tr><td>${r.name}</td><td>${r.final_grade != null ? r.final_grade + "/100" : "No grade yet"}</td></tr>`).join("")}
                </tbody>
            </table>
        </div>`;
    });

    roleContent.innerHTML = html;
}

function renderAdmin(data) {
    const kpi = data.kpi || { calls_count: 0, total_tokens: 0, total_cost: 0, unique_users: [] };
    const traces = data.traces || [];

    let html = `
    <section class="admin-kpi-grid">
        <div class="admin-kpi-card"><div class="admin-kpi-label">📞 Total Calls</div><div class="admin-kpi-value">${kpi.calls_count}</div></div>
        <div class="admin-kpi-card"><div class="admin-kpi-label">🔢 Total Tokens</div><div class="admin-kpi-value">${kpi.total_tokens}</div></div>
        <div class="admin-kpi-card"><div class="admin-kpi-label">💰 Total Cost</div><div class="admin-kpi-value">$${kpi.total_cost.toFixed(4)}</div></div>
        <div class="admin-kpi-card"><div class="admin-kpi-label">👥 Active Users</div><div class="admin-kpi-value">${kpi.unique_users.length}</div></div>
    </section>
    <h3 class="section-title">Recent Conversations</h3>
    <section class="admin-trace-list">`;

    traces.slice(0, 30).forEach(t => {
        html += `
        <div class="admin-trace-card">
            <div class="admin-trace-top">
                <span class="admin-trace-query">${t.query || ""}</span>
                <span class="admin-trace-meta">${t.user_role || ""} - ${t.user_id || ""}</span>
            </div>
            <p>${t.response || ""}</p>
        </div>`;
    });

    html += `</section>`;
    if (data.status === "error") {
        html = `<p class="quiz-status error">${data.error || "Observability data is not available."}</p>` + html;
    }
    roleContent.innerHTML = html;
}

function handleUnauthorized() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("current_user");
    dashboardView.style.display = "none";
    loginView.style.display = "block";
}

const aiAvatarBtn = document.getElementById("aiAvatarBtn");
const aiPanel = document.getElementById("aiPanel");
const aiCloseBtn = document.getElementById("aiCloseBtn");
const aiMessages = document.getElementById("aiMessages");
const aiInputBox = document.getElementById("aiInputBox");
const aiSendBtn = document.getElementById("aiSendBtn");

if (aiAvatarBtn) {
    aiAvatarBtn.addEventListener("click", () => {
        aiPanel.classList.add("open");
        aiAvatarBtn.classList.add("hidden");
        if (aiMessages.children.length === 0) {
            appendMessage("assistant", "أهلاً! أنا Kayfa AI 👋 اسألني عن دراستك أو أي حاجة تخص المنصة.");
        }
    });
}
if (aiCloseBtn) {
    aiCloseBtn.addEventListener("click", () => {
        aiPanel.classList.remove("open");
        aiAvatarBtn.classList.remove("hidden");
    });
}

function appendMessage(role, text, sentiment = null) {
    const wrapper = document.createElement("div");
    wrapper.className = `ai-message-wrapper ${role}`;

    const div = document.createElement("div");
    div.className = `ai-msg ${role}`;
    div.textContent = text;
    wrapper.appendChild(div);

    if (sentiment) {
        const badge = document.createElement("div");
        badge.className = "sentiment-badge";
        const label = sentiment.label || "Unknown";
        const confidence = Number(sentiment.confidence || 0);

        let emoji = "⚪";
        let textLabel = label;

        if (label.toLowerCase() === "positive") { emoji = "🟢"; textLabel = "إيجابي"; }
        else if (label.toLowerCase() === "negative") { emoji = "🔴"; textLabel = "سلبي"; }
        else if (label.toLowerCase() === "neutral") { emoji = "⚪"; textLabel = "محايد"; }

        badge.textContent = `${emoji} ${textLabel} (${Math.round(confidence * 100)}%)`;
        wrapper.appendChild(badge);
    }

    aiMessages.appendChild(wrapper);
    aiMessages.scrollTop = aiMessages.scrollHeight;
    return div;
}

async function sendMessage() {
    const text = aiInputBox.value.trim();
    if (!text) return;

    if (!localStorage.getItem("access_token")) {
        appendMessage("assistant", "⚠️ Your session expired. Please log in again.");
        return;
    }

    appendMessage("user", text);
    aiInputBox.value = "";

    const typingEl = appendMessage("typing", "بيكتب...");
    typingEl.classList.add("typing");

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...authHeaders() },
            body: JSON.stringify({ query: text, history: chatHistory.slice(-6) })
        });
        const data = await res.json();

        typingEl.remove();

        if (!res.ok) {
            if (res.status === 401) return handleUnauthorized();
            appendMessage("assistant", data.detail || "معلش، حصل خطأ في الرد.");
            return;
        }

        appendMessage("assistant", data.response || "معلش، حصل خطأ في الرد.", data.sentiment || null);

        chatHistory.push({ role: "user", content: text });
        chatHistory.push({ role: "assistant", content: data.response || "" });
    } catch (err) {
        if (typingEl && typingEl.parentNode) typingEl.remove();
        appendMessage("assistant", "⚠️ تعذر الاتصال بالـ AI server.");
    }
}

if (aiSendBtn) aiSendBtn.addEventListener("click", sendMessage);
if (aiInputBox) {
    aiInputBox.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); sendMessage(); }
    });
}

const logoutBtn = document.getElementById("logoutBtn");
if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
        try {
            await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", headers: authHeaders() });
        } catch (err) { console.error("Logout error:", err); }

        localStorage.removeItem("access_token");
        localStorage.removeItem("current_user");
        currentUser = { id: null, role: null, name: null };
        chatHistory = [];

        dashboardView.style.display = "none";
        loginView.style.display = "block";
        loginForm.reset();
        loginError.textContent = "";
    });
}

async function restoreSession() {
    const token = localStorage.getItem("access_token");
    if (!token) return;
    try {
        const res = await fetch(`${API_BASE}/api/auth/me`, { headers: authHeaders() });
        if (!res.ok) return handleUnauthorized();

        const data = await res.json();
        currentUser = { id: data.user.id, role: data.user.role, name: data.user.name };
        populateNav(data.user);
        loginView.style.display = "none";
        dashboardView.style.display = "block";
        loadReport();
    } catch (err) {
        console.error("Session restore error:", err);
    }
}

restoreSession();
