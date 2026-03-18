import json

import frappe


def get_indexed_doctypes():
	"""Return metadata for all enabled AI DocType Index records."""
	indexes = frappe.get_all(
		"AI DocType Index",
		filters={"enabled": 1},
		fields=["name", "reference_doctype", "description", "max_records"],
	)

	result = []
	for idx in indexes:
		fields = frappe.get_all(
			"AI DocType Index Field",
			filters={"parent": idx.name, "parenttype": "AI DocType Index"},
			fields=["field_name", "field_label", "field_type"],
			order_by="idx asc",
		)
		result.append(
			{
				"doctype": idx.reference_doctype,
				"description": idx.description,
				"max_records": idx.max_records or 100,
				"fields": fields,
			}
		)

	return result


def _get_index_config(doctype):
	"""Get the index configuration for a given doctype, or throw if not indexed."""
	indexes = frappe.get_all(
		"AI DocType Index",
		filters={"reference_doctype": doctype, "enabled": 1},
		fields=["name", "reference_doctype", "max_records"],
	)

	if not indexes:
		raise ValueError(f"DocType '{doctype}' is not indexed or not enabled for AI access.")

	idx = indexes[0]
	allowed_fields = frappe.get_all(
		"AI DocType Index Field",
		filters={"parent": idx.name, "parenttype": "AI DocType Index"},
		fields=["field_name"],
		order_by="idx asc",
	)
	allowed_set = {f.field_name for f in allowed_fields}

	return {
		"name": idx.name,
		"doctype": idx.reference_doctype,
		"max_records": idx.max_records or 100,
		"allowed_fields": allowed_set,
	}


def _sanitize_fields(requested_fields, allowed_fields):
	"""Filter requested fields to only those that are allowed."""
	if not requested_fields:
		return list(allowed_fields)
	return [f for f in requested_fields if f in allowed_fields]


def _parse_filters(filters):
	"""Parse filters from various input formats into Frappe filter format."""
	if not filters:
		return {}
	if isinstance(filters, str):
		return json.loads(filters)
	return filters


def fetch_records(doctype, filters=None, fields=None, order_by=None, limit=None):
	"""Fetch records from an indexed DocType.

	Returns a list of dicts, scoped to allowed fields only.
	"""
	config = _get_index_config(doctype)

	safe_fields = _sanitize_fields(fields, config["allowed_fields"])
	if not safe_fields:
		return []

	max_limit = config["max_records"]
	if limit is None or limit > max_limit:
		limit = max_limit

	kwargs = {
		"doctype": doctype,
		"filters": _parse_filters(filters),
		"fields": safe_fields,
		"limit_page_length": limit,
	}

	if order_by:
		field_part = order_by.split(" ")[0].strip("`")
		if field_part in config["allowed_fields"]:
			kwargs["order_by"] = order_by

	return frappe.get_all(**kwargs)


def get_record_count(doctype, filters=None):
	"""Return the total count of records matching the given filters."""
	_get_index_config(doctype)
	return frappe.db.count(doctype, filters=_parse_filters(filters))


def get_distinct_values(doctype, field):
	"""Return distinct values for a field in an indexed DocType."""
	config = _get_index_config(doctype)

	if field not in config["allowed_fields"]:
		raise ValueError(f"Field '{field}' is not exposed for DocType '{doctype}'.")

	table = frappe.qb.DocType(doctype)
	results = (
		frappe.qb.from_(table)
		.select(table[field])
		.distinct()
		.limit(500)
		.run(as_dict=True)
	)
	return [r[field] for r in results if r[field] is not None]


def aggregate_data(doctype, field, function="COUNT", filters=None, group_by=None):
	"""Run an aggregation query on an indexed DocType.

	Supported functions: COUNT, SUM, AVG, MIN, MAX.
	"""
	config = _get_index_config(doctype)

	function = function.upper()
	if function not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
		raise ValueError(f"Unsupported aggregation function: {function}")

	if field != "*" and field not in config["allowed_fields"]:
		raise ValueError(f"Field '{field}' is not exposed for DocType '{doctype}'.")

	if group_by and group_by not in config["allowed_fields"]:
		raise ValueError(f"Group-by field '{group_by}' is not exposed for DocType '{doctype}'.")

	safe_filters = _parse_filters(filters)
	table = f"tab{doctype}"

	where_clause = ""
	values = {}
	if safe_filters and isinstance(safe_filters, dict):
		conditions = []
		for i, (k, v) in enumerate(safe_filters.items()):
			if k not in config["allowed_fields"]:
				raise ValueError(f"Filter field '{k}' is not exposed for DocType '{doctype}'.")
			param = f"p{i}"
			conditions.append(f"`{k}` = %({param})s")
			values[param] = v
		where_clause = "WHERE " + " AND ".join(conditions)

	if group_by:
		sql = f"SELECT `{group_by}` as group_key, {function}(`{field}`) as result FROM `{table}` {where_clause} GROUP BY `{group_by}` ORDER BY result DESC LIMIT 100"
	else:
		sql = f"SELECT {function}(`{field}`) as result FROM `{table}` {where_clause}"

	rows = frappe.db.sql(sql, values=values, as_dict=True)
	return rows


