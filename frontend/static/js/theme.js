/* ------------------------------------------------------------------ */
/* Kayfa — light / dark theme toggle                                  */
/* The initial theme is already applied by the inline snippet in      */
/* <head> (before first paint) to avoid a flash of the wrong theme.   */
/* This file just wires up any .theme-toggle buttons on the page.     */
/* ------------------------------------------------------------------ */
const KAYFA_THEME_KEY = "kayfa-theme";

function kayfaGetTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function kayfaSetTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem(KAYFA_THEME_KEY, theme); } catch (e) { /* storage unavailable */ }
    document.querySelectorAll(".theme-toggle").forEach((btn) => {
        btn.setAttribute("aria-checked", theme === "dark" ? "true" : "false");
        btn.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
    });
}

function kayfaToggleTheme() {
    kayfaSetTheme(kayfaGetTheme() === "dark" ? "light" : "dark");
}

document.addEventListener("DOMContentLoaded", () => {
    kayfaSetTheme(kayfaGetTheme());
    document.querySelectorAll(".theme-toggle").forEach((btn) => {
        btn.setAttribute("role", "switch");
        btn.addEventListener("click", kayfaToggleTheme);
    });
});
