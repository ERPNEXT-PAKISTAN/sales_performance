frappe.query_reports["Target Achievement Status"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "fiscal_year",
			label: __("Fiscal Year"),
			fieldtype: "Link",
			options: "Fiscal Year",
			reqd: 1,
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
		{ fieldname: "sales_person", label: __("Sales Person"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "territory", label: __("Territory"), fieldtype: "Link", options: "Territory" },
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
			get_query() {
				return { query: "sales_performance.api.planning.item_group_query" };
			},
		},
		{ fieldname: "customer_group", label: __("Customer Group"), fieldtype: "Link", options: "Customer Group", default: "Market" },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) {
			return value;
		}
		if (column.fieldname === "status") {
			const color = data.status === "Achieved" ? "#16a34a" : "#dc2626";
			return `<span style="font-weight:600;color:${color}">${value}</span>`;
		}
		return value;
	},
};
