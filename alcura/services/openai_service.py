import json

import frappe
from openai import OpenAI


MAX_TOOL_ITERATIONS = 25
FORCE_ANSWER_AFTER = 15


def _get_logger():
	return frappe.logger("alcura_ai", allow_site=True)


def get_settings():
	settings = frappe.get_single("Alcura AI Settings")
	if not settings.enabled:
		frappe.throw("Alcura AI is not enabled. Please enable it in Alcura AI Settings.")
	if not settings.api_key:
		frappe.throw("OpenAI API key is not configured. Please set it in Alcura AI Settings.")
	return settings


def get_client():
	settings = get_settings()
	return OpenAI(api_key=settings.get_password("api_key"))


def test_connection():
	"""Validate the API key by listing models."""
	settings = frappe.get_single("Alcura AI Settings")
	if not settings.api_key:
		frappe.throw("OpenAI API key is not configured.")

	client = OpenAI(api_key=settings.get_password("api_key"))
	model_id = settings.model or "gpt-4o-mini"

	token_kwarg = "max_completion_tokens" if model_id.startswith(("gpt-4.1", "o")) else "max_tokens"
	response = client.chat.completions.create(
		model=model_id,
		messages=[{"role": "user", "content": "Reply with OK"}],
		**{token_kwarg: 5},
	)

	return {
		"success": True,
		"model": model_id,
		"response": response.choices[0].message.content,
	}


def _force_text_response(client, model, messages, temperature, token_param, max_tokens, tools):
	"""Make a final API call with tool_choice='none' to force a text answer."""
	messages.append({
		"role": "system",
		"content": (
			"[SYSTEM] You must now provide your final answer. Summarise your findings "
			"based on all the data you have gathered so far. Do NOT call any more tools."
		),
	})

	kwargs = {
		"model": model,
		"messages": messages,
		"temperature": temperature,
		token_param: max_tokens,
	}
	if tools:
		kwargs["tools"] = tools
		kwargs["tool_choice"] = "none"

	response = client.chat.completions.create(**kwargs)
	return response.choices[0].message.content or ""


def chat_with_tools(messages, tools, tool_dispatcher):
	"""Run a chat completion with tool-calling loop.

	The loop allows up to MAX_TOOL_ITERATIONS rounds of tool calls.
	After FORCE_ANSWER_AFTER rounds, a final call with tool_choice='none'
	forces the model to produce a text response, guaranteeing termination.

	Args:
		messages: List of message dicts (role, content).
		tools: List of OpenAI tool definitions.
		tool_dispatcher: Callable(name, arguments) -> result string.

	Returns:
		The final assistant text response.
	"""
	settings = get_settings()
	client = OpenAI(api_key=settings.get_password("api_key"))

	model = settings.model or "gpt-4o-mini"
	temperature = settings.temperature if settings.temperature is not None else 0.2
	max_tokens = settings.max_tokens or 4096

	uses_max_completion_tokens = model.startswith("gpt-4.1") or model.startswith("o")
	token_param = "max_completion_tokens" if uses_max_completion_tokens else "max_tokens"

	failed_tools = {}

	for iteration in range(MAX_TOOL_ITERATIONS):
		if iteration >= FORCE_ANSWER_AFTER:
			_get_logger().info(f"Iteration {iteration}: forcing text response (budget exceeded)")
			return _force_text_response(
				client, model, messages, temperature, token_param, max_tokens, tools
			)

		kwargs = {
			"model": model,
			"messages": messages,
			"temperature": temperature,
			token_param: max_tokens,
		}
		if tools:
			kwargs["tools"] = tools
			kwargs["tool_choice"] = "auto"

		response = client.chat.completions.create(**kwargs)
		choice = response.choices[0]

		if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
			messages.append(choice.message.model_dump(exclude_none=True))

			tool_names = [tc.function.name for tc in choice.message.tool_calls]
			_get_logger().info(f"Iteration {iteration}: tool calls = {tool_names}")

			for tool_call in choice.message.tool_calls:
				fn_name = tool_call.function.name
				fn_args = json.loads(tool_call.function.arguments)

				try:
					result = tool_dispatcher(fn_name, fn_args)
				except Exception as e:
					error_key = f"{fn_name}:{type(e).__name__}"
					failed_tools[error_key] = failed_tools.get(error_key, 0) + 1
					error_msg = str(e)

					_get_logger().warning(
						f"Iteration {iteration}: {fn_name} failed ({type(e).__name__}): {error_msg[:200]}"
					)

					if failed_tools[error_key] >= 2:
						error_msg += (
							" [FATAL: This tool has failed repeatedly with the same error type. "
							"Do NOT call this tool again. Use a different tool or provide your "
							"final answer based on data already collected.]"
						)

					result = json.dumps({"error": error_msg})

				if not isinstance(result, str):
					result = json.dumps(result, default=str)

				messages.append(
					{
						"role": "tool",
						"tool_call_id": tool_call.id,
						"content": result,
					}
				)
			continue

		_get_logger().info(f"Iteration {iteration}: model returned text response")
		return choice.message.content or ""

	return "I was unable to complete the analysis within the allowed number of steps. Please try a simpler question."
