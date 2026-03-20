import json

import frappe

from alcura.services.analysis_service import dispatch_analysis
from alcura.services.data_service import (
	build_tool_definitions,
	dispatch_tool_call,
	get_indexed_doctypes,
)
from alcura.services.openai_service import chat_with_tools


def _get_logger():
	return frappe.logger("alcura_ai", allow_site=True)


@frappe.whitelist()
def send_message(message, history=None):
	"""Send a message to the AI and get a response.

	Args:
		message: The user's question or prompt.
		history: Optional JSON string of prior messages [{role, content}, ...].

	Returns:
		dict with 'response' and 'charts' keys.

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

	logger = _get_logger()

	doctypes_description = "\n".join(
		f"- {d['doctype']}: {d['description']} (fields: {', '.join(f['field_name'] for f in d['fields'])})"
		for d in indexed
	)

	logger.info(
		f"Indexed doctypes: {[d['doctype'] for d in indexed]}, "
		f"total fields: {sum(len(d['fields']) for d in indexed)}"
	)

	system_prompt_template = settings.system_prompt or (
		"You are a data assistant. Answer questions ONLY using data from your tools. "
		"Say 'I don't have enough data' if you cannot find relevant information."
	)
	system_prompt = system_prompt_template.replace("{indexed_doctypes}", doctypes_description)

	if "{indexed_doctypes}" not in system_prompt_template:
		system_prompt += f"\n\nAvailable data sources:\n{doctypes_description}"
		logger.warning(
			"System prompt does not contain {indexed_doctypes} placeholder. "
			"Appending available data sources automatically."
		)

	messages = [{"role": "system", "content": system_prompt}]

	if history:
		if isinstance(history, str):
			history = json.loads(history)
		for msg in history:
			if msg.get("role") in ("user", "assistant") and msg.get("content"):
				messages.append({"role": msg["role"], "content": msg["content"]})

	messages.append({"role": "user", "content": message.strip()})

	tools = build_tool_definitions()

	logger.info(f"User message: {message.strip()[:200]}")
	logger.info(f"Tool definitions count: {len(tools)}")
	logger.info(f"System prompt length: {len(system_prompt)} chars")

	collected_charts = []

	def _dispatch(name, arguments):
		logger.info(f"Dispatching tool: {name}, args keys: {list(arguments.keys()) if isinstance(arguments, dict) else 'N/A'}")
		try:
			if name == "run_analysis":
				result_json, charts = dispatch_analysis(arguments)
				collected_charts.extend(charts)
				logger.info(f"run_analysis returned {len(result_json)} chars, {len(charts)} charts")
				return result_json
			result = dispatch_tool_call(name, arguments)
			logger.info(f"{name} returned {len(result)} chars")
			return result
		except Exception as e:
			logger.error(f"Tool {name} raised {type(e).__name__}: {str(e)[:300]}")
			raise

	response_text = chat_with_tools(messages, tools, _dispatch)

	logger.info(f"Final response length: {len(response_text)} chars, charts: {len(collected_charts)}")

	return {"response": response_text, "charts": collected_charts}


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
