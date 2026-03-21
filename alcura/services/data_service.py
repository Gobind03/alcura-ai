import json
import math

import frappe


ALLOWED_FILTER_OPS = {"=", "!=", ">", "<", ">=", "<=", "between", "in", "not in", "like", "not like", "is", "is not"}

DATE_PERIOD_FORMATS = {
	"day": "%Y-%m-%d",
	"week": "%x-W%v",
	"month": "%Y-%m",
	"quarter": None,
	"year": "%Y",
}


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
		available = frappe.get_all(
			"AI DocType Index",
			filters={"enabled": 1},
			fields=["reference_doctype"],
		)
		available_names = [a.reference_doctype for a in available]
		raise ValueError(
			f"DocType '{doctype}' is not indexed or not enabled for AI access. "
			f"Available indexed DocTypes: {', '.join(available_names) or 'none'}. "
			f"Use one of those instead."
		)

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
	"""Parse filters from various input formats into a normalised list-of-lists.

	Accepts:
	  - dict: {"field": "value"} or {"field": ["op", "value"]} (Frappe shorthand)
	  - list of lists: [["field", "operator", "value"], ...]
	  - JSON string of either form

	Always returns a list-of-lists or an empty list so downstream code
	only needs to handle one format.
	"""
	if not filters:
		return []
	if isinstance(filters, str):
		filters = json.loads(filters)

	if isinstance(filters, dict):
		normalised = []
		for k, v in filters.items():
			if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str):
				normalised.append([k, v[0], v[1]])
			else:
				normalised.append([k, "=", v])
		return normalised

	if isinstance(filters, list):
		return filters

	return []


def _validate_filter_fields(filters, allowed_fields):
	"""Validate that all filter fields are in the allowed set."""
	if not filters:
		return
	for condition in filters:
		if not isinstance(condition, (list, tuple)):
			continue
		field = condition[0]
		if field not in allowed_fields:
			raise ValueError(
				f"Filter field '{field}' is not exposed. "
				f"Allowed fields: {', '.join(sorted(allowed_fields))}"
			)


