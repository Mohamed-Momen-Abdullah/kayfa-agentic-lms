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
let gradesLoaded = false;
let scheduleLoaded = false;

/* ------------------------------------------------------------------ */
/* Toast helper                                                       */
/* ------------------------------------------------------------------ */
function showToast(message) {
    const host = document.getElementById("toastHost");
    if (!host) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    host.appendChild(el);
    setTimeout(() => el.remove(), 2600);
}

/* ------------------------------------------------------------------ */
/* Password visibility                                                */
/* ------------------------------------------------------------------ */
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

/* ------------------------------------------------------------------ */
/* Login                                                               */
/* ------------------------------------------------------------------ */
if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        loginError.textContent = "";

        const userId = document.getElementById("userIdInput").value.trim();
        const role = document.getElementById("roleInput").value;
        const password = document.getElementById("passwordInput").value;

        if (!userId) { loginError.textContent = "Please enter your User ID."; return; }
        if (!role) { loginError.textContent = "Please select your account type."; return; }
        if (!password) { loginError.textContent = "Please enter your password."; return; }

        loginButton.disabled = true;
        if (loginButtonText) loginButtonText.textContent = "Signing in…";
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
            showView("home");
            loginView.style.display = "none";
            dashboardView.style.display = "block";
        } catch (err) {
            loginError.textContent = "⚠️ Could not reach the server. Make sure the API is running.";
        } finally {
            loginButton.disabled = false;
            if (loginButtonText) loginButtonText.textContent = "Sign in";
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

    const statAdvisor = document.getElementById("statAdvisor");
    if (statAdvisor) statAdvisor.textContent = userData.advisor || "—";

    const currentSemester = document.getElementById("currentSemester");
    if (currentSemester) currentSemester.textContent = userData.semester || "—";

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
    } else if (progressPct) {
        progressPct.textContent = "—";
    }

    const statGpa = document.getElementById("statGpa");
    if (statGpa) statGpa.textContent = userData.gpa != null ? userData.gpa : "—";
}

/* ------------------------------------------------------------------ */
/* Tabs & tiles → panel routing                                       */
/* ------------------------------------------------------------------ */
const READY_SERVICES = ["home", "grades", "schedule"];

function showView(service) {
    document.querySelectorAll(".dash-tab").forEach((t) => {
        t.classList.toggle("active", t.dataset.tab === service || (service === "home" && t.dataset.tab === "home"));
    });
    document.querySelectorAll(".tile").forEach((t) => {
        t.classList.toggle("active-tile", t.dataset.service === service);
    });

    const gradesPanel = document.getElementById("gradesPanel");
    const schedulePanel = document.getElementById("schedulePanel");

    if (service === "grades") {
        gradesPanel.style.display = "block";
        schedulePanel.style.display = "none";
        if (!gradesLoaded) loadGrades();
    } else if (service === "schedule") {
        gradesPanel.style.display = "none";
        schedulePanel.style.display = "block";
        if (!scheduleLoaded) loadSchedule();
    } else {
        // "home" and any not-yet-built service: show grades by default under Home
        gradesPanel.style.display = "block";
        schedulePanel.style.display = "none";
        if (!gradesLoaded) loadGrades();
    }
}

document.querySelectorAll(".dash-tab").forEach((tab) => {
    tab.addEventListener("click", (e) => {
        e.preventDefault();
        const service = tab.dataset.tab;
        if (!READY_SERVICES.includes(service)) {
            showToast(`${tab.textContent.trim()} is coming soon.`);
            return;
        }
        showView(service);
    });
});

document.querySelectorAll(".tile").forEach((tile) => {
    tile.addEventListener("click", () => {
        const service = tile.dataset.service;
        if (!READY_SERVICES.includes(service)) {
            const label = tile.querySelector(".tile-label")?.textContent || "This feature";
            showToast(`${label} is coming soon.`);
            return;
        }
        showView(service);
    });
});

/* ------------------------------------------------------------------ */
/* Grades / Schedule data                                             */
/* ------------------------------------------------------------------ */
function gradeChipClass(grade) {
    if (!grade) return "mid";
    const g = grade.toUpperCase();
    if (g.startsWith("A")) return "good";
    if (g === "F" || g.startsWith("D")) return "low";
    return "mid";
}

