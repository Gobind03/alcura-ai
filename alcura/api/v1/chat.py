import json

import frappe

from alcura.services.data_service import (
	build_tool_definitions,
	dispatch_tool_call,
	get_indexed_doctypes,
)
from alcura.services.openai_service import chat_with_tools


@frappe.whitelist()
def send_message(message, history=None):
	"""Send a message to the AI and get a response.

	Args:
		message: The user's question or prompt.
		history: Optional JSON string of prior messages [{role, content}, ...].

	Returns:
		dict with 'response' key containing the AI's answer.

	Callable at: /api/method/alcura.api.v1.chat.send_message
	"""
	frappe.only_for("System Manager")

	if not message or not message.strip():
		frappe.throw("Message cannot be empty.")

	settings = frappe.get_single("Alcura AI Settings")
	if not settings.enabled:
		frappe.throw("Alcura AI is not enabled. Please enable it in Alcura AI Settings.")

	indexed = get_indexed_doctypes()
	if not indexed:
		frappe.throw("No DocTypes are indexed for AI access. Please configure at least one AI DocType Index.")

	doctypes_description = "\n".join(
		f"- {d['doctype']}: {d['description']} (fields: {', '.join(f['field_name'] for f in d['fields'])})"
		for d in indexed
	)

	system_prompt_template = settings.system_prompt or (
		"You are a data assistant. Answer questions ONLY using data from your tools. "
		"Say 'I don't have enough data' if you cannot find relevant information."
	)
	system_prompt = system_prompt_template.replace("{indexed_doctypes}", doctypes_description)

	messages = [{"role": "system", "content": system_prompt}]

	if history:
		if isinstance(history, str):
			history = json.loads(history)
		for msg in history:
			if msg.get("role") in ("user", "assistant") and msg.get("content"):
				messages.append({"role": msg["role"], "content": msg["content"]})

	messages.append({"role": "user", "content": message.strip()})

	tools = build_tool_definitions()

	response_text = chat_with_tools(messages, tools, dispatch_tool_call)

	return {"response": response_text}


@frappe.whitelist()
def get_context():
	"""Return the list of indexed DocTypes and descriptions for the chat UI.

	Callable at: /api/method/alcura.api.v1.chat.get_context
	"""
	frappe.only_for("System Manager")

	indexed = get_indexed_doctypes()
	return {
		"doctypes": [
			{
				"doctype": d["doctype"],
				"description": d["description"],
				"field_count": len(d["fields"]),
			}
			for d in indexed
		]
	}
