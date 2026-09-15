frappe.query_reports["Sales Target Monthly Performance"] = {
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
			description: __("Amount = surplus amount × %. Qty = surplus qty × % (not converted to selling price). Payable follows this filter."),
		},
		{
			fieldname: "period",
			label: __("Period"),
			fieldtype: "Select",
			options: ["Monthly", "Quarterly", "Half-Yearly", "YTD", "Annual"],
			default: "Monthly",
		},
		{ fieldname: "sales_person", label: __("Sales Person"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "territory", label: __("Territory"), fieldtype: "Link", options: "Territory" },
		{ fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group" },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "month", label: __("Month"), fieldtype: "Int" },
		{ fieldname: "quarter", label: __("Quarter"), fieldtype: "Int" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
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
		if (column.fieldname === "incentive_rate_percent" && flt(data.incentive_rate_percent) > 0) {
			value = `<span style="font-weight:600">${value}</span>`;
		}
		return value;
	},
};
