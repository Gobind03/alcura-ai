from frappe import _


def get_data():
	return [
		{
			"module_name": "Alcura",
			"type": "module",
			"label": _("Alcura"),
			"color": "#4F46E5",
			"icon": "octicon octicon-file-directory",
			"description": _("Custom Frappe Application"),
		}
	]
