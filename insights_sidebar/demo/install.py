# Copyright (c) 2026, Swapnil Ghadigaonkar and contributors
# For license information, please see license.txt

"""Optional demo data for evaluating the Insights Sidebar.

Install:   bench --site <site> execute insights_sidebar.demo.install.install
Uninstall: bench --site <site> execute insights_sidebar.demo.install.uninstall

Data lives in demo/json/. The dashboards ship as an Insights workbook export and are
imported; roles, configs, users and doc-shares are created from the other JSON files.
"""

import json
import os

import frappe
from insights.insights.doctype.insights_workbook.insights_workbook import import_workbook

WORKBOOK_TITLE = "Insights Sidebar Demo"
DEMO_PASSWORD = "Test@1234"
BASE_ROLES = ["Purchase User", "Insights User"]  # Buying visibility + Insights APIs


def install():
	dashboards = import_dashboards()
	create_roles()
	create_configs(dashboards)
	users = create_users()
	share_dashboards(users)
	frappe.db.commit()
	print("Insights Sidebar demo data installed.")
	print(f"Test users (password {DEMO_PASSWORD}): " + ", ".join(u["email"] for u in _data("users")))


def uninstall():
	for config in _data("configs"):
		frappe.delete_doc("Insights Sidebar Config", config["label"], force=1, ignore_missing=True)
	for user in _data("users"):
		frappe.delete_doc("User", user["email"], force=1, ignore_missing=True)
	for role in _data("roles"):
		frappe.delete_doc("Role", role, force=1, ignore_missing=True)

	workbook = frappe.db.get_value("Insights Workbook", {"title": WORKBOOK_TITLE})
	if workbook:
		for doctype in ("Insights Dashboard v3", "Insights Chart v3", "Insights Query v3"):
			for name in frappe.get_all(doctype, filters={"workbook": workbook}, pluck="name"):
				frappe.delete_doc(doctype, name, force=1, ignore_missing=True)
		frappe.delete_doc("Insights Workbook", workbook, force=1, ignore_missing=True)

	frappe.db.commit()
	print("Insights Sidebar demo data removed.")


def import_dashboards():
	workbook = frappe.db.get_value("Insights Workbook", {"title": WORKBOOK_TITLE})
	if not workbook:
		with open(_json_path("workbook.json")) as f:
			workbook = import_workbook(f.read())

	titles = {config["dashboard_title"] for config in _data("configs")}
	return {
		title: frappe.db.get_value("Insights Dashboard v3", {"title": title, "workbook": workbook})
		for title in titles
	}


def create_roles():
	for role in _data("roles"):
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert()


def create_configs(dashboards):
	for config in _data("configs"):
		if frappe.db.exists("Insights Sidebar Config", config["label"]):
			continue
		frappe.get_doc(
			{
				"doctype": "Insights Sidebar Config",
				"label": config["label"],
				"workspace": config["workspace"],
				"insights_dashboard": dashboards[config["dashboard_title"]],
				"position": config["position"],
				"roles": [{"role": role} for role in config["roles"]],
			}
		).insert()


def create_users():
	users = []
	for row in _data("users"):
		if frappe.db.exists("User", row["email"]):
			user = frappe.get_doc("User", row["email"])
		else:
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": row["email"],
					"first_name": row["first_name"],
					"new_password": DEMO_PASSWORD,
					"send_welcome_email": 0,
				}
			).insert()

		assigned = {r.role for r in user.roles}
		for role in BASE_ROLES + row["roles"]:
			if role not in assigned:
				user.append("roles", {"role": role})
		user.save()
		users.append(row)
	return users


def share_dashboards(users):
	# share each dashboard with the users who are allowed to see its sidebar link
	for user in users:
		roles = set(BASE_ROLES) | set(user["roles"])
		for config in _data("configs"):
			if config["roles"] and not roles.intersection(config["roles"]):
				continue
			dashboard = frappe.db.get_value(
				"Insights Sidebar Config", config["label"], "insights_dashboard"
			)
			if dashboard:
				frappe.share.add("Insights Dashboard v3", dashboard, user["email"], read=1)


def _data(name):
	with open(_json_path(f"{name}.json")) as f:
		return json.load(f)


def _json_path(filename):
	return os.path.join(os.path.dirname(__file__), "json", filename)
