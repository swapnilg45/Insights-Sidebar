// Copyright (c) 2026, Swapnil Ghadigaonkar and contributors
// For license information, please see license.txt

// In v16 the workspace sidebar is data-driven by the global `frappe.ui.Sidebar`, so we
// inject our role-filtered links into its item list (as a collapsible section) instead of
// touching the DOM, and swap the workspace body to an iframe in-place when one is clicked.

frappe.provide("insights_sidebar");

insights_sidebar.Sidebar = class Sidebar {
	constructor() {
		this.links = null;
		this.links_by_config = {};
		this.pending_config = null;

		this.load_links();
		this.patch_sidebar();
		this.patch_workspace();
		this.bind_clicks();
		this.bind_realtime();
	}

	bind_realtime() {
		// a config was added/edited/deleted/renamed anywhere — refresh this client's sidebar.
		// frappe.realtime.on() silently no-ops until the socket exists, so poll until it does.
		if (frappe.boot && frappe.boot.disable_async) return;

		const register = () => {
			if (!frappe.realtime || !frappe.realtime.socket) return false;
			frappe.realtime.on("insights_sidebar_changed", () => this.load_links());
			return true;
		};

		if (register()) return;
		const timer = setInterval(() => {
			if (register()) clearInterval(timer);
		}, 1000);
	}

	async load_links() {
		try {
			this.links = (await frappe.xcall("insights_sidebar.api.get_sidebar_links")) || [];
		} catch (e) {
			this.links = [];
		}

		this.links_by_config = {};
		this.links.forEach((link) => {
			this.links_by_config[link.config] = link;
		});

		// if the dashboard currently open was just removed, close it
		const open = this.config_from_url();
		if (open && !this.links_by_config[open]) {
			this.close();
		}

		// the sidebar may have rendered before this call resolved; redraw so our items show
		if (frappe.app && frappe.app.sidebar && frappe.app.sidebar.sidebar_title) {
			frappe.app.sidebar.make_sidebar();
		}
	}

	patch_sidebar() {
		if (!frappe.ui || !frappe.ui.Sidebar) {
			setTimeout(() => this.patch_sidebar(), 200);
			return;
		}

		const proto = frappe.ui.Sidebar.prototype;
		if (proto.__insights_sidebar_patched) return;
		proto.__insights_sidebar_patched = true;

		const me = this;
		const make_sidebar = proto.make_sidebar;
		proto.make_sidebar = function () {
			me.inject_items(this);
			make_sidebar.apply(this, arguments);
			me.highlight(me.config_from_url());
		};
	}

	patch_workspace() {
		if (!frappe.views || !frappe.views.Workspace) {
			setTimeout(() => this.patch_workspace(), 200);
			return;
		}

		const proto = frappe.views.Workspace.prototype;
		if (proto.__insights_sidebar_patched) return;
		proto.__insights_sidebar_patched = true;

		const me = this;
		const show_page = proto.show_page;
		proto.show_page = async function () {
			const result = await show_page.apply(this, arguments);
			me.restore();
			return result;
		};
	}

	bind_clicks() {
		// Capture phase: Frappe's own delegated link handler returns false (stopPropagation)
		// for in-app routes, so a bubbling handler would never fire. Capturing wins the click.
		document.addEventListener(
			"click",
			(e) => {
				const anchor =
					e.target.closest &&
					e.target.closest("a.item-anchor[href*='insights_dashboard=']");
				if (!anchor) return;

				e.preventDefault();
				e.stopPropagation();

				const match = (anchor.getAttribute("href") || "").match(
					/[?&]insights_dashboard=([^&]+)/
				);
				if (match) this.open(decodeURIComponent(match[1]));
			},
			true
		);
	}

	inject_items(sidebar) {
		if (sidebar.editor && sidebar.editor.edit_mode) return;

		// Always strip any section we added before, *first* — so when the last visible item
		// is removed/disabled the group disappears instead of lingering. Then re-add if needed.
		const items = (sidebar.workspace_sidebar_items || []).filter((it) => !it._insights_section);
		sidebar.workspace_sidebar_items = items;

		const title = sidebar.sidebar_title;
		if (!this.links || !this.links.length || !title) return;

		// the v16 sidebar is keyed by workspace title; assumes name == title (true for stock workspaces)
		const mine = this.links
			.filter((link) => (link.workspace || "").toLowerCase() === title.toLowerCase())
			.sort((a, b) => (a.position || 0) - (b.position || 0));
		if (!mine.length) return;

		const section = {
			type: "Section Break",
			label: __("Insights Dashboards"),
			collapsible: 1,
			_insights_section: true,
			nested_items: [],
		};

		mine.forEach((link) => {
			section.nested_items.push({
				type: "Link",
				link_type: "Workspace", // avoids target="_blank" so it never opens a new tab
				link_to: link.workspace,
				label: link.label,
				icon: "dashboard",
				child: 1,
				parent: section,
				route: `/desk/${frappe.router.slug(link.workspace)}?insights_dashboard=${encodeURIComponent(
					link.config
				)}`,
				_insights_config: link.config,
			});
		});

		sidebar.workspace_sidebar_items = items.concat([section]);
	}

	open(config) {
		const link = this.links_by_config[config];
		if (!link) return;

		const ws = frappe.workspace;
		const on_workspace =
			ws && ws._page && (ws._page.name || "").toLowerCase() === link.workspace.toLowerCase();

		if (on_workspace) {
			// same route, so show_page won't fire — render directly
			this.show_dashboard(config);
		} else {
			this.pending_config = config;
			frappe.set_route(frappe.router.slug(link.workspace));
		}
	}

	restore() {
		const config = this.config_from_url() || this.pending_config;
		this.pending_config = null;

		if (!config) {
			this.close();
			return;
		}

		const link = this.links_by_config[config];
		const ws = frappe.workspace;
		if (!link || !ws || !ws._page) return;

		if ((ws._page.name || "").toLowerCase() !== link.workspace.toLowerCase()) {
			this.close();
			return;
		}

		this.show_dashboard(config);
	}

	async show_dashboard(config) {
		const ws = frappe.workspace;
		if (!ws || !ws.body) return;

		let data;
		try {
			data = await frappe.xcall("insights_sidebar.api.get_dashboard_embed_url", { config });
		} catch (e) {
			this.close();
			return;
		}

		const $body = ws.body;
		$body.find(".insights-dashboard-wrap").remove();

		const $wrap = $(
			`<div class="insights-dashboard-wrap">
				<iframe class="insights-dashboard-frame" title="${frappe.utils.escape_html(
					data.label
				)}" src="${data.url}" frameborder="0"></iframe>
			</div>`
		).appendTo($body);

		$body.children().not(".insights-dashboard-wrap").addClass("insights-hidden");

		$wrap.find("iframe").on("load", function () {
			insights_sidebar.hide_chrome(this);
		});

		ws.page && ws.page.set_title(data.label);
		this.set_query(config);
		this.highlight(config);
	}

	close() {
		const ws = frappe.workspace;
		if (!ws || !ws.body) return;
		ws.body.find(".insights-dashboard-wrap").remove();
		ws.body.children().removeClass("insights-hidden");
		this.highlight(null);
	}

	highlight(config) {
		if (config) {
			$(".body-sidebar .standard-sidebar-item").removeClass("active-sidebar");
			const selector = `.body-sidebar a.item-anchor[href*="insights_dashboard=${encodeURIComponent(
				config
			)}"]`;
			$(selector).parent().addClass("active-sidebar");
		} else {
			$(".body-sidebar a.item-anchor[href*='insights_dashboard=']")
				.parent()
				.removeClass("active-sidebar");
		}
	}

	set_query(config) {
		const params = new URLSearchParams(window.location.search);
		params.set("insights_dashboard", config);
		history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
	}

	config_from_url() {
		return new URLSearchParams(window.location.search).get("insights_dashboard");
	}
};

insights_sidebar.hide_chrome = function (iframe) {
	// same-origin iframe: hide the Insights app's own sidebar so only the dashboard shows
	try {
		const doc = iframe.contentDocument;
		if (!doc) return;
		const style = doc.createElement("style");
		style.textContent = `
			#app > div > .h-full.border-r.bg-gray-50,
			#app .flex-shrink-0.flex-col.border-r { display: none !important; }
		`;
		doc.head.appendChild(style);
	} catch (e) {
		// ignore if the document is unavailable
	}
};

$(() => {
	insights_sidebar.sidebar = new insights_sidebar.Sidebar();
});
