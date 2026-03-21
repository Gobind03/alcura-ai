"""Sandboxed Python code interpreter for data analysis.

Executes LLM-generated Python code against pre-loaded pandas DataFrames
in a restricted environment. Captures printed output and matplotlib charts.
"""

import base64
import io
import json
import signal
import traceback

import frappe

from alcura_ai.services.data_service import _get_index_config, fetch_records

EXECUTION_TIMEOUT = 30

_PANDAS_AVAILABLE = True
_MATPLOTLIB_AVAILABLE = True
_NUMPY_AVAILABLE = True

try:
	import pandas  # noqa: F401
except ImportError:
	_PANDAS_AVAILABLE = False

try:
	import matplotlib  # noqa: F401
except ImportError:
	_MATPLOTLIB_AVAILABLE = False

try:
	import numpy  # noqa: F401
except ImportError:
	_NUMPY_AVAILABLE = False


def _check_dependencies():
	"""Raise a clear error if required analysis dependencies are missing."""
	missing = []
	if not _PANDAS_AVAILABLE:
		missing.append("pandas")
	if not _MATPLOTLIB_AVAILABLE:
		missing.append("matplotlib")
	if not _NUMPY_AVAILABLE:
		missing.append("numpy")
	if missing:
		raise ImportError(
			f"The run_analysis tool requires the following packages which are not installed: "
			f"{', '.join(missing)}. Install them with: pip install {' '.join(missing)}. "
			f"Use the other structured tools (date_series, aggregate_data, statistical_summary, "
			f"fetch_records) instead -- they do not require these dependencies."
		)

SAFE_BUILTINS = {
	"abs": abs,
	"all": all,
	"any": any,
	"bin": bin,
	"bool": bool,
	"bytes": bytes,
	"callable": callable,
	"chr": chr,
	"complex": complex,
	"dict": dict,
	"dir": dir,
	"divmod": divmod,
	"enumerate": enumerate,
	"filter": filter,
	"float": float,
	"format": format,
	"frozenset": frozenset,
	"getattr": getattr,
	"hasattr": hasattr,
	"hash": hash,
	"hex": hex,
	"int": int,
	"isinstance": isinstance,
	"issubclass": issubclass,
	"iter": iter,
	"len": len,
	"list": list,
	"map": map,
	"max": max,
	"min": min,
	"next": next,
	"object": object,
	"oct": oct,
	"ord": ord,
	"pow": pow,
	"range": range,
	"repr": repr,
	"reversed": reversed,
	"round": round,
	"set": set,
	"slice": slice,
	"sorted": sorted,
	"str": str,
	"sum": sum,
	"tuple": tuple,
	"type": type,
	"zip": zip,
	"True": True,
	"False": False,
	"None": None,
}

BLOCKED_BUILTINS = {
	"__import__", "eval", "exec", "compile", "globals", "locals",
	"open", "input", "breakpoint", "exit", "quit", "memoryview",
	"__build_class__",
}

ALLOWED_MODULES = {
	"pandas", "numpy", "math", "statistics", "datetime",
	"collections", "itertools", "functools", "decimal",
	"matplotlib", "matplotlib.pyplot",
}


def _safe_import(name, *args, **kwargs):
	"""Restricted import that only allows whitelisted modules."""
	if name not in ALLOWED_MODULES:
		top_level = name.split(".")[0]
		if top_level not in ALLOWED_MODULES:
			raise ImportError(f"Import of '{name}' is not allowed in the analysis sandbox.")
	return __builtins__["__import__"](name, *args, **kwargs) if isinstance(__builtins__, dict) else __import__(name, *args, **kwargs)


class _TimeoutError(Exception):
	pass


def _timeout_handler(signum, frame):
	raise _TimeoutError(f"Analysis execution timed out after {EXECUTION_TIMEOUT} seconds.")


def _load_datasets(datasets):
	"""Fetch data for each dataset spec and convert to pandas DataFrames.

	Args:
		datasets: dict of variable_name -> {"doctype": ..., "filters": ..., "fields": ..., "limit": ...}

	Returns:
		dict of variable_name -> pandas.DataFrame
	"""
	_check_dependencies()
	import pandas as pd

	frames = {}
	for var_name, spec in datasets.items():
		doctype = spec.get("doctype")
		if not doctype:
			raise ValueError(f"Dataset '{var_name}' is missing the 'doctype' key.")

		_get_index_config(doctype)

		records = fetch_records(
			doctype=doctype,
			filters=spec.get("filters"),
			fields=spec.get("fields"),
			limit=spec.get("limit"),
		)
		frames[var_name] = pd.DataFrame(records)

	return frames


def run_analysis(code, datasets=None):
	"""Execute Python code in a sandboxed environment with pre-loaded DataFrames.

	Args:
		code: Python source code to execute.
		datasets: dict of variable_name -> {"doctype", "filters", "fields", "limit"}.

	Returns:
		dict with:
		  - "output": captured print/stdout text
		  - "charts": list of {"title": str, "image_base64": str}
	"""
	_check_dependencies()

	import matplotlib
	matplotlib.use("Agg")
	import matplotlib.pyplot as plt

	import numpy as np
	import pandas as pd

	plt.close("all")

	frames = _load_datasets(datasets or {})

	stdout_capture = io.StringIO()

	namespace = {
		"__builtins__": {**SAFE_BUILTINS, "__import__": _safe_import},
		"pd": pd,
		"np": np,
		"plt": plt,
		"math": __import__("math"),
		"statistics": __import__("statistics"),
		"datetime": __import__("datetime"),
		"collections": __import__("collections"),
		"print": lambda *args, **kwargs: _sandbox_print(stdout_capture, *args, **kwargs),
	}

	for var_name, df in frames.items():
		namespace[var_name] = df

	has_alarm = hasattr(signal, "SIGALRM")

	try:
		compiled = compile(code, "<analysis>", "exec")

		if has_alarm:
			old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
			signal.alarm(EXECUTION_TIMEOUT)

		try:
			exec(compiled, namespace)
		finally:
			if has_alarm:
				signal.alarm(0)
				signal.signal(signal.SIGALRM, old_handler)

	except _TimeoutError as e:
		stdout_capture.write(f"\n[ERROR] {e}\n")
	except Exception:
		stdout_capture.write(f"\n[ERROR]\n{traceback.format_exc()}\n")

	charts = []
	for fig_num in plt.get_fignums():
		fig = plt.figure(fig_num)
		buf = io.BytesIO()
		fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
		buf.seek(0)
		charts.append({
			"title": fig.get_label() or f"Chart {fig_num}",
			"image_base64": base64.b64encode(buf.read()).decode("utf-8"),
		})
		buf.close()

	plt.close("all")

	return {
		"output": stdout_capture.getvalue(),
		"charts": charts,
	}


def _sandbox_print(buffer, *args, **kwargs):
	"""Redirect print() calls to a StringIO buffer."""
	kwargs.pop("file", None)
	print(*args, file=buffer, **kwargs)


def dispatch_analysis(arguments):
	"""Dispatch a run_analysis tool call. Returns JSON string + collected charts.

	Returns:
		tuple of (json_result_string, charts_list)
	"""
	code = arguments.get("code", "")
	datasets = arguments.get("datasets", {})

	if not code.strip():
		return json.dumps({"output": "", "charts": []}), []

	result = run_analysis(code, datasets)
	charts = result.pop("charts", [])
	return json.dumps(result, default=str), charts
