(() => {
	const icon = {
		label: "Sales Performance",
		icon_type: "App",
		link_type: "External",
		link: "/app/sales-performance",
		logo_url: "/assets/sales_performance/images/sales-performance-logo.png",
		icon: "chart-bar",
		bg_color: "blue",
		hidden: 0,
		standard: 1,
		idx: 1,
		name: "Sales Performance",
		app: "sales_performance",
		parent_icon: null,
	};

	function merge(list) {
		const rows = Array.isArray(list) ? list.filter((row) => row && row.label) : [];
		const without = rows.filter((row) => row.label !== "Sales Performance");
		return [icon, ...without];
	}

	function apply() {
		if (!window.frappe || !frappe.boot) {
			return;
		}
		frappe.boot.desktop_icons = merge(frappe.boot.desktop_icons);
		if (Array.isArray(frappe.desktop_icons)) {
			frappe.desktop_icons = merge(frappe.desktop_icons);
		}
	}

	apply();
	$(document).on("app_ready", apply);
	$(document).on("desktop_screen", (_event, data) => {
		apply();
		const page = data && data.desktop;
		if (!page || page._sp_icon_patched) {
			return;
		}
		const has = (frappe.desktop_icons || []).some((row) => row.label === "Sales Performance");
		if (has && (page.apps_icons || []).some((row) => row.label === "Sales Performance")) {
			return;
		}
		page._sp_icon_patched = true;
		page.update();
	});
})();
