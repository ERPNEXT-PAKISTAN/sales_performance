frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["Target Achievement Split"] = {
	method: "sales_performance.sales_performance.dashboard_chart_source.target_achievement_split.target_achievement_split.get_data",
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			default:
				frappe.defaults.get_user_default("fiscal_year") ||
				(frappe.boot.current_fiscal_year && frappe.boot.current_fiscal_year[0]),
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: ["Annual", "Monthly", "Quarterly"],
			default: "Annual",
		},
		{
			fieldname: "judge",
			label: __("Judge On"),
			fieldtype: "Select",
			options: ["Qty", "Amount", "Both"],
			default: "Qty",
		},
	],
};
