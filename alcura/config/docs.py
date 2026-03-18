"""Documentation configuration for the Alcura app.

Used by `bench setup-docs` to generate documentation from source files.
"""


source_link = "https://github.com/alcura/alcura"
docs_base_url = "https://alcura.github.io/alcura"
headline = "Alcura Documentation"
sub_heading = "Custom Frappe Application"


def get_context(context):
	context.brand_html = "Alcura"
