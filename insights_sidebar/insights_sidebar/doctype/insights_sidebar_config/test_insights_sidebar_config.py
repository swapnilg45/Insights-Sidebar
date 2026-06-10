# Copyright (c) 2026, Swapnil Ghadigaonkar and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from insights_sidebar.api import (
	clear_sidebar_cache,
	get_dashboard_embed_url,
	get_sidebar_links,
	has_role_access,
)

ROLE_A = "_Test Dashboard Role A"
ROLE_B = "_Test Dashboard Role B"
WORKSPACE = "Buying"

# These tests create their own fixtures with ignore_links, so skip the framework's
# recursive test-record loading for the link targets (it otherwise drags in erpnext
# setup like Fiscal Year, which clashes with existing data on a real site).
IGNORE_TEST_RECORD_DEPENDENCIES = ["Workspace", "Insights Dashboard v3", "Role"]


class IntegrationTestInsightsSidebarConfig(IntegrationTestCase):
	def setUp(self):
		clear_sidebar_cache()
		for role in (ROLE_A, ROLE_B):
			if not frappe.db.exists("Role", role):
				frappe.get_doc(
					{"doctype": "Role", "role_name": role, "desk_access": 1}
				).insert(ignore_permissions=True)

		# Links are created with ignore_links so the tests don't depend on a real
		# Insights Dashboard existing — the role/cache logic under test doesn't need one.
		self.cfg_a = self._make_config("_Test Config A", roles=[ROLE_A], position=1)
		self.cfg_b = self._make_config("_Test Config B", roles=[ROLE_B], position=2)
		self.cfg_all = self._make_config("_Test Config All", roles=[], position=3)

	def tearDown(self):
		frappe.set_user("Administrator")
		clear_sidebar_cache()

	def _make_config(self, label, roles, position, disabled=0, dashboard="_TEST-DASH"):
		if frappe.db.exists("Insights Sidebar Config", label):
			frappe.delete_doc("Insights Sidebar Config", label, force=1)
		doc = frappe.get_doc(
			{
				"doctype": "Insights Sidebar Config",
				"label": label,
				"workspace": WORKSPACE,
				"insights_dashboard": dashboard,
				"position": position,
				"disabled": disabled,
				"roles": [{"role": role} for role in roles],
			}
		)
		doc.insert(ignore_permissions=True, ignore_links=True)
		return doc.name

	# --- has_role_access (pure logic) -------------------------------------------------

	def test_empty_roles_visible_to_everyone(self):
		self.assertTrue(has_role_access([]))

	def test_role_access_intersection(self):
		with patch("frappe.get_roles", return_value=["System Manager", ROLE_A]):
			self.assertTrue(has_role_access([ROLE_A]))
			self.assertFalse(has_role_access([ROLE_B]))

	# --- get_sidebar_links (role filtering) -------------------------------------------

	def test_links_filtered_by_role(self):
		with patch("frappe.get_roles", return_value=[ROLE_A]):
			labels = {link["label"] for link in get_sidebar_links()}
		self.assertIn("_Test Config A", labels)
		self.assertIn("_Test Config All", labels)  # empty roles -> visible to all
		self.assertNotIn("_Test Config B", labels)

	def test_links_unrelated_role_hides_role_gated_items(self):
		# a user with neither role must not see either role-gated item, but still sees
		# open (empty-role) items. Asserted as a subset so unrelated configs on the site
		# (e.g. seeded demo data) don't make the test brittle.
		with patch("frappe.get_roles", return_value=["_Some Unrelated Role"]):
			labels = {link["label"] for link in get_sidebar_links()}
		self.assertNotIn("_Test Config A", labels)
		self.assertNotIn("_Test Config B", labels)
		self.assertIn("_Test Config All", labels)

	def test_links_omit_dashboard_name(self):
		# the dashboard docname must not leak to the client
		with patch("frappe.get_roles", return_value=[ROLE_A]):
			links = get_sidebar_links()
		self.assertTrue(links)
		self.assertTrue(all("dashboard" not in link for link in links))

	def test_disabled_config_excluded_from_links(self):
		self._make_config("_Test Config Disabled", roles=[], position=4, disabled=1)
		clear_sidebar_cache()
		with patch("frappe.get_roles", return_value=[ROLE_A]):
			labels = {link["label"] for link in get_sidebar_links()}
		self.assertNotIn("_Test Config Disabled", labels)

	# --- get_dashboard_embed_url (server-side enforcement) ----------------------------

	def test_embed_url_blocks_role_mismatch(self):
		with patch("frappe.get_roles", return_value=[ROLE_A]):
			with self.assertRaises(frappe.PermissionError):
				get_dashboard_embed_url(self.cfg_b)

	def test_embed_url_blocks_disabled(self):
		cfg = self._make_config("_Test Config Disabled2", roles=[], position=5, disabled=1)
		with self.assertRaises(frappe.PermissionError):
			get_dashboard_embed_url(cfg)

	def test_embed_url_missing_config(self):
		with self.assertRaises(frappe.DoesNotExistError):
			get_dashboard_embed_url("_Nonexistent Config")

	def test_embed_url_happy_path(self):
		# authorized + dashboard exists + has read -> returns the embed URL.
		# The dashboard existence/read are mocked so the test needs no real Insights doc.
		with (
			patch("frappe.get_roles", return_value=[ROLE_A]),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.has_permission", return_value=True),
		):
			result = get_dashboard_embed_url(self.cfg_a)
		self.assertEqual(result["url"], "/insights/dashboards/_TEST-DASH")

	# --- controller validations -------------------------------------------------------

	def test_duplicate_roles_removed(self):
		cfg = self._make_config("_Test Config Dupes", roles=[ROLE_A, ROLE_A, ROLE_B], position=7)
		doc = frappe.get_doc("Insights Sidebar Config", cfg)
		self.assertEqual([row.role for row in doc.roles], [ROLE_A, ROLE_B])

	def test_negative_position_clamped(self):
		cfg = self._make_config("_Test Config NegPos", roles=[], position=-5)
		self.assertEqual(frappe.db.get_value("Insights Sidebar Config", cfg, "position"), 0)

	# --- cache invalidation -----------------------------------------------------------

	def test_cache_cleared_on_save(self):
		# behaviour-based: a saved change must be reflected on the next fetch (i.e. the
		# cache was invalidated by on_update). Asserting the cache key directly is fragile
		# because get_cached_configs repopulates it on the very next read.
		self.assertIn(self.cfg_a, [link["config"] for link in get_sidebar_links()])
		doc = frappe.get_doc("Insights Sidebar Config", self.cfg_a)
		doc.disabled = 1
		doc.flags.ignore_links = True  # the test fixture uses a dummy dashboard link
		doc.save(ignore_permissions=True)
		self.assertNotIn(self.cfg_a, [link["config"] for link in get_sidebar_links()])

	def test_cache_cleared_on_delete(self):
		self.assertIn(self.cfg_a, [link["config"] for link in get_sidebar_links()])
		frappe.delete_doc("Insights Sidebar Config", self.cfg_a, force=1)
		self.assertNotIn(self.cfg_a, [link["config"] for link in get_sidebar_links()])
