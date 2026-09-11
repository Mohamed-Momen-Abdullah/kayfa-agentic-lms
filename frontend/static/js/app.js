/* ==========================================================================
   Kayfa portal — single-page app shell
   ========================================================================== */
const API = "/api";

const state = {
  token: localStorage.getItem("kayfa_token") || null,
  user: JSON.parse(localStorage.getItem("kayfa_user") || "null"),
  view: null,
  chatHistory: [],       // [{role, content}]
  activeQuiz: null,      // {courseId, courseTitle, questions, quizToken, selected: {}}
  isChatBusy: false,
};

const ICONS = {
  dashboard: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>`,
  chat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>`,
  quiz: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 0 1 5 0c0 1.7-2.2 2-2.4 3.5"/><circle cx="12" cy="16.3" r="0.3" fill="currentColor"/></svg>`,
  observability: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 15l3.5-4 3 3L19 8"/></svg>`,
  mic: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0"/><line x1="12" y1="19" x2="12" y2="22"/></svg>`,
  send: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`,
  speaker: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/></svg>`,
};

const NAV = {
  Student: [
    { id: "dashboard", label: "Dashboard", icon: "dashboard" },
    { id: "chat", label: "Ask Kayfa", icon: "chat" },
    { id: "quiz", label: "Practice Quiz", icon: "quiz" },
  ],
  Instructor: [
    { id: "dashboard", label: "Dashboard", icon: "dashboard" },
    { id: "chat", label: "Ask Kayfa", icon: "chat" },
  ],
  Admin: [
    { id: "dashboard", label: "Observability", icon: "observability" },
  ],
};

const QUICK_PROMPTS = [
  "Explain this simply",
  "Give me an example",
  "Quiz me on this",
  "Summarize my progress",
];

/* ------------------------------------------------------------------ */
/* Utilities                                                           */
/* ------------------------------------------------------------------ */
function toast(message, type = "") {
  const wrap = document.getElementById("toastWrap");
  const el = document.createElement("div");
  el.className = `toast ${type}`.trim();
  el.textContent = message;
  wrap.appendChild(el);
  setTimeout(() => el.remove(), 3600);
}

function isArabic(text) {
  return /[\u0600-\u06FF]/.test(text);
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function initials(name) {
  if (!name) return "?";
  return name.split(" ").filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("");
}

async function api(path, { method = "GET", body = null } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;

  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    doLogout(true);
    throw new Error("Session expired. Please sign in again.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || "Something went wrong.");
  }
  return data;
}

/* ------------------------------------------------------------------ */
/* Theme                                                               */
/* ------------------------------------------------------------------ */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  localStorage.setItem("kayfa_theme", theme);
}
function initTheme() {
  const saved = localStorage.getItem("kayfa_theme")
    || (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  applyTheme(saved);
}
document.getElementById("themeToggle").addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  applyTheme(current === "dark" ? "light" : "dark");
});

/* ------------------------------------------------------------------ */
/* Auth                                                                 */
/* ------------------------------------------------------------------ */
document.getElementById("loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;
  const errorBox = document.getElementById("loginError");
  const btn = document.getElementById("loginBtn");

  errorBox.classList.remove("show");
  btn.disabled = true;
  btn.textContent = "Signing in…";

  try {
    const data = await api("/auth/login", {
      method: "POST",
      body: { username, password },
    });
    state.token = data.access_token;
    state.user = data.user;
    localStorage.setItem("kayfa_token", state.token);
    localStorage.setItem("kayfa_user", JSON.stringify(state.user));
    enterApp();
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.classList.add("show");
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign in";
  }
});

