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

	function already_first(list) {
		return Array.isArray(list) && list[0] && list[0].label === "Sales Performance" && list[0].app === "sales_performance";
	}

	function merge(list) {
		const rows = Array.isArray(list) ? list.filter((row) => row && row.label) : [];
		const without = rows.filter((row) => row.label !== "Sales Performance");
		return [icon, ...without];
	}

	function apply() {
		if (!window.frappe || !frappe.boot) {
			return;
		}
		if (!already_first(frappe.boot.desktop_icons)) {
			frappe.boot.desktop_icons = merge(frappe.boot.desktop_icons);
		}
		if (Array.isArray(frappe.desktop_icons) && !already_first(frappe.desktop_icons)) {
			frappe.desktop_icons = merge(frappe.desktop_icons);
		}
	}

	apply();
	$(document).on("app_ready", apply);
	$(document).on("desktop_screen", apply);
})();