async function authedGet(path) {
    const token = localStorage.getItem("access_token");
    const res = await fetch(`${API_BASE}${path}`, {
        headers: { "Authorization": `Bearer ${token}` }
    });
    if (res.status === 401) {
        localStorage.removeItem("access_token");
        localStorage.removeItem("current_user");
        loginView.style.display = "block";
        dashboardView.style.display = "none";
        throw new Error("Session expired");
    }
    return res.json();
}

async function loadGrades() {
    const wrap = document.getElementById("gradesTableWrap");
    try {
        const data = await authedGet("/api/academic/grades");
        const grades = data.grades || [];
        gradesLoaded = true;
        if (grades.length === 0) {
            wrap.innerHTML = `<div class="empty-state">No grades on record yet.</div>`;
            return;
        }
        const rows = grades.map(g => `
            <tr>
                <td>${escapeHtml(g.course_id)}</td>
                <td>${escapeHtml(g.title || "—")}</td>
                <td>${g.credits != null ? g.credits : "—"}</td>
                <td>${escapeHtml(g.semester || "—")} ${g.year || ""}</td>
                <td><span class="grade-chip ${gradeChipClass(g.grade)}">${escapeHtml(g.grade || "—")}</span></td>
            </tr>
        `).join("");
        wrap.innerHTML = `
            <table class="data-table">
                <thead><tr><th>Course</th><th>Title</th><th>Credits</th><th>Term</th><th>Grade</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    } catch (err) {
        if (err.message !== "Session expired") {
            wrap.innerHTML = `<div class="empty-state">⚠️ Could not load grades right now.</div>`;
        }
    }
}

async function loadSchedule() {
    const wrap = document.getElementById("scheduleTableWrap");
    try {
        const data = await authedGet("/api/academic/schedule");
        const rows_ = data.schedule || [];
        scheduleLoaded = true;
        if (rows_.length === 0) {
            wrap.innerHTML = `<div class="empty-state">No scheduled sections found.</div>`;
            return;
        }
        const rows = rows_.map(s => {
            const day = s.day != null ? s.day : "—";
            const start = (s.start_hr != null) ? `${String(s.start_hr).padStart(2, "0")}:${String(s.start_min || 0).padStart(2, "0")}` : "—";
            const end = (s.end_hr != null) ? `${String(s.end_hr).padStart(2, "0")}:${String(s.end_min || 0).padStart(2, "0")}` : "—";
            const location = [s.building, s.room_number].filter(Boolean).join(" ");
            return `
                <tr>
                    <td>${escapeHtml(s.course_id)}</td>
                    <td>${escapeHtml(s.title || "—")}</td>
                    <td>${escapeHtml(String(day))}</td>
                    <td>${start} – ${end}</td>
                    <td>${escapeHtml(location || "—")}</td>
                </tr>
            `;
        }).join("");
        wrap.innerHTML = `
            <table class="data-table">
                <thead><tr><th>Course</th><th>Title</th><th>Day</th><th>Time</th><th>Location</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    } catch (err) {
        if (err.message !== "Session expired") {
            wrap.innerHTML = `<div class="empty-state">⚠️ Could not load your schedule right now.</div>`;
        }
    }
}

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
/* AI chat panel                                                      */
/* ------------------------------------------------------------------ */
const aiAvatarBtn = document.getElementById("aiAvatarBtn");
const aiPanel = document.getElementById("aiPanel");
const aiCloseBtn = document.getElementById("aiCloseBtn");
const aiMessages = document.getElementById("aiMessages");
const aiInputBox = document.getElementById("aiInputBox");
const aiSendBtn = document.getElementById("aiSendBtn");
const aiVoiceBtn = document.getElementById("aiVoiceBtn");

let mediaRecorder = null;
let recordedChunks = [];
let isRecording = false;

