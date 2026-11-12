"use strict";

// Progressive enhancement: navigation and server forms still work without JS.
document.body.classList.add("js-ready");
const toggle = document.getElementById("nav-toggle");
const menu = document.getElementById("primary-menu");
if (toggle && menu) {
  toggle.addEventListener("click", () => {
    const open = toggle.getAttribute("aria-expanded") !== "true";
    toggle.setAttribute("aria-expanded", String(open));
    menu.classList.toggle("is-open", open);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && toggle.getAttribute("aria-expanded") === "true") {
      toggle.setAttribute("aria-expanded", "false");
      menu.classList.remove("is-open");
      toggle.focus();
    }
  });
  menu.querySelectorAll("a").forEach((link) => {
    if (new URL(link.href).pathname === window.location.pathname) {
      link.setAttribute("aria-current", "page");
    }
  });
}
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
document.querySelectorAll(".table-responsive").forEach((region) => {
  region.setAttribute("tabindex", "0");
  region.setAttribute("role", "region");
  region.setAttribute("aria-label", region.querySelector("caption")?.textContent.trim() || "Scrollable data table");
});
