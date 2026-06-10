# Copyright (c) 2026, Swapnil Ghadigaonkar and contributors
# For license information, please see license.txt

"""Server API for the Insights Sidebar.

Security model: the client is never trusted. `get_sidebar_links` filters by role on
the server (so the browser only receives links the user may see), and
`get_dashboard_embed_url` re-validates on every call — role match, not-disabled, and
`frappe.has_permission` read on the dashboard — before returning an embed URL. The full
config list is cached once and role-filtered per request, so refreshes stay cheap.
"""

import frappe
from frappe import _

SIDEBAR_CACHE_KEY = "insights_sidebar_links"


def _load_configs():
	configs = frappe.get_all(
		"Insights Sidebar Config",
		filters={"disabled": 0},
		fields=["name", "label", "workspace", "insights_dashboard", "position"],
		order_by="position asc, label asc",
	)

	role_map = {}
	for row in frappe.get_all(
		"Has Role",
		filters={"parenttype": "Insights Sidebar Config"},
		fields=["parent", "role"],
	):
		role_map.setdefault(row.parent, []).append(row.role)

	for config in configs:
		config["roles"] = role_map.get(config["name"], [])

	return configs


def get_cached_configs():
	return frappe.cache().get_value(SIDEBAR_CACHE_KEY, _load_configs)


def clear_sidebar_cache():
	frappe.cache().delete_value(SIDEBAR_CACHE_KEY)


def has_role_access(allowed_roles):
	if not allowed_roles:
		return True
	return bool(set(frappe.get_roles()).intersection(allowed_roles))


@frappe.whitelist()
def get_sidebar_links():
	"""Return the sidebar links the current user is allowed to see.

	Role-filtered server-side; the dashboard name is intentionally not exposed here
	(the client opens a link via `get_dashboard_embed_url`, which re-checks access).
	"""
	links = []

	for config in get_cached_configs():
		if not has_role_access(config.get("roles")):
			continue

		links.append(
			{
				"config": config["name"],
				"label": config["label"],
				"workspace": config["workspace"],
				"position": config["position"],
			}
		)

	return links


@frappe.whitelist()
def get_dashboard_embed_url(config):
	"""Validate access and return the embed URL for a sidebar config's dashboard.

	Layered server-side enforcement (never trusts the client): the config must exist,
	not be disabled, match the user's roles, and the user must have `read` on the
	dashboard. Raises `PermissionError`/`DoesNotExistError` otherwise.
	"""
	if not frappe.db.exists("Insights Sidebar Config", config):
		frappe.throw(_("Sidebar item not found"), frappe.DoesNotExistError)

	doc = frappe.get_cached_doc("Insights Sidebar Config", config)
	allowed_roles = [row.role for row in doc.roles]

	if doc.disabled or not has_role_access(allowed_roles):
		raise frappe.PermissionError(_("You are not permitted to view this dashboard."))

	if not frappe.db.exists("Insights Dashboard v3", doc.insights_dashboard):
		frappe.throw(_("Linked dashboard no longer exists"), frappe.DoesNotExistError)

	# never hand out an embed URL the user can't actually read
	if not frappe.has_permission("Insights Dashboard v3", "read", doc=doc.insights_dashboard):
		raise frappe.PermissionError(_("You are not permitted to view this dashboard."))

	return {
		"label": doc.label,
		"url": f"/insights/dashboards/{doc.insights_dashboard}",
	}
