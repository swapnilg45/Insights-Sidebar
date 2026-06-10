# Insights Sidebar

Inject role-based **Insights dashboard** links into an existing workspace's sidebar and open
the chosen dashboard **in place** inside the Desk — no full page reload, no new browser tab, and
the workspace sidebar stays mounted with the active item highlighted.

The dashboard is embedded as a same-origin `<iframe>` whose own chrome is hidden, so it looks
native to the Desk.

## How it works

A single configuration DocType, **Insights Sidebar Config**, defines each link. A whitelisted API
returns the role-filtered links (cached), and a small client script adds them to the workspace
sidebar and renders the dashboard when one is clicked.

```
Insights Sidebar Config ──► api.get_sidebar_links()  (cached, role-filtered)
                                      │
        public/js/insights_sidebar.js │  injects items into frappe.ui.Sidebar
                                      ▼
        click ──► api.get_dashboard_embed_url()  (re-validates roles server-side)
                                      │
                                      ▼
        <iframe src="/insights/dashboards/<name>">  rendered into the workspace body
```

### Frappe v16 note

In v16 the workspace sidebar is rendered by the global `frappe.ui.Sidebar` class from data in
`frappe.boot.workspace_sidebar_item[<workspace>].items` — it is no longer built by the Workspace
view. So this app does **not** poke the rendered DOM. Instead it injects a collapsible
*"Insights Dashboards"* section (with our links as nested items) into that data list before the
sidebar renders, and lets Frappe draw them natively. The in-place viewer swaps the workspace's
content area (`.layout-main-section`) to the iframe and keeps the route on the workspace, so the
sidebar stays visible.

## Configuration DocType — `Insights Sidebar Config`

| Field | Type | Notes |
|---|---|---|
| **Label** | Data (required, unique) | Text shown in the sidebar |
| **Workspace** | Link → Workspace (required) | Workspace to attach the link under (e.g. *Buying*) |
| **Insights Dashboard** | Link → Insights Dashboard v3 (required) | Dashboard to embed |
| **Position** | Int | Sort order among injected items (lower = higher up) |
| **Disabled** | Check | Hide without deleting |
| **Roles** | Table → Has Role | Who can see it. **Leave empty to show it to all logged-in users** |

Nothing is hardcoded — dashboards and roles are chosen by reference, never by id or name in code.

## Adding a new link

1. Go to **Insights Sidebar Config → New**.
2. Set **Label**, pick the **Workspace** and the **Insights Dashboard**, set a **Position**.
3. Add the **Roles** that should see it (or leave empty for everyone).
4. Save. The link appears under that workspace's sidebar on the next page load.

The link cache is cleared automatically when a config is created, updated, or deleted
(`on_update` / `on_trash`), so changes show up without a manual cache clear.

## Role-based visibility

- A link is shown only if the user has **at least one** of its configured roles.
- An **empty** Roles table means the link is visible to **all logged-in users**.
- Visibility is filtered **server-side** in `get_sidebar_links()`; the client only ever receives
  the links the current user is allowed to see.

## Security model (layered)

Access is enforced at three independent layers — granting a sidebar config role alone is not
enough to view a dashboard:

1. **Sidebar config roles** — control whether the link is *listed*, and `get_dashboard_embed_url()`
   re-validates the user's roles **and** calls `frappe.has_permission("Insights Dashboard v3",
   "read", ...)` on the server before returning the embed URL (raises `PermissionError`
   otherwise). The client check is never trusted, and an unreadable dashboard URL never reaches
   the browser.
2. **Insights User role** — Insights gates its own APIs behind the **Insights User** role; without
   it the embedded dashboard returns 403.
3. **Per-dashboard read (DocShare)** — Insights v3 enforces document-level read on
   `Insights Dashboard v3`. A user must own the dashboard, be an Insights Admin, or have it shared
   with read access (`frappe.share.add(...)`). Otherwise the iframe shows a permission error even
   though the link is visible.

To grant a user a working dashboard link you typically need: the config role (or none), the
**Insights User** role, **read** access to the workspace's module (e.g. *Purchase User* for
*Buying*), and a **DocShare** (or ownership) of the dashboard.

## Performance

Sidebar links are cached in `frappe.cache()` under `insights_sidebar_links` and rebuilt only when
a config changes — there is no per-page-refresh table scan.

## Verifying

1. Create dashboards in Insights, create a couple of `Insights Sidebar Config` records under a
   workspace with different roles, and assign roles/DocShares to test users.
2. Log in as each user and open the workspace — confirm only the permitted links appear under the
   *Insights Dashboards* section.
3. Click a link — the dashboard loads in place (no reload, no new tab), the sidebar stays visible,
   the item is highlighted, and the Insights chrome is hidden.
4. Delete (or disable) a config — its link disappears live from every open Desk, via a
   `publish_realtime` broadcast (no refresh needed).
5. Confirm an unauthorized user cannot reach a dashboard even by calling
   `get_dashboard_embed_url` directly (it raises `PermissionError`).

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
# fetch the dependencies into the bench if they aren't already present
bench get-app erpnext --branch version-16
bench get-app https://github.com/frappe/insights --branch version-3
bench get-app $URL_OF_THIS_REPO --branch main
bench --site <site> install-app insights_sidebar
```

**erpnext** and **insights** are declared in `required_apps`, so `install-app` installs them
first automatically (they must already be present in the bench). insights provides the
`Insights Dashboard v3` DocType the links point to; erpnext provides the workspaces (such as
*Buying*) the links attach under.

## Demo data (for evaluation)

To try the app without building everything by hand, load the bundled demo: two Insights
dashboards (under one workbook), the `Sales Dashboard Viewer` / `Purchase Dashboard Viewer` roles,
three sidebar configs under **Buying**, three test users, and the doc-shares they need.

```bash
bench --site <site> execute insights_sidebar.demo.install.install
```

This creates three users (password `Test@1234`), each showing a different slice under the
*Insights Dashboards* section of the **Buying** workspace:

| User | Sees |
|---|---|
| `sales.tester@example.com` | Sales Dashboard, All Hands KPIs |
| `purchase.tester@example.com` | Purchase Dashboard, All Hands KPIs |
| `basic.tester@example.com` | All Hands KPIs only |

Log in as each, open **Buying**, and click a link — the dashboard renders in place. Remove the
demo data with:

```bash
bench --site <site> execute insights_sidebar.demo.install.uninstall
```

The data lives in `insights_sidebar/demo/json/` (the dashboards as an Insights workbook export);
`install.py` imports the workbook and creates the roles, configs, users and shares from it.

## License

MIT
