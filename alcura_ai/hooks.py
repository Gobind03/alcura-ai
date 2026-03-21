from . import __version__ as app_version

app_name = "alcura_ai"
app_title = "Alcura"
app_publisher = "Alcura"
app_description = "Custom Frappe Application"
app_email = "developers@alcura.com"
app_license = "MIT"

# --- Javascript / CSS Assets ---
app_include_js = ["alcura_ai.bundle.js"]
app_include_css = ["alcura_ai.bundle.css"]

# --- Apps Screen (v16 desktop) ---
add_to_apps_screen = [
	{
		"name": "alcura_ai",
		"logo": "/assets/alcura_ai/images/logo.png",
		"title": "Alcura",
		"route": "/desk/alcura_ai",
	}
]

# Portal (injected in web.html)
# web_include_js = []
# web_include_css = []

# --- DocType Class Overrides ---
# override_doctype_class = {
# 	"ToDo": "alcura_ai.overrides.todo.CustomToDo",
# }

# --- Doc Events ---
# Invalidate the Redis cache for indexed-DocType metadata whenever the
# configuration changes, so stale data never leaks into AI prompts.
doc_events = {
	"AI DocType Index": {
		"after_insert": "alcura_ai.services.cache_service.invalidate_all",
		"on_update": "alcura_ai.services.cache_service.invalidate_all",
		"on_trash": "alcura_ai.services.cache_service.invalidate_all",
	},
	"Alcura AI Settings": {
		"on_update": "alcura_ai.services.cache_service.invalidate_all",
	},
	"Alcura Knowledge Source": {
		"after_insert": "alcura_ai.services.cache_service.invalidate_all",
		"on_update": "alcura_ai.services.cache_service.invalidate_all",
		"on_trash": "alcura_ai.services.cache_service.invalidate_all",
	},
}

# --- Scheduled Tasks ---
# scheduler_events = {
# 	"cron": {
# 		"0/15 * * * *": [
# 			"alcura_ai.services.cron.every_fifteen_minutes",
# 		],
# 	},
# 	"daily": [
# 		"alcura_ai.services.daily.run_daily_tasks",
# 	],
# 	"hourly": [
# 		"alcura_ai.services.hourly.run_hourly_tasks",
# 	],
# 	"weekly": [],
# 	"monthly": [],
# }

# --- Override Whitelisted Methods ---
# Last value in the list is used (last writer wins).
# override_whitelisted_methods = {
# 	"frappe.client.get_count": "alcura_ai.api.v1.sample.custom_get_count",
# }

# --- Permissions ---
# permission_query_conditions = {
# 	"DocType Name": "alcura_ai.utils.permissions.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"DocType Name": "alcura_ai.utils.permissions.has_permission",
# }

# --- Jinja Customization ---
# jinja = {
# 	"methods": [
# 		"alcura_ai.utils.jinja.custom_method",
# 	],
# 	"filters": [
# 		"alcura_ai.utils.jinja.custom_filter",
# 	],
# }

# --- Boot Session ---
# extend_bootinfo = [
# 	"alcura_ai.utils.boot.extend_bootinfo",
# ]

# --- Fixtures ---
# Automatically export/import these DocTypes during app install/update.
# fixtures = [
# 	{"dt": "Custom Field", "filters": [["module", "=", "Alcura"]]},
# 	{"dt": "Property Setter", "filters": [["module", "=", "Alcura"]]},
# ]

# --- Website Route Rules ---
# website_route_rules = [
# 	{"from_route": "/alcura_ai/<path:app_path>", "to_route": "alcura_ai"},
# ]

# --- Request Hooks ---
# before_request = []
# after_request = []

# --- Install Hooks ---
# before_install = "alcura_ai.setup.install.before_install"
# after_install = "alcura_ai.setup.install.after_install"
# before_uninstall = "alcura_ai.setup.install.before_uninstall"
# after_uninstall = "alcura_ai.setup.install.after_uninstall"

# --- Migration Hooks ---
# after_migrate = []
