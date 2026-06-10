// Copyright (c) 2026, Swapnil Ghadigaonkar and contributors
// For license information, please see license.txt

frappe.ui.form.on("Insights Sidebar Config", {
	refresh(frm) {
		frm.set_query("workspace", () => ({ filters: { public: 1 } }));
		frm.set_query("role", "roles", () => ({ filters: { disabled: 0 } }));
		show_visibility_intro(frm);
	},
	roles_add: show_visibility_intro,
	roles_remove: show_visibility_intro,
});

function show_visibility_intro(frm) {
	const visible_to_all = !(frm.doc.roles || []).length;
	frm.set_intro(
		visible_to_all ? __("No roles selected — visible to all logged-in users.") : "",
		"blue"
	);
}