def dispatch_tool_call(name, arguments):
	"""Dispatch a tool call from OpenAI to the appropriate data function."""
	dispatchers = {
		"fetch_records": lambda args: json.dumps(
			fetch_records(
				doctype=args["doctype"],
				filters=args.get("filters"),
				fields=args.get("fields"),
				order_by=args.get("order_by"),
				limit=args.get("limit"),
			),
			default=str,
		),
		"get_record_count": lambda args: json.dumps(
			{"count": get_record_count(doctype=args["doctype"], filters=args.get("filters"))},
			default=str,
		),
		"get_distinct_values": lambda args: json.dumps(
			{"values": get_distinct_values(doctype=args["doctype"], field=args["field"])},
			default=str,
		),
		"aggregate_data": lambda args: json.dumps(
			aggregate_data(
				doctype=args["doctype"],
				field=args["field"],
				function=args.get("function", "COUNT"),
				filters=args.get("filters"),
				group_by=args.get("group_by"),
			),
			default=str,
		),
	}

	if name not in dispatchers:
		raise ValueError(f"Unknown tool: {name}")

	return dispatchers[name](arguments)


def build_tool_definitions():
	"""Generate OpenAI function-calling tool definitions."""
	indexed = get_indexed_doctypes()
	if not indexed:
		return []

	doctype_names = [d["doctype"] for d in indexed]
	doctype_enum_desc = ", ".join(doctype_names)

	return [
		{
			"type": "function",
			"function": {
				"name": "fetch_records",
				"description": f"Fetch records from an indexed DocType. Available DocTypes: {doctype_enum_desc}",
				"parameters": {
					"type": "object",
					"properties": {
						"doctype": {
							"type": "string",
							"description": "The DocType to query",
							"enum": doctype_names,
						},
						"filters": {
							"type": "object",
							"description": "Key-value filter conditions, e.g. {\"status\": \"Active\"}",
						},
						"fields": {
							"type": "array",
							"items": {"type": "string"},
							"description": "List of field names to return. If omitted, all allowed fields are returned.",
						},
						"order_by": {
							"type": "string",
							"description": "Sort expression, e.g. 'creation desc'",
						},
						"limit": {
							"type": "integer",
							"description": "Maximum number of records to return",
						},
					},
					"required": ["doctype"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "get_record_count",
				"description": f"Get the total count of records in a DocType, optionally filtered. Available DocTypes: {doctype_enum_desc}",
				"parameters": {
					"type": "object",
					"properties": {
						"doctype": {
							"type": "string",
							"description": "The DocType to count",
							"enum": doctype_names,
						},
						"filters": {
							"type": "object",
							"description": "Optional key-value filter conditions",
						},
					},
					"required": ["doctype"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "get_distinct_values",
				"description": f"Get all distinct/unique values for a specific field in a DocType. Useful for understanding categorical data. Available DocTypes: {doctype_enum_desc}",
				"parameters": {
					"type": "object",
					"properties": {
						"doctype": {
							"type": "string",
							"description": "The DocType to query",
							"enum": doctype_names,
						},
						"field": {
							"type": "string",
							"description": "The field name to get distinct values for",
						},
					},
					"required": ["doctype", "field"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "aggregate_data",
				"description": f"Run aggregation (COUNT, SUM, AVG, MIN, MAX) on a numeric field, optionally grouped by another field. Available DocTypes: {doctype_enum_desc}",
				"parameters": {
					"type": "object",
					"properties": {
						"doctype": {
							"type": "string",
							"description": "The DocType to aggregate",
							"enum": doctype_names,
						},
						"field": {
							"type": "string",
							"description": "The field to aggregate (use '*' for COUNT)",
						},
						"function": {
							"type": "string",
							"enum": ["COUNT", "SUM", "AVG", "MIN", "MAX"],
							"description": "The aggregation function",
						},
						"filters": {
							"type": "object",
							"description": "Optional key-value filter conditions",
						},
						"group_by": {
							"type": "string",
							"description": "Optional field to group results by",
						},
					},
					"required": ["doctype", "field"],
				},
			},
		},
	]