function doLogout(silent = false) {
  state.token = null;
  state.user = null;
  state.chatHistory = [];
  state.activeQuiz = null;
  localStorage.removeItem("kayfa_token");
  localStorage.removeItem("kayfa_user");
  document.getElementById("appShell").classList.add("hidden");
  document.getElementById("loginScreen").classList.remove("hidden");
  if (!silent) toast("Signed out.", "success");
}
document.getElementById("logoutBtn").addEventListener("click", async () => {
  try { await api("/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ }
  doLogout();
});

/* ------------------------------------------------------------------ */
/* App shell / navigation                                              */
/* ------------------------------------------------------------------ */
async function enterApp() {
  document.getElementById("loginScreen").classList.add("hidden");
  document.getElementById("appShell").classList.remove("hidden");

  document.getElementById("userAvatar").textContent = initials(state.user.name);
  document.getElementById("userName").textContent = state.user.name;
  document.getElementById("userRole").textContent = state.user.role;

  const navGroup = document.getElementById("navGroup");
  navGroup.innerHTML = "";
  NAV[state.user.role].forEach((item, i) => {
    const el = document.createElement("div");
    el.className = "nav-item" + (i === 0 ? " active" : "");
    el.dataset.view = item.id;
    el.innerHTML = `${ICONS[item.icon]}<span>${item.label}</span>`;
    el.addEventListener("click", () => switchView(item.id));
    navGroup.appendChild(el);
  });

  // Restore this user's own past conversation with the chat agents
  // (server only ever returns the signed-in user's traces — see
  // /api/chat/history) before the first view renders, so if they land
  // straight on the chat tab it's already there instead of popping in.
  try {
    const { messages } = await api("/chat/history");
    state.chatHistory = messages || [];
  } catch (err) {
    state.chatHistory = [];
  }

  switchView(NAV[state.user.role][0].id);
}

function switchView(viewId) {
  state.view = viewId;
  document.querySelectorAll(".nav-item").forEach(el => {
    el.classList.toggle("active", el.dataset.view === viewId);
  });

  const titles = {
    dashboard: state.user.role === "Admin" ? "Observability" : "Dashboard",
    chat: "Ask Kayfa",
    quiz: "Practice Quiz",
  };
  const subs = {
    dashboard: state.user.role === "Admin"
      ? "Live activity across both agents, backed by MongoDB."
      : `Welcome back, ${state.user.name.split(" ")[0]}.`,
    chat: "Academic Help Agent + Quiz Agent, routed automatically.",
    quiz: "Generate a quiz from your enrolled course material.",
  };
  document.getElementById("viewTitle").textContent = titles[viewId] || "";
  document.getElementById("viewSub").textContent = subs[viewId] || "";

  const content = document.getElementById("viewContent");
  content.innerHTML = `<div style="padding:40px;text-align:center;color:var(--ink-faint);">Loading…</div>`;

  if (viewId === "dashboard") {
    state.user.role === "Admin" ? renderAdminDashboard(content) : renderRoleDashboard(content);
  } else if (viewId === "chat") {
    renderChat(content);
  } else if (viewId === "quiz") {
    renderQuizHome(content);
  }
}

/* ------------------------------------------------------------------ */
/* Student / Instructor dashboard                                      */
/* ------------------------------------------------------------------ */
async function renderRoleDashboard(content) {
  try {
    const data = await api("/report");
    if (data.status !== "success") {
      content.innerHTML = `<div class="card"><p>${escapeHtml(data.error || "Could not load your report.")}</p></div>`;
      return;
    }

    if (state.user.role === "Student") {
      content.innerHTML = `
        <div class="stat-row" style="margin-bottom:22px;">
          <div class="stat"><div class="stat-value">${data.enrolled_courses_count}</div><div class="stat-label">Enrolled courses</div></div>
          <div class="stat"><div class="stat-value">${data.average_grade || "—"}</div><div class="stat-label">Average grade</div></div>
          <div class="stat"><div class="stat-value">${data.quizzes_taken}</div><div class="stat-label">Practice quizzes taken</div></div>
          <div class="stat"><div class="stat-value">${data.average_quiz_score || "—"}</div><div class="stat-label">Avg. quiz score</div></div>
        </div>
        <div id="planBanner"></div>
        <div class="card">
          <div class="card-head"><h3>My courses</h3></div>
          ${data.courses.length ? data.courses.map(courseRowStudent).join("") : `<div class="empty-row">You're not enrolled in any courses yet.</div>`}
        </div>`;

      // Loaded separately from /report — a stale/missing plan shouldn't
      // block the rest of the dashboard from rendering.
      loadInterventionPlan();
    } else {
      content.innerHTML = `
        <div class="stat-row" style="margin-bottom:22px;">
          <div class="stat"><div class="stat-value">${data.courses_teaching}</div><div class="stat-label">Courses teaching</div></div>
          <div class="stat"><div class="stat-value">${data.total_students}</div><div class="stat-label">Total students</div></div>
          <div class="stat"><div class="stat-value">${data.average_class_grade || "—"}</div><div class="stat-label">Avg. class grade</div></div>
        </div>
        <div id="alertsBanner"></div>
        ${data.courses.map(courseCardInstructor).join("")}`;

      loadInstructorAlerts();
    }
  } catch (err) {
    content.innerHTML = `<div class="card"><p>${escapeHtml(err.message)}</p></div>`;
  }
}

/* ------------------------------------------------------------------ */
/* Per-quiz improvement plan (diagnosis + steps + project + look_into) */
/* ------------------------------------------------------------------ */
function improvementPlanBodyHtml(plan) {
  const weeks = plan.weeks && plan.weeks.length
    ? plan.weeks
    : (plan.steps || []).length
      ? [{
        title: "Study plan",
        days: plan.steps.map((step, index) => ({
          day: `Day ${index + 1}`,
          title: step.title || "Review lesson",
          focus: step.title || "Review lesson",
          task: step.description || "Review the related lesson material.",
          resources: [],
        })),
      }]
      : [];
  const project = plan.project;
  const lookInto = plan.look_into || [];

  const weeksHtml = weeks.length ? `
    <div class="study-plan-weeks">
      ${weeks.map((week, weekIndex) => `
        <section class="study-plan-week">
          <h4>${escapeHtml(week.title || `Week ${weekIndex + 1}`)}</h4>
          ${(week.days || []).map((day, dayIndex) => `
            <div class="plan-day">
              <div class="plan-day-heading">
                <span class="plan-step-num">${dayIndex + 1}</span>
                <div>
                  <div class="plan-step-title">${escapeHtml(day.day || `Day ${dayIndex + 1}`)} · ${escapeHtml(day.title || "Study session")}</div>
                  ${day.focus ? `<div class="plan-step-desc"><strong>Focus:</strong> ${escapeHtml(day.focus)}</div>` : ""}
                </div>
              </div>
              ${day.task ? `<div class="plan-day-task">${escapeHtml(day.task)}</div>` : ""}
              ${(day.resources || []).length ? `<div class="plan-resources">
                ${(day.resources || []).map(resource => {
                  const query = resource.search_query || resource.title || "";
                  const href = resource.url || resource.video_url || `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
                  return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="plan-resource">
                    ${escapeHtml(resource.title || "Watch related YouTube video")}${resource.provider ? ` <span>· ${escapeHtml(resource.provider)}</span>` : ""}
                  </a>`;
                }).join("")}
              </div>` : ""}
            </div>`).join("")}
        </section>`).join("")}
    </div>` : "";

  const projectHtml = project && project.title ? `
    <div class="plan-project">
      <div class="plan-project-title">🎯 ${escapeHtml(project.title)}</div>
      ${project.description ? `<p>${escapeHtml(project.description)}</p>` : ""}
    </div>` : "";

  const tagsHtml = lookInto.length ? `
    <div class="plan-tags-label">Look into</div>
    <div class="plan-tags">${lookInto.map(t => `<span class="chip static">${escapeHtml(t)}</span>`).join("")}</div>` : "";

  return `${weeksHtml}${projectHtml}${tagsHtml}`;
}

function improvementPlanCardHtml(plan) {
  return `
    <div class="quiz-analysis">
      <span class="quiz-analysis-label">Improvement plan</span>
      ${escapeHtml(plan.diagnosis || "")}
      ${improvementPlanBodyHtml(plan)}
    </div>`;
}

function legacyStudyPlanHtml(analysis, courseTitle) {
  const conceptMatch = analysis.match(/(?:from\s+the|for|on)\s+(.+?)(?:\s+lessons?|\s+as\s+these|\.|$)/i);
  const concepts = conceptMatch
    ? conceptMatch[1].replace(/\s+and\s+/i, ", ").split(/,\s*/).map(concept => concept.trim()).filter(Boolean)
    : [];
  const fallbackConcepts = concepts.length ? concepts : [courseTitle];

  const days = fallbackConcepts.map((concept, index) => {
    const query = `${courseTitle} ${concept} tutorial examples`;
    return `
      <div class="plan-day">
        <div class="plan-day-heading">
          <span class="plan-step-num">${index + 1}</span>
          <div>
            <div class="plan-step-title">Day ${index + 1} · Review ${escapeHtml(concept)}</div>
            <div class="plan-step-desc"><strong>Focus:</strong> ${escapeHtml(courseTitle)} vocabulary, examples, and practice.</div>
          </div>
        </div>
        <div class="plan-day-task">Re-read the ${escapeHtml(courseTitle)} lesson, write a short definition, and complete five practice questions about ${escapeHtml(concept)}.</div>
        <div class="plan-resources">
          <a href="https://www.youtube.com/results?search_query=${encodeURIComponent(query)}" target="_blank" rel="noopener noreferrer" class="plan-resource">
            Find a related video <span>· YouTube</span>
          </a>
        </div>
      </div>`;
  }).join("");

  return `
    <div class="quiz-analysis">
      <span class="quiz-analysis-label">Study plan · Week 1</span>
      ${escapeHtml(analysis)}
      <div class="study-plan-weeks">
        <section class="study-plan-week">
          <h4>Week 1 · Build the foundation</h4>
          ${days}
        </section>
      </div>
    </div>`;
}

function planHasContent(plan) {
  return !!plan && (
    (plan.steps && plan.steps.length) ||
    (plan.weeks && plan.weeks.some(week => week.days && week.days.length)) ||
    (plan.project && plan.project.title) ||
    (plan.look_into && plan.look_into.length)
  );
}

/* ------------------------------------------------------------------ */
/* Intervention planner — at-risk banner (student) + alerts (instructor) */
/* ------------------------------------------------------------------ */
const SEVERITY_LABEL = { high: "🔴 High", medium: "🟠 Medium", low: "🟡 Low" };

const SIGNAL_LABEL = {
  low_attendance: "Low attendance",
  quiz_decline: "Quiz scores dropping",
  stalled_progress: "Progress stalled",
  low_grade: "Low grade",
};

async function loadInterventionPlan() {
  const banner = document.getElementById("planBanner");
  if (!banner) return;
  try {
    const plan = await api("/planner/latest");
    renderInterventionPlanCard(plan);
  } catch (err) {
    banner.innerHTML = ""; // fail quiet — this is a supplementary panel, not the core dashboard
  }
}

function renderInterventionPlanCard(plan) {
  const banner = document.getElementById("planBanner");
  if (!banner) return;

  if (!plan || plan.status === "none" || plan.status === "ok" || !plan.signals || !plan.signals.length) {
    banner.innerHTML = `
      <div class="card risk-card risk-ok">
        <div class="card-head"><h3>You're on track</h3></div>
        <p style="color:var(--ink-faint);font-size:13.5px;">No risk signals detected in your latest check.</p>
      </div>`;
    return;
  }

  const signalRows = plan.signals.map(s => `
    <div class="quiz-history-row">
      <span>${SEVERITY_LABEL[s.severity] || s.severity} · ${escapeHtml(SIGNAL_LABEL[s.type] || s.type)}</span>
      <span style="color:var(--ink-faint);font-size:12px;">${escapeHtml(s.course_title)}</span>
    </div>
    <div class="quiz-history-note">${escapeHtml(s.detail)}</div>
  `).join("");

  const stepSummaries = (plan.steps || []).map(st => {
    if (st.agent === "academic_agent") return `A short explanation was generated for <strong>${escapeHtml(st.course_title)}</strong>.`;
    if (st.agent === "quiz_agent") return `A focused practice quiz was prepared for <strong>${escapeHtml(st.course_title)}</strong>.`;
    if (st.agent === "notify_instructor") return `Your instructor for <strong>${escapeHtml(st.course_title)}</strong> was notified.`;
    return null;
  }).filter(Boolean);

  banner.innerHTML = `
    <div class="card risk-card risk-alert">
      <div class="card-head">
        <h3>Some things need attention</h3>
        <button class="btn btn-ghost" id="recheckPlanBtn">Check now</button>
      </div>
      <p style="color:var(--ink-faint);font-size:13.5px;">${escapeHtml(plan.summary || "")}</p>
      <div class="quiz-history">${signalRows}</div>
      ${stepSummaries.length ? `
        <div class="quiz-history-title" style="margin-top:14px;">What Kayfa already did for you</div>
        <div class="quiz-history-note">${stepSummaries.join("<br>")}</div>
      ` : ""}
    </div>`;

  const recheckBtn = document.getElementById("recheckPlanBtn");
  if (recheckBtn) {
    recheckBtn.addEventListener("click", async () => {
      recheckBtn.disabled = true;
      recheckBtn.textContent = "Checking…";
      try {
        const plan = await api("/planner/run", { method: "POST" });
        renderInterventionPlanCard(plan);
        toast("Checked for the latest updates.", "success");
      } catch (err) {
        toast(err.message, "error");
        recheckBtn.disabled = false;
        recheckBtn.textContent = "Check now";
      }
    });
  }
}

async function loadInstructorAlerts() {
  const banner = document.getElementById("alertsBanner");
  if (!banner) return;
  try {
    const { alerts } = await api("/planner/alerts");
    renderInstructorAlertsCard(alerts || []);
  } catch (err) {
    banner.innerHTML = "";
  }
}

function renderInstructorAlertsCard(alerts) {
  const banner = document.getElementById("alertsBanner");
  if (!banner) return;

  if (!alerts.length) {
    banner.innerHTML = "";
    return;
  }

  const rows = alerts.map(a => `
    <tr>
      <td>${escapeHtml(a.student_name)}</td>
      <td>${escapeHtml(a.course_title)}</td>
      <td>${SEVERITY_LABEL[a.severity] || escapeHtml(a.severity)}</td>
      <td>${escapeHtml(a.message)}</td>
    </tr>`).join("");

  banner.innerHTML = `
    <div class="card risk-card risk-alert" style="margin-bottom:16px;">
      <div class="card-head"><h3>Student alerts</h3><span class="badge neutral">${alerts.length}</span></div>
      <table>
        <thead><tr><th>Student</th><th>Course</th><th>Severity</th><th>Note</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

function courseRowStudent(c) {
  const gradeHtml = c.final_grade != null
    ? `<span class="grade-pill">${c.final_grade}/10</span>`
    : `<span class="grade-pill pending">In progress</span>`;

  const attendanceHtml = c.attendance_percent != null
    ? `<span style="font-size:12px;color:${c.attendance_percent < 60 ? "var(--bad)" : "var(--ink-faint)"};">${c.attendance_percent}% attendance</span>`
    : "";

  const attempts = c.quiz_attempts || [];
  let historyHtml = `<div class="quiz-history"><div class="quiz-history-title">Quiz history</div>`;
  if (attempts.length === 0) {
    historyHtml += `<div class="quiz-history-empty">No quiz attempts yet.</div>`;
  } else {
    attempts.forEach(a => {
      historyHtml += `<div class="quiz-history-row"><span>${a.correct}/${a.total} correct</span><span>${a.score}/10</span></div>`;
      if (planHasContent(a.improvement_plan)) {
        historyHtml += `<details class="plan-details">
          <summary>${escapeHtml(a.improvement_plan.diagnosis || a.analysis || "View improvement plan")}</summary>
          ${improvementPlanBodyHtml(a.improvement_plan)}
        </details>`;
      } else if (a.analysis) {
        historyHtml += legacyStudyPlanHtml(a.analysis, c.title);
      }
    });
  }
  historyHtml += `</div>`;

  return `
    <div class="course-item">
      <div class="course-top">
        <span class="course-title">${escapeHtml(c.title)}</span>
        <span class="course-code">${escapeHtml(c.code)}</span>
      </div>
      <div class="course-desc">${escapeHtml(c.description)}</div>
      <div class="progress-bar"><div style="width:${c.progress_percent}%"></div></div>
      <div class="course-foot">
        <span style="font-size:12px;color:var(--ink-faint);">${c.progress_percent}% complete</span>
        ${attendanceHtml}
        ${gradeHtml}
      </div>
      ${historyHtml}
    </div>`;
}

function courseCardInstructor(c) {
  return `
    <div class="card">
      <div class="card-head">
        <h3>${escapeHtml(c.title)} <span style="color:var(--ink-faint);font-weight:500;">· ${escapeHtml(c.code)}</span></h3>
        <span class="badge neutral">${c.enrolled_count} students · avg ${c.average_grade || "—"}</span>
      </div>
      <table>
        <thead><tr><th>Student</th><th>Final grade</th><th>Report</th></tr></thead>
        <tbody>
          ${c.roster.length ? c.roster.map(r => `
            <tr>
              <td>${escapeHtml(r.name)}</td>
              <td>${r.final_grade != null ? r.final_grade + "/10" : "In progress"}</td>
              <td class="report-cell">${escapeHtml(r.report || "")}</td>
            </tr>
          `).join("") : `<tr><td colspan="3" class="empty-row">No students enrolled yet.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

/* ------------------------------------------------------------------ */
/* Chat — Academic Help Agent + Quiz Agent, with voice input/output     */
/* ------------------------------------------------------------------ */
function renderChat(content) {
  content.innerHTML = `
    <div class="chat-panel">
      <div class="chat-head">
        <div class="agent-icon"><img src="/static/images/kayfa_icon_blue.png" alt=""></div>
        <div>
          <h4>Kayfa Agents</h4>
          <p>Ask about a topic, or say "quiz me on…" to switch agents automatically.</p>
        </div>
      </div>
      <div class="chat-scroll" id="chatScroll"></div>
      <div class="chip-row" id="chipRow"></div>
      <div class="chat-composer">
        <textarea id="chatInput" rows="1" placeholder="Type your question, in Arabic or English…"></textarea>
        <button class="btn-icon mic-btn hidden" id="micBtn" title="Speak your question" aria-label="Voice input">${ICONS.mic}</button>
        <button class="btn-icon" id="sendBtn" title="Send" aria-label="Send message">${ICONS.send}</button>
      </div>
    </div>`;

  const chipRow = document.getElementById("chipRow");
  QUICK_PROMPTS.forEach(p => {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = p;
    chip.addEventListener("click", () => sendChat(p));
    chipRow.appendChild(chip);
  });

  renderChatHistory();

  const input = document.getElementById("chatInput");
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });
  document.getElementById("sendBtn").addEventListener("click", () => sendChat());

  setupVoiceInput();
}

function renderChatHistory() {
  const scroll = document.getElementById("chatScroll");
  if (!scroll) return;
  if (state.chatHistory.length === 0) {
    scroll.innerHTML = `<div style="margin:auto;text-align:center;color:var(--ink-faint);font-size:13.5px;max-width:280px;">
      Start a conversation — ask a course question or request a quick quiz.</div>`;
    return;
  }
  scroll.innerHTML = state.chatHistory.map((m, i) => renderMessage(m, i)).join("");
  scroll.scrollTop = scroll.scrollHeight;
  scroll.querySelectorAll(".speak-btn").forEach(btn => {
    btn.addEventListener("click", () => speakText(btn.dataset.text, btn));
  });
}

function sentimentBadgeHtml(sentiment) {
  if (!sentiment) return "";
  const label = sentiment.label || "Neutral";
  const confidence = Math.round((sentiment.confidence || 0) * 100);
  const emojiByLabel = { positive: "🟢", negative: "🔴", neutral: "⚪" };
  const emoji = emojiByLabel[label.toLowerCase()] || "⚪";
  return `<span class="badge ${label.toLowerCase()}">${emoji} ${label} (${confidence}%)</span>`;
}

function renderMessage(m, i) {
  if (m.role === "user") {
    const sentimentBadge = sentimentBadgeHtml(m.sentiment);
    return `<div class="msg user">
      <div class="bubble">${escapeHtml(m.content)}</div>
      ${sentimentBadge ? `<div class="msg-meta">${sentimentBadge}</div>` : ""}
    </div>`;
  }
  const agentBadge = m.agent === "quiz_agent"
    ? `<span class="badge agent-quiz">Quiz Agent</span>`
    : `<span class="badge agent-academic">Academic Help</span>`;
  return `<div class="msg assistant">
    <div class="bubble ${isArabic(m.content) ? "ar-text" : ""}" dir="${isArabic(m.content) ? "rtl" : "ltr"}">${escapeHtml(m.content)}</div>
    <div class="msg-meta">
      ${agentBadge}
      <button class="speak-btn" data-text="${escapeHtml(m.content)}" title="Read aloud" aria-label="Read aloud">${ICONS.speaker}</button>
    </div>
  </div>`;
}

async function sendChat(prefill) {
  const input = document.getElementById("chatInput");
  const text = (prefill !== undefined ? prefill : input.value).trim();
  if (!text || state.isChatBusy) return;

  input.value = "";
  state.chatHistory.push({ role: "user", content: text });
  renderChatHistory();

  const scroll = document.getElementById("chatScroll");
  const typing = document.createElement("div");
  typing.className = "msg assistant";
  typing.innerHTML = `<div class="bubble typing-dots"><span></span><span></span><span></span></div>`;
  scroll.appendChild(typing);
  scroll.scrollTop = scroll.scrollHeight;

  state.isChatBusy = true;
  document.getElementById("sendBtn").disabled = true;
  try {
    const historyPayload = state.chatHistory.slice(-8, -1).map(m => ({ role: m.role, content: m.content }));
    const data = await api("/chat", { method: "POST", body: { query: text, history: historyPayload } });
    const lastUserMsg = [...state.chatHistory].reverse().find(m => m.role === "user");
    if (lastUserMsg) lastUserMsg.sentiment = data.sentiment;
    state.chatHistory.push({ role: "assistant", content: data.response, agent: data.agent });
  } catch (err) {
    state.chatHistory.push({ role: "assistant", content: `⚠️ ${err.message}`, agent: "academic_agent" });
  } finally {
    state.isChatBusy = false;
    document.getElementById("sendBtn").disabled = false;
    renderChatHistory();
  }
}

/* --- Voice input: record with MediaRecorder, transcribe via Groq Whisper on the server --- */
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

function setupVoiceInput() {
  const micBtn = document.getElementById("micBtn");
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return; // stays hidden — unsupported browser

  micBtn.classList.remove("hidden");

  micBtn.addEventListener("click", async () => {
    if (isRecording) {
      mediaRecorder.stop();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];
      mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(track => track.stop());
        micBtn.classList.remove("recording");
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        await sendVoiceForTranscription(audioBlob);
      };
      mediaRecorder.start();
      isRecording = true;
      micBtn.classList.add("recording");
    } catch (err) {
      toast("Couldn't access the microphone — check browser permissions.", "error");
    }
  });
}

async function sendVoiceForTranscription(audioBlob) {
  const input = document.getElementById("chatInput");
  const micBtn = document.getElementById("micBtn");
  isRecording = false;
  input.placeholder = "Transcribing your voice…";
  const formData = new FormData();
  formData.append("file", audioBlob, "voice.webm");

  try {
    const headers = {};
    if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
    const res = await fetch(`${API}/voice/transcribe`, { method: "POST", headers, body: formData });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Could not transcribe audio.");
    input.value = data.text || "";
    input.focus();
  } catch (err) {
    toast(err.message, "error");
  } finally {
    input.placeholder = "Type your question, in Arabic or English…";
  }
}

function speakText(text, btn) {
  if (!("speechSynthesis" in window)) {
    toast("Voice playback isn't supported in this browser.", "error");
    return;
  }
  if (window.speechSynthesis.speaking) {
    window.speechSynthesis.cancel();
    document.querySelectorAll(".speak-btn.speaking").forEach(b => b.classList.remove("speaking"));
    return;
  }
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = isArabic(text) ? "ar-EG" : "en-US";
  utter.onstart = () => btn.classList.add("speaking");
  utter.onend = () => btn.classList.remove("speaking");
  window.speechSynthesis.speak(utter);
}

/* ------------------------------------------------------------------ */
/* Practice Quiz (Quiz Agent, grounded in course material)             */
/* ------------------------------------------------------------------ */
async function renderQuizHome(content) {
  content.innerHTML = `<div class="card"><div class="spinner"></div></div>`;
  try {
    const courses = await api("/courses");
    if (!courses.length) {
      content.innerHTML = `<div class="card"><p>You're not enrolled in any courses yet, so there's nothing to quiz you on.</p></div>`;
      return;
    }
    content.innerHTML = `
      <div class="card">
        <div class="card-head"><h3>Choose a course</h3></div>
        <div class="quiz-course-list">
          ${courses.map(c => `
            <button class="quiz-course-btn" data-id="${c.id}" data-title="${escapeHtml(c.title)}">
              <span><span class="qc-title">${escapeHtml(c.title)}</span><br><span class="qc-code">${escapeHtml(c.code)}</span></span>
              <span style="color:var(--ink-faint);">→</span>
            </button>`).join("")}
        </div>
      </div>
      <div id="quizArea"></div>`;

    content.querySelectorAll(".quiz-course-btn").forEach(btn => {
      btn.addEventListener("click", () => startQuiz(btn.dataset.id, btn.dataset.title));
    });
  } catch (err) {
    content.innerHTML = `<div class="card"><p>${escapeHtml(err.message)}</p></div>`;
  }
}

async function startQuiz(courseId, courseTitle) {
  const area = document.getElementById("quizArea");
  area.innerHTML = `<div class="card" style="margin-top:18px;"><div class="spinner"></div> Generating your quiz…</div>`;
  try {
    const data = await api("/quiz/generate", { method: "POST", body: { course_id: courseId } });
    state.activeQuiz = { quizToken: data.quiz_token, courseTitle: data.course_title || courseTitle, questions: data.questions, selected: {} };
    renderActiveQuiz();
  } catch (err) {
    area.innerHTML = `<div class="card" style="margin-top:18px;"><p>${escapeHtml(err.message)}</p></div>`;
  }
}

function renderActiveQuiz() {
  const area = document.getElementById("quizArea");
  const q = state.activeQuiz;
  area.innerHTML = `
    <div class="card" style="margin-top:18px;">
      <div class="card-head"><h3>${escapeHtml(q.courseTitle)}</h3><span class="badge agent-quiz">Quiz Agent</span></div>
      ${q.questions.map((question, i) => `
        <div class="quiz-question">
          <div class="q-text">${i + 1}. ${escapeHtml(question.question)}</div>
          <div class="quiz-options" data-qi="${i}">
            ${question.options.map((opt, j) => `
              <label class="quiz-option" data-qi="${i}" data-oi="${j}">
                <input type="radio" name="q${i}" value="${j}">
                <span>${escapeHtml(opt)}</span>
              </label>`).join("")}
          </div>
        </div>`).join("")}
      <button class="btn btn-primary btn-block" id="submitQuizBtn" style="margin-top:8px;">Submit answers</button>
    </div>`;

  area.querySelectorAll(".quiz-option").forEach(opt => {
    opt.addEventListener("click", () => {
      const qi = opt.dataset.qi;
      opt.querySelector("input").checked = true;
      state.activeQuiz.selected[qi] = opt.dataset.oi;
      area.querySelectorAll(`.quiz-option[data-qi="${qi}"]`).forEach(o => o.classList.remove("selected"));
      opt.classList.add("selected");
    });
  });

  document.getElementById("submitQuizBtn").addEventListener("click", submitQuiz);
}

async function submitQuiz() {
  const q = state.activeQuiz;
  if (Object.keys(q.selected).length < q.questions.length) {
    toast("Answer every question before submitting.", "error");
    return;
  }
  const btn = document.getElementById("submitQuizBtn");
  btn.disabled = true;
  btn.textContent = "Grading…";
  try {
    const result = await api("/quiz/submit", { method: "POST", body: { quiz_token: q.quizToken, answers: q.selected } });

    document.querySelectorAll(".quiz-option").forEach(opt => {
      const qi = Number(opt.dataset.qi), oi = Number(opt.dataset.oi);
      const correctIdx = result.correct_answers[qi];
      if (oi === correctIdx) opt.classList.add("correct");
      else if (String(q.selected[qi]) === String(oi)) opt.classList.add("incorrect");
    });

    const area = document.getElementById("quizArea");
    const resultCard = document.createElement("div");
    resultCard.className = "card";
    resultCard.style.marginTop = "18px";
    resultCard.innerHTML = `
      <div class="quiz-result">
        <div class="score-value">${result.score}/10</div>
        <div class="score-label">${result.correct} of ${result.total} correct — saved to your grades.</div>
      </div>
      ${result.improvement_plan
        ? improvementPlanCardHtml(result.improvement_plan)
        : `<div class="quiz-analysis"><span class="quiz-analysis-label">Where you can improve</span>${escapeHtml(result.analysis || "")}</div>`}
      <div style="text-align:center;">
        <button class="btn btn-ghost" style="margin-top:16px;" onclick="renderQuizHome(document.getElementById('viewContent'))">Try another course</button>
      </div>`;
    area.appendChild(resultCard);
    resultCard.scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (err) {
    toast(err.message, "error");
    btn.disabled = false;
    btn.textContent = "Submit answers";
  }
}

/* ------------------------------------------------------------------ */
/* Admin — observability dashboard, backed by real trace data          */
/* ------------------------------------------------------------------ */
let _allTraces = [];
let _adminData = null;
let _adminTab = "time";

async function renderAdminDashboard(content) {
  content.innerHTML = `<div class="card"><div class="spinner"></div></div>`;
  try {
    const data = await api("/report");
    if (data.status !== "success") {
      content.innerHTML = `<div class="card"><p>${escapeHtml(data.error || "Could not load observability data.")}</p></div>`;
      return;
    }
    _adminData = data;
    _allTraces = data.traces;
    const kpi = data.kpi;

    content.innerHTML = `
      <div class="stat-row" style="margin-bottom:22px;">
        <div class="stat"><div class="stat-value">${kpi.calls_count}</div><div class="stat-label">Agent calls logged</div></div>
        <div class="stat"><div class="stat-value">${kpi.unique_users.length}</div><div class="stat-label">Unique users</div></div>
        <div class="stat"><div class="stat-value">${kpi.total_tokens.toLocaleString()}</div><div class="stat-label">Tokens used</div></div>
        <div class="stat"><div class="stat-value">${kpi.avg_response_time_ms}</div><div class="stat-label">Avg. response time (ms)</div></div>
      </div>
      <div class="tab-row" id="adminTabRow">
        <button class="tab-btn" data-tab="time">Usage Over Time</button>
        <button class="tab-btn" data-tab="user">Usage by User</button>
        <button class="tab-btn" data-tab="recent">Recent Activity</button>
        <button class="tab-btn" data-tab="learning">Self-Refining Agents</button>
        <button class="tab-btn" data-tab="system">System</button>
      </div>
      <div id="adminTabContent"></div>`;

    document.querySelectorAll("#adminTabRow .tab-btn").forEach(btn => {
      btn.addEventListener("click", () => { _adminTab = btn.dataset.tab; renderAdminTab(); });
    });
    renderAdminTab();
  } catch (err) {
    content.innerHTML = `<div class="card"><p>${escapeHtml(err.message)}</p></div>`;
  }
}

function renderAdminTab() {
  document.querySelectorAll("#adminTabRow .tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === _adminTab);
  });
  if (_adminTab === "time") renderUsageOverTime();
  else if (_adminTab === "user") renderUsageByUser();
  else if (_adminTab === "recent") renderRecentActivity();
  else if (_adminTab === "learning") renderSelfRefining();
  else if (_adminTab === "system") renderSystemTab();
}

const ROLE_COLORS = { student: "#5B4FE0", instructor: "#22C55E", admin: "#F59E0B", unknown: "#94A3B8" };

function renderUsageOverTime() {
  const container = document.getElementById("adminTabContent");
  const series = _adminData.usage_over_time || [];
  const byRole = _adminData.usage_by_role || [];

  const max = Math.max(1, ...series.map(d => d.tokens));
  const bars = series.map(d => `
    <div class="bar-col">
      <span class="bar-value">${d.tokens}</span>
      <div class="bar" style="height:${(d.tokens / max) * 100}%"></div>
      <span class="bar-label">${d.date}</span>
    </div>`).join("");

  const totalRoleTokens = byRole.reduce((sum, r) => sum + r.tokens, 0) || 1;
  let cursor = 0;
  const gradientParts = byRole.map(r => {
    const slice = (r.tokens / totalRoleTokens) * 360;
    const color = ROLE_COLORS[r.role.toLowerCase()] || ROLE_COLORS.unknown;
    const part = `${color} ${cursor}deg ${cursor + slice}deg`;
    cursor += slice;
    return part;
  });
  const donutStyle = gradientParts.length ? `background:conic-gradient(${gradientParts.join(",")});` : `background:var(--line);`;
  const legend = byRole.map(r => {
    const color = ROLE_COLORS[r.role.toLowerCase()] || ROLE_COLORS.unknown;
    const pct = Math.round((r.tokens / totalRoleTokens) * 100);
    return `<div class="donut-legend-item"><span class="donut-dot" style="background:${color}"></span>${escapeHtml(r.role)} — ${pct}% (${r.tokens} tokens)</div>`;
  }).join("");

  container.innerHTML = `
    <div class="card">
      <div class="card-head"><h3>Tokens used per day</h3></div>
      ${series.length ? `<div class="bar-chart">${bars}</div>` : `<div class="empty-row">No usage data yet.</div>`}
    </div>
    <div class="card" style="margin-top:16px;">
      <div class="card-head"><h3>Token usage by role</h3></div>
      ${byRole.length ? `
        <div class="donut-wrap">
          <div class="donut" style="${donutStyle}"></div>
          <div class="donut-legend">${legend}</div>
        </div>` : `<div class="empty-row">No usage data yet.</div>`}
    </div>`;
}

function renderUsageByUser() {
  const container = document.getElementById("adminTabContent");
  const rows = _adminData.usage_by_user || [];
  container.innerHTML = `
    <div class="card">
      <div class="card-head"><h3>Usage by user</h3></div>
      <table>
        <thead><tr><th>Name</th><th>Role</th><th>Conversations</th><th>Total tokens</th><th>Avg latency (ms)</th></tr></thead>
        <tbody>
          ${rows.length ? rows.map(u => `
            <tr>
              <td>${escapeHtml(u.full_name)}</td>
              <td>${escapeHtml(u.role)}</td>
              <td>${u.conversations}</td>
              <td>${u.total_tokens}</td>
              <td>${u.avg_latency_ms}</td>
            </tr>`).join("") : `<tr><td colspan="5" class="empty-row">No usage data yet.</td></tr>`}
        </tbody>
      </table>
    </div>`;
}

function renderSystemTab() {
  const container = document.getElementById("adminTabContent");
  const s = _adminData.system || { students: 0, instructors: 0, courses: 0, model: "—" };
  container.innerHTML = `
    <div class="system-grid">
      <div class="system-card"><div class="system-value">${s.students}</div><div class="system-label">Students</div></div>
      <div class="system-card"><div class="system-value">${s.instructors}</div><div class="system-label">Instructors</div></div>
      <div class="system-card"><div class="system-value">${s.courses}</div><div class="system-label">Courses</div></div>
    </div>
    <div class="system-footer">Agent model in use: ${escapeHtml(s.model)}</div>`;
}

function _formatTimestamp(ts) {
  if (!ts) return "Never";
  return new Date(ts * 1000).toLocaleString();
}

function _selfRefiningCard(label, stats) {
  const strategy = (stats.current_strategy || "").trim();
  return `
    <div class="card" style="margin-top:16px;">
      <div class="card-head"><h3>${escapeHtml(label)}</h3></div>
      <div class="system-grid">
        <div class="system-card"><div class="system-value">${stats.experiences_recorded}</div><div class="system-label">Experiences recorded</div></div>
        <div class="system-card"><div class="system-value">${stats.refinements_triggered}</div><div class="system-label">Refinements triggered</div></div>
      </div>
      <div class="system-footer">Last refined: ${escapeHtml(_formatTimestamp(stats.last_refined_at))}</div>
      ${strategy
      ? `<div class="empty-row" style="text-align:left; white-space:pre-wrap;">${escapeHtml(strategy)}</div>`
      : `<div class="empty-row">No strategy learned yet — not enough recurring weaknesses seen so far.</div>`}
    </div>`;
}

function renderSelfRefining() {
  const container = document.getElementById("adminTabContent");
  const data = _adminData.self_refining;
  if (!data) {
    container.innerHTML = `<div class="card"><p>No self-refining data available.</p></div>`;
    return;
  }
  container.innerHTML =
    _selfRefiningCard("Academic Help Agent", data.academic_agent) +
    _selfRefiningCard("Quiz Agent", data.quiz_agent);
}

function renderRecentActivity() {
  const container = document.getElementById("adminTabContent");
  container.innerHTML = `
    <div class="card">
      <div class="card-head"><h3>Recent activity</h3></div>
      <div class="filter-row">
        <input type="text" id="traceSearch" placeholder="Search by user or message…">
        <select id="agentFilter">
          <option value="">All agents</option>
          <option value="academic_agent">Academic Help</option>
          <option value="quiz_agent">Quiz Agent</option>
        </select>
        <button class="btn btn-ghost" id="exportCsv">Export CSV</button>
      </div>
      <table>
        <thead><tr><th>Time</th><th>User</th><th>Agent</th><th>Message</th><th>Sentiment</th></tr></thead>
        <tbody id="traceBody"></tbody>
      </table>
    </div>`;

  document.getElementById("traceSearch").addEventListener("input", renderTraceTable);
  document.getElementById("agentFilter").addEventListener("change", renderTraceTable);
  document.getElementById("exportCsv").addEventListener("click", exportTracesCsv);
  renderTraceTable();
}

function renderTraceTable() {
  const search = (document.getElementById("traceSearch")?.value || "").toLowerCase();
  const agentFilter = document.getElementById("agentFilter")?.value || "";
  const body = document.getElementById("traceBody");
  if (!body) return;

  const filtered = _allTraces.filter(t => {
    if (agentFilter && t.agent !== agentFilter) return false;
    if (search && !(`${t.full_name || t.user_id} ${t.query}`.toLowerCase().includes(search))) return false;
    return true;
  });

  if (!filtered.length) {
    body.innerHTML = `<tr><td colspan="5" class="empty-row">No activity matches your filters yet.</td></tr>`;
    return;
  }

  body.innerHTML = filtered.map((t, i) => {
    const agentBadge = t.agent === "quiz_agent"
      ? `<span class="badge agent-quiz">Quiz</span>` : `<span class="badge agent-academic">Academic</span>`;
    const sentimentBadge = t.sentiment ? sentimentBadgeHtml(t.sentiment) : "—";
    const time = t.timestamp ? new Date(t.timestamp).toLocaleString() : "—";
    return `
      <tr class="trace-row" data-idx="${i}">
        <td>${time}</td>
        <td>${escapeHtml(t.full_name || t.user_id || "—")}<br><span style="color:var(--ink-faint);font-size:11.5px;">${escapeHtml(t.user_role || "")}</span></td>
        <td>${agentBadge}</td>
        <td class="trace-detail" title="${escapeHtml(t.query || "")}">${escapeHtml(t.query || "")}</td>
        <td>${sentimentBadge}</td>
      </tr>
      <tr class="trace-expand-row hidden" data-expand="${i}">
        <td colspan="5">
          <div class="trace-expand-label">Question</div>
          <div class="trace-expand-text">${escapeHtml(t.query || "")}</div>
          <div class="trace-expand-label">Answer</div>
          <div class="trace-expand-text">${escapeHtml(t.response || "")}</div>
        </td>
      </tr>`;
  }).join("");

  body.querySelectorAll(".trace-row").forEach(row => {
    row.addEventListener("click", () => {
      const expandRow = body.querySelector(`.trace-expand-row[data-expand="${row.dataset.idx}"]`);
      if (expandRow) expandRow.classList.toggle("hidden");
    });
  });
}

function exportTracesCsv() {
  const rows = [["timestamp", "user_id", "full_name", "role", "agent", "query", "response", "sentiment", "prompt_tokens", "completion_tokens", "latency_ms", "cost_usd"]];
  _allTraces.forEach(t => rows.push([
    t.timestamp || "", t.user_id || "", t.full_name || "", t.user_role || "", t.agent || "",
    (t.query || "").replace(/\n/g, " "), (t.response || "").replace(/\n/g, " "),
    t.sentiment ? t.sentiment.label : "", t.prompt_tokens || 0, t.completion_tokens || 0, t.latency_ms ?? "", t.cost_usd || 0,
  ]));
  const csv = rows.map(r => r.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "kayfa_activity.csv";
  a.click();
}

/* ------------------------------------------------------------------ */
/* Boot                                                                 */
/* ------------------------------------------------------------------ */
initTheme();
if (state.token && state.user) {
  enterApp();
}