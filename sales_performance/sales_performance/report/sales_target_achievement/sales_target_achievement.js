frappe.query_reports["Sales Target Achievement"] = {
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
			default: frappe.defaults.get_user_default("fiscal_year")
				|| (frappe.boot.current_fiscal_year && frappe.boot.current_fiscal_year[0]),
		},
		{
			fieldname: "pay_on",
			label: __("Pay Incentive On"),
			fieldtype: "Select",
			options: "Amount\nQty",
			default: "Amount",
			reqd: 1,
			description: __("The earned salesperson payout is shared across items in proportion to their positive Qty or Amount surplus."),
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: ["Annual", "Monthly", "Quarterly"],
			default: "Monthly",
		},
		{ fieldname: "month", label: __("Month"), fieldtype: "Int", depends_on: "eval:doc.period === 'Monthly'" },
		{ fieldname: "quarter", label: __("Quarter"), fieldtype: "Int", depends_on: "eval:doc.period === 'Quarterly'" },
		{
			fieldname: "incentive_band",
			label: __("Incentive Achievement"),
			fieldtype: "Select",
			options: "All\nMin\nMax\nNot Achieve",
			default: "All",
			description: __("Min/Max show the earned incentive band. Not Achieve shows rows with no allocated incentive."),
		},
		{ fieldname: "sales_person", label: __("Sales Person"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "territory", label: __("Territory"), fieldtype: "Link", options: "Territory" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group",
			get_query() { return { query: "sales_performance.api.planning.item_group_query" }; } },
		{ fieldname: "customer_group", label: __("Customer Group"), fieldtype: "Link", options: "Customer Group" },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
	formatter(value, row, column, data, default_formatter) {
		if (data && data.is_total_row) {
			return `<strong>${default_formatter(value, row, column, data)}</strong>`;
		}
		value = (window.sales_performance && sales_performance.report_formatter)
			? sales_performance.report_formatter(value, row, column, data, default_formatter)
			: default_formatter(value, row, column, data);
		if (!data) {
			return value;
		}
		if (column.fieldname === "incentive_on_amount" && flt(data.incentive_on_amount) > 0) {
			value = `<span style="color:#1a5276">${value}</span>`;
		}
		if (column.fieldname === "incentive_on_qty" && flt(data.incentive_on_qty) > 0) {
			value = `<span style="color:#6c3483">${value}</span>`;
		}
		if (column.fieldname === "incentive_amount" && flt(data.incentive_amount) > 0) {
			value = `<span style="font-weight:600;color:#16833b">${value}</span>`;
		}
		return value;
	},
};
