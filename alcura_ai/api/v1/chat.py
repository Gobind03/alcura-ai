"""Chat API endpoints.

``send_message`` enqueues the OpenAI call as a Frappe background job so
that gunicorn web-workers are freed immediately. The frontend polls
``poll_response`` until the result is ready, or receives it instantly
via ``frappe.publish_realtime``.
"""

import json
import uuid
from datetime import datetime

import frappe

from alcura_ai.services.analysis_service import dispatch_analysis
from alcura_ai.services.data_service import (
	build_tool_definitions,
	dispatch_tool_call,
	get_indexed_doctypes,
)
from alcura_ai.services.openai_service import chat_with_tools
from alcura_ai.services.rate_limiter import check_rate_limit, record_usage

MAX_HISTORY_MESSAGES_DEFAULT = 20
TASK_TTL = 600  # results expire after 10 minutes


def _get_logger():
	return frappe.logger("alcura_ai", allow_site=True)


def _task_key(task_id):
	return f"alcura_ai:task:{task_id}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@frappe.whitelist()
def send_message(message, history=None):
	"""Enqueue an AI message and return a task_id for polling.

	Args:
		message: The user's question or prompt.
		history: Optional JSON string of prior messages [{role, content}, ...].

	Returns:
		dict with ``task_id`` for use with ``poll_response``.

	Callable at: /api/method/alcura_ai.api.v1.chat.send_message
	"""
	frappe.only_for("System Manager")

	if not message or not message.strip():
		frappe.throw("Message cannot be empty.")

	settings = frappe.get_single("Alcura AI Settings")
	if not settings.enabled:
		frappe.throw("Alcura AI is not enabled. Please enable it in Alcura AI Settings.")

	rate_limit = settings.get("rate_limit_per_hour") or 0
	check_rate_limit(limit=rate_limit)

	indexed = get_indexed_doctypes()
	if not indexed:
		frappe.throw(
			"No DocTypes are indexed for AI access. "
			"Please configure at least one AI DocType Index."
		)

	max_history = settings.get("max_history_messages") or MAX_HISTORY_MESSAGES_DEFAULT
	if history:
		if isinstance(history, str):
			history = json.loads(history)
		history = _truncate_history(history, max_history)
	else:
		history = []

	record_usage()

	task_id = str(uuid.uuid4())
	user = frappe.session.user
	site = frappe.local.site

	frappe.cache.set_value(
		_task_key(task_id),
		json.dumps({"status": "queued"}),
		expires_in_sec=TASK_TTL,
	)

	frappe.enqueue(
		"alcura_ai.api.v1.chat._process_message",
		queue="default",
		timeout=120,
		is_async=True,
		task_id=task_id,
		message=message.strip(),
		history=history,
		user=user,
		site=site,
	)

	return {"task_id": task_id}


@frappe.whitelist()
def poll_response(task_id):
	"""Check whether a background AI task has completed.

	Args:
		task_id: The id returned by ``send_message``.

	Returns:
		dict with ``status`` (``queued`` | ``running`` | ``done`` | ``error``),
		and ``response`` + ``charts`` when status is ``done``.

	Callable at: /api/method/alcura_ai.api.v1.chat.poll_response
	"""
	frappe.only_for("System Manager")

	if not task_id:
		frappe.throw("task_id is required.")

	raw = frappe.cache.get_value(_task_key(task_id))
	if raw is None:
		return {"status": "expired"}

	try:
		return json.loads(raw)
	except (json.JSONDecodeError, TypeError):
		return {"status": "error", "error": "Corrupt task data."}


@frappe.whitelist()
def get_context():
	"""Return the list of indexed DocTypes and descriptions for the chat UI.

	Callable at: /api/method/alcura_ai.api.v1.chat.get_context
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


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------


def _process_message(task_id, message, history, user, site):
	"""Run in a background worker -- builds context and calls OpenAI."""
	logger = _get_logger()

	try:
		frappe.cache.set_value(
			_task_key(task_id),
			json.dumps({"status": "running"}),
			expires_in_sec=TASK_TTL,
		)

		settings = frappe.get_single("Alcura AI Settings")
		indexed = get_indexed_doctypes()

		doctypes_description = "\n".join(
			f"- {d['doctype']}: {d['description']} "
			f"(fields: {', '.join(f['field_name'] for f in d['fields'])})"
			for d in indexed
		)

		system_prompt_template = settings.system_prompt or (
			"You are a data assistant. Answer questions ONLY using data from your tools. "
			"Say 'I don't have enough data' if you cannot find relevant information."
		)

		now = datetime.now()
		system_prompt = system_prompt_template.replace("{indexed_doctypes}", doctypes_description)
		system_prompt = system_prompt.replace("{current_date}", now.strftime("%Y-%m-%d"))
		system_prompt = system_prompt.replace("{current_datetime}", now.strftime("%Y-%m-%d %H:%M:%S"))

		if "{indexed_doctypes}" not in system_prompt_template:
			system_prompt += f"\n\nAvailable data sources:\n{doctypes_description}"

		date_context = (
			f"\n\nCURRENT DATE CONTEXT:\n"
			f"- Today's date: {now.strftime('%Y-%m-%d')}\n"
			f"- Current time: {now.strftime('%H:%M:%S')}\n"
			f"- When users refer to relative dates (e.g. 'last 1 year', 'past 6 months', "
			f"'this quarter'), calculate the exact date range using today's date.\n"
			f"- Always use YYYY-MM-DD format for date filter values."
		)
		system_prompt += date_context

		messages = [{"role": "system", "content": system_prompt}]

		for msg in history:
			if msg.get("role") in ("user", "assistant") and msg.get("content"):
				messages.append({"role": msg["role"], "content": msg["content"]})

		messages.append({"role": "user", "content": message})

		tools = build_tool_definitions()

		logger.info(f"[{task_id[:8]}] User: {message[:200]}")
		logger.info(f"[{task_id[:8]}] Tools: {len(tools)}, prompt: {len(system_prompt)} chars")

		collected_charts = []

		def _dispatch(name, arguments):
			if name == "run_analysis":
				result_json, charts = dispatch_analysis(arguments)
				collected_charts.extend(charts)
				return result_json
			return dispatch_tool_call(name, arguments)

		response_text = chat_with_tools(messages, tools, _dispatch)

		result = {
			"status": "done",
			"response": response_text,
			"charts": collected_charts,
		}

		frappe.cache.set_value(
			_task_key(task_id),
			json.dumps(result, default=str),
			expires_in_sec=TASK_TTL,
		)

		frappe.publish_realtime(
			event="alcura_ai_response",
			message={"task_id": task_id},
			user=user,
		)

		logger.info(
			f"[{task_id[:8]}] Done — response: {len(response_text)} chars, "
			f"charts: {len(collected_charts)}"
		)

	except Exception as e:
		logger.error(f"[{task_id[:8]}] Failed: {type(e).__name__}: {e}")
		frappe.cache.set_value(
			_task_key(task_id),
			json.dumps({
				"status": "error",
				"error": str(e),
			}),
			expires_in_sec=TASK_TTL,
		)
		frappe.publish_realtime(
			event="alcura_ai_response",
			message={"task_id": task_id},
			user=user,
		)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _truncate_history(history, max_messages):
	"""Keep only the last *max_messages* user/assistant pairs.

	Always preserves the most recent exchanges so the model retains
	conversational context without unbounded token growth.
	"""
	if not history or max_messages <= 0:
		return history

	relevant = [m for m in history if m.get("role") in ("user", "assistant")]
	if len(relevant) <= max_messages:
		return relevant

	return relevant[-max_messages:]
