"""Redis-backed caching for expensive, rarely-changing data.

Uses Frappe's built-in Redis cache (`frappe.cache`) with key prefixes
so all Alcura cache entries can be invalidated in bulk when DocType
index configuration changes.
"""

import json

import frappe

CACHE_PREFIX = "alcura_ai"
DEFAULT_TTL = 300  # 5 minutes


def _make_key(suffix):
	return f"{CACHE_PREFIX}:{suffix}"


def get_cached(key, builder, ttl=DEFAULT_TTL):
	"""Return a cached value, calling *builder* to populate on miss.

	Args:
		key: Cache key suffix (will be prefixed with ``alcura_ai:``).
		builder: Zero-arg callable that produces the value to cache.
		ttl: Time-to-live in seconds (default 300).

	Returns:
		The cached (or freshly built) value.
	"""
	cache = frappe.cache
	full_key = _make_key(key)

	raw = cache.get_value(full_key)
	if raw is not None:
		try:
			return json.loads(raw)
		except (json.JSONDecodeError, TypeError):
			return raw

	value = builder()
	try:
		serialised = json.dumps(value, default=str)
	except (TypeError, ValueError):
		serialised = value
	cache.set_value(full_key, serialised, expires_in_sec=ttl)
	return value


def invalidate_all(doc=None, method=None):
	"""Remove every ``alcura_ai:*`` cache key.

	Called when AI DocType Index records are created, updated or deleted
	so that stale metadata never leaks into prompts.

	Accepts ``doc`` and ``method`` args so it can be used directly as a
	Frappe doc_event handler.
	"""
	cache = frappe.cache
	for suffix in ("indexed_doctypes", "tool_definitions"):
		cache.delete_value(_make_key(suffix))


def invalidate_key(suffix):
	frappe.cache.delete_value(_make_key(suffix))