if (aiAvatarBtn) {
    aiAvatarBtn.addEventListener("click", () => {
        aiPanel.classList.add("open");
        aiAvatarBtn.classList.add("hidden");
        if (aiMessages.children.length === 0) {
            appendMessage("assistant", "Hi! I'm Kayfa AI 👋 Ask me about your grades, schedule, or anything about your studies.");
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
        const label = (sentiment.label || "Unknown").toLowerCase();
        const confidence = Number(sentiment.confidence || 0);
        let emoji = "⚪";
        if (label === "positive") emoji = "🟢";
        else if (label === "negative") emoji = "🔴";
        badge.textContent = `${emoji} ${sentiment.label || "Unknown"} (${Math.round(confidence * 100)}%)`;
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
        appendMessage("assistant", "⚠️ Your session has expired. Please sign in again.");
        return;
    }

    appendMessage("user", text);
    aiInputBox.value = "";

    const typingWrapper = appendMessage("typing", "Typing…");
    typingWrapper.parentElement.classList.add("typing");

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

        typingWrapper.parentElement.remove();

        if (!res.ok) {
            if (res.status === 401) {
                localStorage.removeItem("access_token");
                localStorage.removeItem("current_user");
                appendMessage("assistant", "⚠️ Your session has expired. Please sign in again.");
                return;
            }
            appendMessage("assistant", data.detail || "Sorry, something went wrong with that reply.");
            return;
        }

        appendMessage("assistant", data.response || "Sorry, something went wrong with that reply.", data.sentiment || null);

        chatHistory.push({ role: "user", content: text });
        chatHistory.push({ role: "assistant", content: data.response || "" });
    } catch (err) {
        if (typingWrapper && typingWrapper.parentElement) typingWrapper.parentElement.remove();
        appendMessage("assistant", "⚠️ Could not reach the AI server. Make sure the API is running.");
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

async function sendAudioToAI(blob) {
    const token = localStorage.getItem("access_token");
    if (!token) {
        appendMessage("assistant", "⚠️ Your session has expired. Please sign in again.");
        return;
    }

    const typingWrapper = appendMessage("typing", "Listening and transcribing…");
    typingWrapper.parentElement.classList.add("typing");

    try {
        const formData = new FormData();
        formData.append("file", blob, "voice-recording.webm");

        const res = await fetch(`${API_BASE}/api/chat/audio`, {
            method: "POST",
            headers: { "Authorization": `Bearer ${token}` },
            body: formData
        });

        const data = await res.json();
        typingWrapper.parentElement.remove();

        if (!res.ok) {
            if (res.status === 401) {
                localStorage.removeItem("access_token");
                localStorage.removeItem("current_user");
                appendMessage("assistant", "⚠️ Your session has expired. Please sign in again.");
                return;
            }
            appendMessage("assistant", data.detail || "Could not process the audio.");
            return;
        }

        appendMessage("assistant", data.response || "Sorry, something went wrong with that reply.", data.sentiment || null);
        chatHistory.push({ role: "user", content: "[audio_message]" });
        chatHistory.push({ role: "assistant", content: data.response || "" });
    } catch (err) {
        if (typingWrapper && typingWrapper.parentElement) typingWrapper.parentElement.remove();
        appendMessage("assistant", "⚠️ Could not send the audio to the server.");
    }
}

async function toggleVoiceRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        appendMessage("assistant", "⚠️ This browser does not support voice recording.");
        return;
    }

    if (isRecording) {
        if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
        isRecording = false;
        if (aiVoiceBtn) {
            aiVoiceBtn.classList.remove("is-recording");
            aiVoiceBtn.textContent = "🎙️";
            aiVoiceBtn.setAttribute("aria-label", "Record voice");
        }
        return;
    }

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
        mediaRecorder = new MediaRecorder(stream, { mimeType });
        recordedChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) recordedChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(recordedChunks, { type: mimeType });
            stream.getTracks().forEach((track) => track.stop());
            if (audioBlob.size > 0) await sendAudioToAI(audioBlob);
        };

        mediaRecorder.start();
        isRecording = true;
        if (aiVoiceBtn) {
            aiVoiceBtn.classList.add("is-recording");
            aiVoiceBtn.textContent = "■";
            aiVoiceBtn.setAttribute("aria-label", "Stop recording");
        }

        appendMessage("assistant", "🎙️ Recording… tap again to stop and send.");
    } catch (err) {
        console.error("Microphone access error:", err);
        appendMessage("assistant", "⚠️ Could not access the microphone. Check your browser permissions.");
    }
}

if (aiVoiceBtn) aiVoiceBtn.addEventListener("click", toggleVoiceRecording);

/* ------------------------------------------------------------------ */
/* Logout / session restore                                           */
/* ------------------------------------------------------------------ */
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
        gradesLoaded = false;
        scheduleLoaded = false;

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
        populateDashboard({ ...userInfo, ...storedUser, id: currentUser.id, role: currentUser.role, name: currentUser.name });
        showView("home");
        loginView.style.display = "none";
        dashboardView.style.display = "block";
    } catch (err) {
        console.error("Session restore error:", err);
    }
}

restoreSession();
