"""Shared pytest fixtures for Alcura tests.

Tests must be run via `bench run-tests --app alcura_ai` which initialises
the Frappe environment (database, site config, etc.) before test
collection begins.
"""

import pytest

import frappe
from frappe.tests.utils import FrappeTestCase


class AlcuraTestCase(FrappeTestCase):
	"""Base test case for Alcura.

	Provides automatic transaction rollback so each test starts with
	a clean database state. Subclass this instead of FrappeTestCase
	directly to pick up any app-wide fixtures.
	"""

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")


@pytest.fixture(autouse=True)
def _set_admin_user():
	"""Ensure each test runs as Administrator by default."""
	frappe.set_user("Administrator")
	yield
	frappe.set_user("Administrator")
