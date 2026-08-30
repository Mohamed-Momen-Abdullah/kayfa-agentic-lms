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

let currentUser = { id: null, role: null, name: null };
let chatHistory = [];

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

        const userId = document.getElementById("userIdInput").value.trim();
        const role = document.getElementById("roleInput").value;
        const password = document.getElementById("passwordInput").value;

        if (!userId) { loginError.textContent = "من فضلك أدخل الـ User ID."; return; }
        if (!role) { loginError.textContent = "من فضلك اختر نوع الحساب."; return; }
        if (!password) { loginError.textContent = "من فضلك أدخل كلمة المرور."; return; }

        loginButton.disabled = true;
        if (loginButtonText) loginButtonText.textContent = "Logging in...";
        if (loginSpinner) loginSpinner.hidden = false;

        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ user_id: userId, role: role, password: password })
            });
            const data = await res.json();

            if (!res.ok) {
                loginError.textContent = data.detail || "Invalid credentials.";
                return;
            }
            if (!data.access_token) {
                loginError.textContent = "Login succeeded but no access token was returned.";
                return;
            }

            localStorage.setItem("access_token", data.access_token);
            localStorage.setItem("current_user", JSON.stringify(data.user));

            currentUser = { id: data.user.id, role: data.user.role, name: data.user.name };

            populateDashboard(data.user);
            loginView.style.display = "none";
            dashboardView.style.display = "block";
        } catch (err) {
            loginError.textContent = "⚠️ تعذر الاتصال بالسيرفر. تأكد أن AOU_API.py شغال على port 8000.";
        } finally {
            loginButton.disabled = false;
            if (loginButtonText) loginButtonText.textContent = "Login";
            if (loginSpinner) loginSpinner.hidden = true;
        }
    });
}

function populateDashboard(userData) {
    const navUserId = document.getElementById("navUserId");
    const navUserName = document.getElementById("navUserName");
    const navUserRole = document.getElementById("navUserRole");

    if (navUserId) navUserId.textContent = userData.id || "—";
    if (navUserName) navUserName.textContent = userData.name || "—";
    if (navUserRole) navUserRole.textContent = userData.role || "—";

    const cardUserId = document.getElementById("cardUserId");
    const cardUserName = document.getElementById("cardUserName");
    const cardProgram = document.getElementById("cardProgram");
    const cardRole = document.getElementById("cardRole");

    if (cardUserId) cardUserId.textContent = userData.id || "—";
    if (cardUserName) cardUserName.textContent = userData.name || "—";
    if (cardProgram) cardProgram.textContent = userData.dept_name || "—";
    if (cardRole) cardRole.textContent = userData.role || "—";

    const statDepartment = document.getElementById("statDepartment");
    if (statDepartment) statDepartment.textContent = userData.dept_name || "—";

    const statHours = document.getElementById("statHours");
    const progressHours = document.getElementById("progressHours");
    const hours = userData.tot_cred;

    if (statHours) statHours.textContent = hours != null ? hours : "—";
    if (progressHours) progressHours.textContent = hours != null ? hours : "—";

    const progressPct = document.getElementById("progressPct");
    const progressRing = document.getElementById("progressRing");

    if (hours != null) {
        const pct = Math.min(100, Math.round(Number(hours) / 1.4));
        if (progressPct) progressPct.textContent = `${pct}%`;
        if (progressRing) progressRing.style.setProperty("--pct", `${pct * 3.6}deg`);
    } else {
        if (progressPct) progressPct.textContent = "—";
    }

    const statGpa = document.getElementById("statGpa");
    if (statGpa) statGpa.textContent = userData.gpa != null ? userData.gpa : "—";
}

document.querySelectorAll(".dash-tab").forEach((tab) => {
    tab.addEventListener("click", (e) => {
        e.preventDefault();
        document.querySelectorAll(".dash-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
    });
});

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
            appendMessage("assistant", "أهلاً! أنا CampusX AI 👋 اسألني عن دراستك أو أي حاجة تخص الجامعة.");
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

        if (label.toLowerCase() === "positive") {
            emoji = "🟢"; textLabel = "إيجابي";
        } else if (label.toLowerCase() === "negative") {
            emoji = "🔴"; textLabel = "سلبي";
        } else if (label.toLowerCase() === "neutral") {
            emoji = "⚪"; textLabel = "محايد";
        }

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

    const token = localStorage.getItem("access_token");
    if (!token) {
        appendMessage("assistant", "⚠️ انتهت جلسة الدخول. من فضلك سجل الدخول مرة أخرى.");
        return;
    }

    appendMessage("user", text);
    aiInputBox.value = "";

    const typingEl = appendMessage("typing", "بيكتب...");
    typingEl.classList.add("typing");

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({ query: text, history: chatHistory.slice(-6) })
        });
        const data = await res.json();

        typingEl.remove();

        if (!res.ok) {
            if (res.status === 401) {
                localStorage.removeItem("access_token");
                localStorage.removeItem("current_user");
                appendMessage("assistant", "⚠️ انتهت جلسة الدخول. سجل الدخول مرة أخرى.");
                return;
            }
            appendMessage("assistant", data.detail || "معلش، حصل خطأ في الرد.");
            return;
        }

        appendMessage("assistant", data.response || "معلش، حصل خطأ في الرد.", data.sentiment || null);

        chatHistory.push({ role: "user", content: text });
        chatHistory.push({ role: "assistant", content: data.response || "" });
    } catch (err) {
        if (typingEl && typingEl.parentNode) typingEl.remove();
        appendMessage("assistant", "⚠️ تعذر الاتصال بالـ AI server. تأكد أن API شغال.");
    }
}

if (aiSendBtn) aiSendBtn.addEventListener("click", sendMessage);
if (aiInputBox) {
    aiInputBox.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            sendMessage();
        }
    });
}

const logoutBtn = document.getElementById("logoutBtn");
if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
        const token = localStorage.getItem("access_token");
        try {
            if (token) {
                await fetch(`${API_BASE}/api/auth/logout`, {
                    method: "POST",
                    headers: { "Authorization": `Bearer ${token}` }
                });
            }
        } catch (err) {
            console.error("Logout error:", err);
        }

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
        const res = await fetch(`${API_BASE}/api/auth/me`, {
            method: "GET",
            headers: { "Authorization": `Bearer ${token}` }
        });

        if (!res.ok) {
            localStorage.removeItem("access_token");
            localStorage.removeItem("current_user");
            return;
        }

        const data = await res.json();
        const userInfo = data.user;
        const storedUser = JSON.parse(localStorage.getItem("current_user") || "{}");

        currentUser = {
            id: storedUser.id || userInfo.student_id || userInfo.instructor_id,
            role: storedUser.role || "Student",
            name: storedUser.name || userInfo.name
        };
        populateDashboard({ ...userInfo, id: currentUser.id, role: currentUser.role, name: currentUser.name });
        loginView.style.display = "none";
        dashboardView.style.display = "block";
    } catch (err) {
        console.error("Session restore error:", err);
    }
}

restoreSession();
