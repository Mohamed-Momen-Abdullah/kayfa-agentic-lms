const API_BASE = "";
const loginView = document.getElementById("loginView");
const dashboardView = document.getElementById("dashboardView");
const loginForm = document.getElementById("loginForm");
const loginError = document.getElementById("loginError");

let currentUser = { id: null, role: null, name: null };
let chatHistory = [];

if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        loginError.textContent = "";

        const userId = document.getElementById("userIdInput").value.trim();
        const role = document.getElementById("roleInput").value;
        const password = document.getElementById("passwordInput").value;

        // Admin Routing override
        if (role === "Admin") {
            try {
                const res = await fetch(`${API_BASE}/api/admin/login`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ email: userId, password: password })
                });
                const data = await res.json();
                if (!res.ok) { loginError.textContent = data.detail || "Invalid admin credentials."; return; }

                localStorage.setItem("admin_token", data.access_token);
                window.location.href = "aou_admin.html"; // Route to STUFF page
            } catch (err) {
                loginError.textContent = "Server connection failed.";
            }
            return;
        }

        // Standard User Login
        try {
            const res = await fetch(`${API_BASE}/api/auth/login`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ user_id: userId, role: role, password: password })
            });
            const data = await res.json();

            if (!res.ok) { loginError.textContent = data.detail || "Invalid credentials."; return; }

            localStorage.setItem("access_token", data.access_token);
            localStorage.setItem("current_user", JSON.stringify(data.user));

            document.getElementById("navUserName").textContent = data.user.name;
            document.getElementById("navUserRole").textContent = data.user.role;

            loginView.style.display = "none";
            dashboardView.style.display = "flex";

            if (document.getElementById("aiMessages").children.length === 0) {
                appendMessage("assistant", "أهلاً! أنا Kayfa AI 👋 كيف يمكنني مساعدتك اليوم؟");
            }
        } catch (err) {
            loginError.textContent = "Server connection failed.";
        }
    });
}

// Full Screen Chat Logic
const aiMessages = document.getElementById("aiMessages");
const aiInputBox = document.getElementById("aiInputBox");
const aiSendBtn = document.getElementById("aiSendBtn");

function appendMessage(role, text) {
    const wrapper = document.createElement("div");
    wrapper.className = `ai-message-wrapper ${role}`;
    const div = document.createElement("div");
    div.className = `ai-msg ${role}`;
    div.textContent = text;
    wrapper.appendChild(div);
    aiMessages.appendChild(wrapper);
    aiMessages.scrollTop = aiMessages.scrollHeight;
    return div;
}

async function sendMessage() {
    const text = aiInputBox.value.trim();
    if (!text) return;
    const token = localStorage.getItem("access_token");

    appendMessage("user", text);
    aiInputBox.value = "";
    const typingEl = appendMessage("typing", "بيكتب...");

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
            body: JSON.stringify({ query: text, history: chatHistory.slice(-6) })
        });
        const data = await res.json();
        typingEl.parentNode.remove();

        if (!res.ok) { appendMessage("assistant", "Error generating response."); return; }

        appendMessage("assistant", data.response);
        chatHistory.push({ role: "user", content: text });
        chatHistory.push({ role: "assistant", content: data.response });
    } catch (err) {
        typingEl.parentNode.remove();
        appendMessage("assistant", "Network Error.");
    }
}

if (aiSendBtn) aiSendBtn.addEventListener("click", sendMessage);
if (aiInputBox) aiInputBox.addEventListener("keydown", (e) => { if (e.key === "Enter") sendMessage(); });

document.getElementById("logoutBtn")?.addEventListener("click", () => {
    localStorage.clear();
    location.reload();
});

// Replace the auto-restore block at the bottom of aou_js.js with this:
async function restoreSession() {
    const token = localStorage.getItem("access_token");
    // If no token exists, stay on the login screen
    if (!token || window.location.pathname.includes("aou_admin")) return;

    try {
        // Verify the token with the FastAPI backend
        const res = await fetch(`${API_BASE}/api/auth/me`, {
            method: "GET",
            headers: { "Authorization": `Bearer ${token}` }
        });

        if (!res.ok) {
            // Token is expired or invalid - clear it and stay on login
            localStorage.removeItem("access_token");
            localStorage.removeItem("current_user");
            return;
        }

        const data = await res.json();

        document.getElementById("navUserName").textContent = data.user.name || "Student";
        document.getElementById("navUserRole").textContent = data.user.role || "User";

        loginView.style.display = "none";
        dashboardView.style.display = "flex";

        if (document.getElementById("aiMessages").children.length === 0) {
            appendMessage("assistant", "أهلاً مجدداً! كيف يمكنني مساعدتك؟");
        }
    } catch (err) {
        console.error("Session restore error:", err);
        localStorage.clear(); // Failsafe if the backend is down
    }
}

// Initialize
restoreSession();