"""Per-user rate limiting backed by Redis.

Uses a sliding-window counter pattern: each user gets a Redis key
that tracks the number of messages sent in the current window.
The key auto-expires so there is zero cleanup overhead.
"""

import frappe


def _rate_limit_key(user):
	return f"alcura_ai:rate:{user}"


def check_rate_limit(user=None, limit=None):
	"""Check whether the user has exceeded their message quota.

	Args:
		user: Frappe user id (defaults to ``frappe.session.user``).
		limit: Max messages per hour. ``0`` or ``None`` disables the limit.

	Returns:
		dict with ``allowed`` (bool), ``used`` (int), ``limit`` (int),
		and ``remaining`` (int) keys.

	Raises:
		frappe.ValidationError: When the rate limit is exceeded.
	"""
	user = user or frappe.session.user

	if not limit:
		return {"allowed": True, "used": 0, "limit": 0, "remaining": 0}

	cache = frappe.cache
	key = _rate_limit_key(user)

	current = cache.get_value(key)
	used = int(current) if current else 0

	if used >= limit:
		frappe.throw(
			f"Rate limit exceeded. You can send {limit} messages per hour. "
			"Please wait before sending more messages.",
			exc=frappe.ValidationError,
		)

	return {"allowed": True, "used": used, "limit": limit, "remaining": limit - used}


def record_usage(user=None):
	"""Increment the message counter for the current window.

	The counter key expires after 3600 seconds (1 hour) so stale
	entries clean themselves up automatically.
	"""
	user = user or frappe.session.user
	cache = frappe.cache
	key = _rate_limit_key(user)

	current = cache.get_value(key)
	new_count = (int(current) if current else 0) + 1
	cache.set_value(key, new_count, expires_in_sec=3600)
