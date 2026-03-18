from . import __version__ as app_version

app_name = "alcura"
app_title = "Alcura"
app_publisher = "Alcura"
app_description = "Custom Frappe Application"
app_email = "developers@alcura.com"
app_license = "MIT"

# --- Javascript / CSS Assets ---
app_include_js = ["alcura.bundle.js"]
app_include_css = ["alcura.bundle.css"]

# --- Apps Screen (v16 desktop) ---
add_to_apps_screen = [
	{
		"name": "alcura",
		"logo": "/assets/alcura/images/logo.png",
		"title": "Alcura",
		"route": "/desk/alcura",
	}
]

# Portal (injected in web.html)
# web_include_js = []
# web_include_css = []

# --- DocType Class Overrides ---
# override_doctype_class = {
# 	"ToDo": "alcura.overrides.todo.CustomToDo",
# }

# --- Doc Events ---
# Hook into document lifecycle events.
# doc_events = {
# 	"*": {
# 		"on_update": "alcura.services.handler.on_update",
# 	},
# 	"Sales Invoice": {
# 		"on_submit": "alcura.services.invoice.on_submit",
# 		"on_cancel": "alcura.services.invoice.on_cancel",
# 	},
# }

# --- Scheduled Tasks ---
# scheduler_events = {
# 	"cron": {
# 		"0/15 * * * *": [
# 			"alcura.services.cron.every_fifteen_minutes",
# 		],
# 	},
# 	"daily": [
# 		"alcura.services.daily.run_daily_tasks",
# 	],
# 	"hourly": [
# 		"alcura.services.hourly.run_hourly_tasks",
# 	],
# 	"weekly": [],
# 	"monthly": [],
# }

# --- Override Whitelisted Methods ---
# Last value in the list is used (last writer wins).
# override_whitelisted_methods = {
# 	"frappe.client.get_count": "alcura.api.v1.sample.custom_get_count",
# }

# --- Permissions ---
# permission_query_conditions = {
# 	"DocType Name": "alcura.utils.permissions.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"DocType Name": "alcura.utils.permissions.has_permission",
# }

# --- Jinja Customization ---
# jinja = {
# 	"methods": [
# 		"alcura.utils.jinja.custom_method",
# 	],
# 	"filters": [
# 		"alcura.utils.jinja.custom_filter",
# 	],
# }

# --- Boot Session ---
# extend_bootinfo = [
# 	"alcura.utils.boot.extend_bootinfo",
# ]

# --- Fixtures ---
# Automatically export/import these DocTypes during app install/update.
# fixtures = [
# 	{"dt": "Custom Field", "filters": [["module", "=", "Alcura"]]},
# 	{"dt": "Property Setter", "filters": [["module", "=", "Alcura"]]},
# ]

# --- Website Route Rules ---
# website_route_rules = [
# 	{"from_route": "/alcura/<path:app_path>", "to_route": "alcura"},
# ]

# --- Request Hooks ---
# before_request = []
# after_request = []

# --- Install Hooks ---
# before_install = "alcura.setup.install.before_install"
# after_install = "alcura.setup.install.after_install"
# before_uninstall = "alcura.setup.install.before_uninstall"
# after_uninstall = "alcura.setup.install.after_uninstall"

# --- Migration Hooks ---
# after_migrate = []