def _build_sql_where(filters, allowed_fields):
	"""Build a parameterised SQL WHERE clause from list-of-lists filters.

	``filters`` should already be normalised by ``_parse_filters`` into
	``[[field, op, value], ...]`` format.

	Returns (where_clause_str, values_dict).
	"""
	if not filters:
		return "", {}

	if isinstance(filters, dict):
		filters = _parse_filters(filters)

	conditions = []
	values = {}

	for i, condition in enumerate(filters):
		if not isinstance(condition, (list, tuple)) or len(condition) < 3:
			raise ValueError(f"Invalid filter format: {condition}")
		field, op, value = condition[0], condition[1].lower(), condition[2]
		if field not in allowed_fields:
			raise ValueError(
				f"Filter field '{field}' is not exposed for this DocType. "
				f"Allowed fields: {', '.join(sorted(allowed_fields))}"
			)
		if op not in ALLOWED_FILTER_OPS:
			raise ValueError(
				f"Unsupported filter operator: '{op}'. "
				f"Allowed operators: {', '.join(sorted(ALLOWED_FILTER_OPS))}"
			)

		param = f"p{i}"
		if op == "between":
			if not isinstance(value, (list, tuple)) or len(value) != 2:
				raise ValueError("'between' operator requires a list of two values.")
			lo, hi = f"{param}_lo", f"{param}_hi"
			conditions.append(f"`{field}` BETWEEN %({lo})s AND %({hi})s")
			values[lo] = value[0]
			values[hi] = value[1]
		elif op in ("in", "not in"):
			if not isinstance(value, (list, tuple)):
				raise ValueError(f"'{op}' operator requires a list of values.")
			placeholders = ", ".join(f"%({param}_{j})s" for j in range(len(value)))
			keyword = "IN" if op == "in" else "NOT IN"
			conditions.append(f"`{field}` {keyword} ({placeholders})")
			for j, v in enumerate(value):
				values[f"{param}_{j}"] = v
		elif op in ("is", "is not"):
			keyword = "IS" if op == "is" else "IS NOT"
			conditions.append(f"`{field}` {keyword} NULL")
		elif op == "like":
			conditions.append(f"`{field}` LIKE %({param})s")
			values[param] = value
		elif op == "not like":
			conditions.append(f"`{field}` NOT LIKE %({param})s")
			values[param] = value
		else:
			sql_op = {"=": "=", "!=": "!=", ">": ">", "<": "<", ">=": ">=", "<=": "<="}[op]
			conditions.append(f"`{field}` {sql_op} %({param})s")
			values[param] = value

	if not conditions:
		return "", {}
	return "WHERE " + " AND ".join(conditions), values


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

	parsed = _parse_filters(filters)
	_validate_filter_fields(parsed, config["allowed_fields"])

	kwargs = {
		"doctype": doctype,
		"filters": parsed,
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
	config = _get_index_config(doctype)
	parsed = _parse_filters(filters)
	_validate_filter_fields(parsed, config["allowed_fields"])
	return frappe.db.count(doctype, filters=parsed)


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


def aggregate_data(doctype, field, function="COUNT", filters=None, group_by=None, aggregations=None):
	"""Run an aggregation query on an indexed DocType.

	Supports two modes:
	  1. Single aggregation: provide ``field`` and ``function``.
	  2. Multi-aggregation: provide ``aggregations`` as a list of
	     ``{"field": ..., "function": ...}`` dicts.

	Supported functions: COUNT, SUM, AVG, MIN, MAX.
	"""
	config = _get_index_config(doctype)

	agg_list = []
	if aggregations:
		for agg in aggregations:
			fn = agg.get("function", "COUNT").upper()
			fld = agg.get("field", "*")
			if fn not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
				raise ValueError(f"Unsupported aggregation function: {fn}")
			if fld != "*" and fld not in config["allowed_fields"]:
				raise ValueError(f"Field '{fld}' is not exposed for DocType '{doctype}'.")
			agg_list.append((fn, fld))
	else:
		function = function.upper()
		if function not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
			raise ValueError(f"Unsupported aggregation function: {function}")
		if field != "*" and field not in config["allowed_fields"]:
			raise ValueError(f"Field '{field}' is not exposed for DocType '{doctype}'.")
		agg_list.append((function, field))

	if group_by and group_by not in config["allowed_fields"]:
		raise ValueError(f"Group-by field '{group_by}' is not exposed for DocType '{doctype}'.")

	table = f"tab{doctype}"
	where_clause, values = _build_sql_where(_parse_filters(filters), config["allowed_fields"])

	select_parts = []
	for i, (fn, fld) in enumerate(agg_list):
		col_ref = f"`{fld}`" if fld != "*" else fld
		alias = f"result" if len(agg_list) == 1 else f"result_{i}"
		select_parts.append(f"{fn}({col_ref}) as {alias}")

	select_clause = ", ".join(select_parts)

	if group_by:
		sql = f"SELECT `{group_by}` as group_key, {select_clause} FROM `{table}` {where_clause} GROUP BY `{group_by}` ORDER BY {select_parts[0].split(' as ')[0]} DESC LIMIT 100"
	else:
		sql = f"SELECT {select_clause} FROM `{table}` {where_clause}"

	rows = frappe.db.sql(sql, values=values, as_dict=True)
	return rows


def date_series(doctype, date_field, period="month", metric_field="*", function="COUNT", filters=None):
	"""Group records by a date period and compute an aggregate.

	Args:
		doctype: The indexed DocType to query.
		date_field: A date/datetime field to group by.
		period: One of 'day', 'week', 'month', 'quarter', 'year'.
		metric_field: The field to aggregate (use '*' for COUNT).
		function: COUNT, SUM, AVG, MIN, or MAX.
		filters: Optional filters (dict or list-of-lists).

	Returns:
		List of dicts with 'period' and 'result' keys.
	"""
	config = _get_index_config(doctype)

	if date_field not in config["allowed_fields"]:
		raise ValueError(f"Date field '{date_field}' is not exposed for DocType '{doctype}'.")
	if metric_field != "*" and metric_field not in config["allowed_fields"]:
		raise ValueError(f"Metric field '{metric_field}' is not exposed for DocType '{doctype}'.")

	period = period.lower()
	if period not in DATE_PERIOD_FORMATS:
		raise ValueError(f"Unsupported period: '{period}'. Use one of: day, week, month, quarter, year.")

	function = function.upper()
	if function not in {"COUNT", "SUM", "AVG", "MIN", "MAX"}:
		raise ValueError(f"Unsupported aggregation function: {function}")

	table = f"tab{doctype}"
	where_clause, values = _build_sql_where(_parse_filters(filters), config["allowed_fields"])

	col_ref = f"`{metric_field}`" if metric_field != "*" else metric_field

	if period == "quarter":
		period_expr = f"CONCAT(YEAR(`{date_field}`), '-Q', QUARTER(`{date_field}`))"
	else:
		fmt = DATE_PERIOD_FORMATS[period]
		# Double the % signs so they survive frappe.db.sql's %-formatting
		# e.g. '%Y-%m' becomes '%%Y-%%m' which produces '%Y-%m' in the final SQL
		safe_fmt = fmt.replace("%", "%%")
		period_expr = f"DATE_FORMAT(`{date_field}`, '{safe_fmt}')"

	sql = (
		f"SELECT {period_expr} as period, {function}({col_ref}) as result "
		f"FROM `{table}` {where_clause} "
		f"GROUP BY period ORDER BY period ASC LIMIT 1000"
	)

	rows = frappe.db.sql(sql, values=values, as_dict=True)
	return [r for r in rows if r.get("period") is not None]


def statistical_summary(doctype, field, filters=None):
	"""Return a statistical summary for a numeric field.

	Returns dict with: count, sum, avg, min, max, stddev, median, p25, p75.
	"""
	config = _get_index_config(doctype)

	if field not in config["allowed_fields"]:
		raise ValueError(f"Field '{field}' is not exposed for DocType '{doctype}'.")

	table = f"tab{doctype}"
	where_clause, values = _build_sql_where(_parse_filters(filters), config["allowed_fields"])

	sql = (
		f"SELECT COUNT(`{field}`) as `count`, "
		f"SUM(`{field}`) as `sum`, "
		f"AVG(`{field}`) as `avg`, "
		f"MIN(`{field}`) as `min`, "
		f"MAX(`{field}`) as `max`, "
		f"STDDEV_POP(`{field}`) as `stddev` "
		f"FROM `{table}` {where_clause}"
	)
	row = frappe.db.sql(sql, values=values, as_dict=True)[0]

	result = {
		"count": row["count"] or 0,
		"sum": float(row["sum"]) if row["sum"] is not None else 0.0,
		"avg": float(row["avg"]) if row["avg"] is not None else 0.0,
		"min": float(row["min"]) if row["min"] is not None else 0.0,
		"max": float(row["max"]) if row["max"] is not None else 0.0,
		"stddev": float(row["stddev"]) if row["stddev"] is not None else 0.0,
	}

	count = result["count"]
	if count > 0:
		sorted_sql = (
			f"SELECT `{field}` as val FROM `{table}` {where_clause} "
			f"AND `{field}` IS NOT NULL ORDER BY `{field}` ASC"
		) if where_clause else (
			f"SELECT `{field}` as val FROM `{table}` "
			f"WHERE `{field}` IS NOT NULL ORDER BY `{field}` ASC"
		)
		sorted_rows = frappe.db.sql(sorted_sql, values=values, as_dict=True)
		vals = [float(r["val"]) for r in sorted_rows]

		def _percentile(sorted_vals, p):
			n = len(sorted_vals)
			if n == 0:
				return 0.0
			k = (n - 1) * (p / 100.0)
			f_idx = math.floor(k)
			c_idx = math.ceil(k)
			if f_idx == c_idx:
				return sorted_vals[int(k)]
			return sorted_vals[f_idx] * (c_idx - k) + sorted_vals[c_idx] * (k - f_idx)

		result["p25"] = _percentile(vals, 25)
		result["median"] = _percentile(vals, 50)
		result["p75"] = _percentile(vals, 75)
	else:
		result["p25"] = 0.0
		result["median"] = 0.0
		result["p75"] = 0.0

	return result


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
				field=args.get("field", "*"),
				function=args.get("function", "COUNT"),
				filters=args.get("filters"),
				group_by=args.get("group_by"),
				aggregations=args.get("aggregations"),
			),
			default=str,
		),
		"date_series": lambda args: json.dumps(
			date_series(
				doctype=args["doctype"],
				date_field=args["date_field"],
				period=args.get("period", "month"),
				metric_field=args.get("metric_field", "*"),
				function=args.get("function", "COUNT"),
				filters=args.get("filters"),
			),
			default=str,
		),
		"statistical_summary": lambda args: json.dumps(
			statistical_summary(
				doctype=args["doctype"],
				field=args["field"],
				filters=args.get("filters"),
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
							"oneOf": [
								{
									"type": "object",
									"description": "Key-value equality filters, e.g. {\"status\": \"Active\"}",
								},
								{
									"type": "array",
									"items": {
										"type": "array",
										"items": {},
										"minItems": 3,
										"maxItems": 3,
									},
									"description": "Operator filters as [[field, op, value], ...]. Operators: =, !=, >, <, >=, <=, between, in, not in, like, not like, is, is not",
								},
							],
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
							"oneOf": [
								{"type": "object", "description": "Key-value equality filters"},
								{
									"type": "array",
									"items": {"type": "array", "items": {}, "minItems": 3, "maxItems": 3},
									"description": "Operator filters [[field, op, value], ...]",
								},
							],
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
				"description": f"Run aggregation (COUNT, SUM, AVG, MIN, MAX) on a field, optionally grouped. Supports single or multiple aggregations in one call. Available DocTypes: {doctype_enum_desc}",
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
							"description": "The field to aggregate (use '*' for COUNT). Ignored when 'aggregations' is provided.",
						},
						"function": {
							"type": "string",
							"enum": ["COUNT", "SUM", "AVG", "MIN", "MAX"],
							"description": "The aggregation function. Ignored when 'aggregations' is provided.",
						},
						"aggregations": {
							"type": "array",
							"items": {
								"type": "object",
								"properties": {
									"field": {"type": "string"},
									"function": {"type": "string", "enum": ["COUNT", "SUM", "AVG", "MIN", "MAX"]},
								},
								"required": ["field", "function"],
							},
							"description": "Multiple aggregations: [{field, function}, ...]. When provided, 'field' and 'function' params are ignored.",
						},
						"filters": {
							"oneOf": [
								{"type": "object"},
								{"type": "array", "items": {"type": "array", "items": {}, "minItems": 3, "maxItems": 3}},
							],
							"description": "Optional filter conditions",
						},
						"group_by": {
							"type": "string",
							"description": "Optional field to group results by",
						},
					},
					"required": ["doctype"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "date_series",
				"description": f"Group records by a time period (day/week/month/quarter/year) and compute an aggregate. Ideal for trend and time-series analysis. Available DocTypes: {doctype_enum_desc}",
				"parameters": {
					"type": "object",
					"properties": {
						"doctype": {
							"type": "string",
							"description": "The DocType to query",
							"enum": doctype_names,
						},
						"date_field": {
							"type": "string",
							"description": "The date or datetime field to group by",
						},
						"period": {
							"type": "string",
							"enum": ["day", "week", "month", "quarter", "year"],
							"description": "Time period granularity",
						},
						"metric_field": {
							"type": "string",
							"description": "The field to aggregate (default '*' for COUNT)",
						},
						"function": {
							"type": "string",
							"enum": ["COUNT", "SUM", "AVG", "MIN", "MAX"],
							"description": "The aggregation function (default COUNT)",
						},
						"filters": {
							"oneOf": [
								{"type": "object"},
								{"type": "array", "items": {"type": "array", "items": {}, "minItems": 3, "maxItems": 3}},
							],
							"description": "Optional filter conditions",
						},
					},
					"required": ["doctype", "date_field", "period"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "statistical_summary",
				"description": f"Get a full statistical summary of a numeric field: count, sum, avg, min, max, stddev, median, 25th and 75th percentiles. Available DocTypes: {doctype_enum_desc}",
				"parameters": {
					"type": "object",
					"properties": {
						"doctype": {
							"type": "string",
							"description": "The DocType to analyze",
							"enum": doctype_names,
						},
						"field": {
							"type": "string",
							"description": "The numeric field to summarize",
						},
						"filters": {
							"oneOf": [
								{"type": "object"},
								{"type": "array", "items": {"type": "array", "items": {}, "minItems": 3, "maxItems": 3}},
							],
							"description": "Optional filter conditions",
						},
					},
					"required": ["doctype", "field"],
				},
			},
		},
		{
			"type": "function",
			"function": {
				"name": "run_analysis",
				"description": (
					"Execute Python/pandas code to perform advanced data analysis and create charts. "
					"Data from indexed DocTypes is pre-loaded as pandas DataFrames. "
					"Available libraries: pandas (pd), numpy (np), matplotlib.pyplot (plt), math, statistics, datetime, collections. "
					"Use print() to output results. Use plt to create charts (bar, line, pie, scatter, hist, etc.). "
					f"Available DocTypes for datasets: {doctype_enum_desc}"
				),
				"parameters": {
					"type": "object",
					"properties": {
						"code": {
							"type": "string",
							"description": "Python code to execute. Use print() for output and plt for charts.",
						},
						"datasets": {
							"type": "object",
							"description": "Dict of variable_name -> {doctype, filters, fields, limit}. Each becomes a pandas DataFrame accessible by variable_name in the code.",
							"additionalProperties": {
								"type": "object",
								"properties": {
									"doctype": {"type": "string", "enum": doctype_names},
									"filters": {},
									"fields": {"type": "array", "items": {"type": "string"}},
									"limit": {"type": "integer"},
								},
								"required": ["doctype"],
							},
						},
					},
					"required": ["code", "datasets"],
				},
			},
		},
	]
