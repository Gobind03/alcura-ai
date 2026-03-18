"""Tests for the sample API endpoints."""

import frappe
from frappe.tests.utils import FrappeTestCase

from alcura.api.v1.sample import echo, ping


class TestPingEndpoint(FrappeTestCase):
	def test_ping_returns_pong(self):
		result = ping()
		self.assertEqual(result["message"], "pong")
		self.assertEqual(result["app"], "alcura")
		self.assertIn("version", result)


class TestEchoEndpoint(FrappeTestCase):
	def test_echo_returns_text(self):
		result = echo(text="hello")
		self.assertEqual(result["echo"], "hello")

	def test_echo_without_text_raises(self):
		with self.assertRaises(frappe.MandatoryError):
			echo()
