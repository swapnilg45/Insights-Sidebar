# Copyright (c) 2026, Swapnil Ghadigaonkar and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from insights_sidebar.api import clear_sidebar_cache


class InsightsSidebarConfig(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.core.doctype.has_role.has_role import HasRole
		from frappe.types import DF

		disabled: DF.Check
		insights_dashboard: DF.Link
		label: DF.Data
		position: DF.Int
		roles: DF.Table[HasRole]
		workspace: DF.Link
	# end: auto-generated types

	def validate(self):
		self.validate_workspace_is_public()
		self.deduplicate_roles()
		if self.position and self.position < 0:
			self.position = 0

	def validate_workspace_is_public(self):
		if self.workspace and not frappe.db.get_value("Workspace", self.workspace, "public"):
			frappe.throw(_("Workspace {0} is private. Choose a public workspace.").format(frappe.bold(self.workspace)))

	def deduplicate_roles(self):
		seen = set()
		deduped = []
		for row in self.roles:
			if row.role and row.role not in seen:
				seen.add(row.role)
				deduped.append(row)
		self.roles = deduped

	def on_update(self):
		self.notify_change()

	def on_trash(self):
		self.notify_change()

	def after_rename(self, old, new, merge=False):
		self.notify_change()

	def notify_change(self):
		clear_sidebar_cache()
		frappe.publish_realtime("insights_sidebar_changed", after_commit=True)
