import frappe

from alcura.services.openai_service import test_connection


@frappe.whitelist()
def test_openai_connection():
	"""Test the OpenAI API connection using the configured key.

	Callable at: /api/method/alcura.api.v1.settings.test_openai_connection
	"""
	frappe.only_for("System Manager")

	try:
		result = test_connection()
		return result
	except Exception as e:
		frappe.throw(f"Connection failed: {e}")
