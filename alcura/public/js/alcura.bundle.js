/**
 * Alcura Desk bundle entry point.
 *
 * This file is auto-discovered by `bench build` and compiled to
 * /assets/alcura/dist/js/alcura.bundle.<hash>.js
 *
 * Include it in hooks.py via:
 *   app_include_js = ["alcura.bundle.js"]
 */

window.alcura = window.alcura || {};

frappe.ready(() => {
	console.info("[Alcura] App loaded");
});
