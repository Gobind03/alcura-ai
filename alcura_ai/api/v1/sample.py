import frappe


@frappe.whitelist()
def ping():
	"""Health-check endpoint.

	Returns a simple response confirming the API is reachable.
	Callable at: /api/method/alcura_ai.api.v1.sample.ping
	"""
	return {"message": "pong", "app": "alcura_ai", "version": frappe.get_module("alcura_ai").__version__}


@frappe.whitelist()
def echo(text: str | None = None):
	"""Echo back the provided text.

	Args:
		text: Arbitrary string to echo back.

	Callable at: /api/method/alcura_ai.api.v1.sample.echo
	"""
	if text is None:
		frappe.throw("Parameter 'text' is required", frappe.MandatoryError)

	return {"echo": text}
