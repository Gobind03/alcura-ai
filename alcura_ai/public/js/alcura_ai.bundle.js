/**
 * Alcura Desk bundle entry point.
 *
 * This file is auto-discovered by `bench build` and compiled to
 * /assets/alcura_ai/dist/js/alcura_ai.bundle.<hash>.js
 *
 * Include it in hooks.py via:
 *   app_include_js = ["alcura_ai.bundle.js"]
 */

window.alcura_ai = window.alcura_ai || {};

frappe.ready(() => {
	console.info("[Alcura] App loaded");
});
