const salesTargetByTerritoryPrintTemplate = `
{% 
var esc = function(value) { return frappe.utils.escape_html(String(value == null ? "" : value)); };
var num = function(value) { return Number(value || 0).toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 2}); };
var filter_labels = {
	company: "Company", fiscal_year: "Fiscal Year", pay_on: "Pay Incentive On", period: "Period",
	month: "Month", quarter: "Quarter", incentive_band: "Incentive Achievement", sales_person: "Sales Person",
	territory: "Territory", item_group: "Item Group", customer_group: "Customer Group", item: "Item",
	from_date: "From Date", to_date: "To Date"
};
var source_rows = original_data || data || [];
var total_row = source_rows.find(function(row) { return row.is_total_row; }) || {};
var item_rows = source_rows.filter(function(row) { return row._node_type === "item_group"; });
var sum_field = function(fieldname) { return item_rows.reduce(function(total, row) { return total + Number(row[fieldname] || 0); }, 0); };
var summary_values = typeof summary !== "undefined" && summary ? summary : {
	target_qty: total_row.target_qty || sum_field("target_qty"),
	actual_qty: total_row.actual_qty || sum_field("actual_qty"),
	qty_achievement_percent: total_row.qty_achievement_percent || (sum_field("target_qty") ? sum_field("actual_qty") / sum_field("target_qty") * 100 : 0),
	target_amount: total_row.target_amount || sum_field("target_amount"),
	actual_amount: total_row.actual_amount || sum_field("actual_amount"),
	amount_achievement_percent: total_row.amount_achievement_percent || (sum_field("target_amount") ? sum_field("actual_amount") / sum_field("target_amount") * 100 : 0),
	incentive_amount: total_row.incentive_amount || sum_field("incentive_amount"),
	incentive_rate_percent: total_row.incentive_rate_percent || 0
};
var visible_groups = typeof group_count === "number" ? group_count : data.filter(function(row) { return row.is_group_row; }).length;
var visible_items = typeof item_count === "number" ? item_count : item_rows.length;
var expanded = typeof expanded_nodes !== "undefined" ? expanded_nodes : source_rows.filter(function(row) {
	return row.is_group_row && data.some(function(visibleRow) { return visibleRow._parent_node === row._node; });
}).map(function(row) { return row._node; });
var updated_text = typeof updated !== "undefined" ? updated : frappe.datetime.now_datetime();
var hierarchy = filters.period === "Annual" ? "Territory → Item Group" : "Period → Territory → Item Group";
var filter_value = function(key, value) { return ["from_date", "to_date"].includes(key) ? frappe.datetime.str_to_user(value) : value; };
var currency = function(value) { return frappe.format(value || 0, {fieldtype: "Currency", precision: 0}, {for_print: true}); };
var incentive_currency = function(value) { return frappe.format(value || 0, {fieldtype: "Currency", precision: 2}, {for_print: true}); };
var quantity = function(value) { return frappe.format(value || 0, {fieldtype: "Float", precision: 0}, {for_print: true}); };
var percent = function(value) { return frappe.format(value || 0, {fieldtype: "Percent", precision: 2}, {for_print: true}); };
var include_col = function(col) { return col.name && col._id !== "_check" && !["pay_on", "incentive_band"].includes(col.fieldname || col.id); };
%}
<style>
.sor-print{--accent:#0f766e;--accent-dark:#115e59;color:#334155;font-family:Arial,sans-serif;font-size:10px;width:100%;}
.sor-print *{box-sizing:border-box;}
.sor-print .hero{display:flex;align-items:center;gap:12px;min-height:48px;padding:8px 14px;margin-bottom:10px;border-radius:8px;background:linear-gradient(105deg,#134e4a 0%,#0f766e 62%,#0e7490 100%)!important;color:#fff!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sor-print .eyebrow{color:#99f6e4;font-size:9px;font-weight:700;letter-spacing:1px;white-space:nowrap;}
.sor-print h2{margin:0;color:#fff!important;font-size:18px;font-weight:700;white-space:nowrap;}
.sor-print .description{color:#d1fae5;font-size:10px;}
.sor-print .filter-panel,.sor-print .report-panel{margin-bottom:10px;border:1px solid #dbe4e8;border-radius:8px;overflow:hidden;}
.sor-print .panel-title{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 11px;border-bottom:1px solid #dbe4e8;}
.sor-print .panel-title strong,.sor-print .toolbar strong{color:#115e59;font-size:11px;}
.sor-print .panel-title span{color:#64748b;font-size:9px;}
.sor-print .filters{padding:7px 11px;color:#334155;line-height:1.8;}
.sor-print .filters span{display:inline-block;margin-right:16px;}
.sor-print .filters strong{color:#475569;font-weight:600;}
.sor-print .filters .filter-sales_person,.sor-print .filters .filter-territory{font-size:11px;font-weight:700;}
.sor-print .filters .filter-sales_person strong,.sor-print .filters .filter-territory strong{color:#115e59;font-size:11px;font-weight:800;}
.sor-print .kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px;}
.sor-print .kpi{min-width:0;padding:7px 10px;border:1px solid #dbe4e8;border-top:3px solid #0f766e;border-radius:7px;background:#f0fdfa!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sor-print .kpi:nth-child(2){border-top-color:#0891b2;background:#ecfeff!important;}
.sor-print .kpi:nth-child(3){border-top-color:#7c3aed;background:#f5f3ff!important;}
.sor-print .kpi:nth-child(4){border-top-color:#c2410c;background:#fff7ed!important;}
.sor-print .kpi-label{color:#64748b;font-size:9px;}
.sor-print .kpi-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:4px;}
.sor-print .kpi-metric-label{display:block;margin-bottom:2px;color:#64748b;font-size:8px;}
.sor-print .kpi-value{display:block;color:#134e4a;font-size:15px;font-weight:700;line-height:1.1;white-space:nowrap;}
.sor-print .toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 11px;}
.sor-print .count{margin-top:2px;color:#64748b;font-size:9px;}
.sor-print .details{width:100%;border-collapse:separate;border-spacing:0;font-size:9px;table-layout:auto;}
.sor-print .details th{position:sticky;top:0;background:#0f766e!important;color:#fff!important;font-size:9px;font-weight:700;white-space:nowrap;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sor-print .details th,.sor-print .details td{padding:5px 7px;border-bottom:1px solid #e2e8f0;vertical-align:middle;overflow-wrap:anywhere;}
.sor-print .details tbody td:nth-child(even){background:#f0fdfa!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sor-print .details td.number{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}
.sor-print .details tr.group td{background:#ccfbf1!important;color:#134e4a;font-weight:700;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sor-print .details tr.child td:first-child{padding-left:24px;color:#475569;}
.sor-print .group-label{display:inline-block;white-space:nowrap;}
.sor-print .details tr.total td{background:#0f766e!important;color:#fff!important;font-weight:700;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sor-print .details tr.total td strong{color:#1e3a8a!important;background:#dbeafe!important;}
.sor-print .footer{display:flex;justify-content:space-between;gap:12px;padding:7px 11px;color:#64748b;font-size:9px;}
.sor-print thead{display:table-header-group;}
.sor-print tr{break-inside:avoid;}
.sor-print .kpis,.sor-print .filter-panel{break-inside:avoid;}
@media print{.print-format{max-width:none!important;padding:0!important;}.sor-print{font-size:9px;}.sor-print .details{font-size:8px;} }
</style>
<div class="sor-print">
  <div class="hero"><span class="eyebrow">{{ __("SALES PERFORMANCE · TARGET ACHIEVEMENT") }}</span><h2>{{ __("Sales Target by Territory") }}</h2><span class="description">{{ __("Target, actual and allocated incentives") }}</span></div>
  <section class="filter-panel">
    <div class="panel-title"><strong>{{ __("Report filters") }}</strong><span>{{ esc(hierarchy) }}</span></div>
    <div class="filters"><span><strong>{{ __("Hierarchy") }}:</strong> {{ esc(__(hierarchy)) }}</span>
    {% Object.keys(filter_labels).forEach(function(key) { if (filters[key]) { %}<span class="filter-{{key}}"><strong>{{ esc(__(filter_labels[key])) }}:</strong> {{ esc(filter_value(key, filters[key])) }}</span>{% } }); %}
    </div>
  </section>
  <section class="kpis">
    <div class="kpi"><div class="kpi-label">{{ __("Target") }}</div><div class="kpi-pair"><div><span class="kpi-metric-label">{{ __("Amount") }}</span><strong class="kpi-value">{{ currency(summary_values.target_amount) }}</strong></div><div><span class="kpi-metric-label">{{ __("Qty") }}</span><strong class="kpi-value">{{ quantity(summary_values.target_qty) }}</strong></div></div></div>
    <div class="kpi"><div class="kpi-label">{{ __("Actual") }}</div><div class="kpi-pair"><div><span class="kpi-metric-label">{{ __("Amount") }}</span><strong class="kpi-value">{{ currency(summary_values.actual_amount) }}</strong></div><div><span class="kpi-metric-label">{{ __("Qty") }}</span><strong class="kpi-value">{{ quantity(summary_values.actual_qty) }}</strong></div></div></div>
    <div class="kpi"><div class="kpi-label">{{ __("Achievement") }}</div><div class="kpi-pair"><div><span class="kpi-metric-label">{{ __("Amount") }}</span><strong class="kpi-value">{{ percent(summary_values.amount_achievement_percent) }}</strong></div><div><span class="kpi-metric-label">{{ __("Qty") }}</span><strong class="kpi-value">{{ percent(summary_values.qty_achievement_percent) }}</strong></div></div></div>
    <div class="kpi"><div class="kpi-label">{{ __("Incentive") }}</div><div class="kpi-pair"><div><span class="kpi-metric-label">{{ __("Amount") }}</span><strong class="kpi-value">{{ incentive_currency(summary_values.incentive_amount) }}</strong></div><div><span class="kpi-metric-label">{{ __("Rate %") }}</span><strong class="kpi-value">{{ percent(summary_values.incentive_rate_percent) }}</strong></div></div></div>
  </section>
  <section class="report-panel">
    <div class="toolbar"><div><strong>{{ __("Territory details") }}</strong><div class="count">{{ __("{0} groups · {1} item rows · Grouped by {2}", [num(visible_groups), num(visible_items), __(hierarchy)]) }}</div></div></div>
    <table class="details"><thead><tr>
      {% columns.forEach(function(col) { if (include_col(col)) { %}<th class="{{ frappe.model.is_numeric_field(col.fieldtype) ? "number" : "" }}">{{ esc(__(col.name)) }}</th>{% } }); %}
    </tr></thead><tbody>
      {% data.forEach(function(row) { var is_group = !!row.is_group_row; var row_class = row.is_total_row ? "total" : is_group ? "group" : "child"; var indent = row.is_total_row ? 0 : is_group ? Number(row.indent || 0) * 18 : 24 + Math.max(0, Number(row.indent || 0) - 1) * 18; %}<tr class="{{ row_class }}">
        {% columns.forEach(function(col) { if (include_col(col)) { var key = col.fieldname || col.id; var value = col.fieldname ? row[col.fieldname] : row[col.id]; var is_number = frappe.model.is_numeric_field(col.fieldtype); %}
          <td class="{{ is_number ? "number" : "" }}"{% if col._index === 0 %} style="padding-left:{{indent + 7}}px"{% endif %}>
            {% if (row.is_total_row && col._index === 0) { %}{{ __("Total") }}
            {% } else if (is_group && key === "group_value") { %}<span class="group-label">{{ expanded.includes(row._node) ? "▾" : "▸" }} {{ esc(value) }}</span>
            {% } else if (key === "group_value") { %}{{ esc(value) }}
            {% } else if (col.fieldtype === "Check") { %}{{ value == 1 ? "✓" : "✗" }}
            {% } else { %}{{ col.format ? col.format(value, row, col, row, true) : col.docfield ? frappe.format(value, col.docfield) : esc(value) }}{% } %}
          </td>
        {% } }); %}
      </tr>{% }); %}
    </tbody></table>
    <div class="footer"><span>{{ __("Territory and Item Group totals follow the selected report filters.") }}</span><span>{{ esc(updated_text) }}</span></div>
  </section>
</div>`;

frappe.query_reports["Sales Target by Territory"] = {
	html_format: salesTargetByTerritoryPrintTemplate,
	tree: true,
	name_field: "_node",
	parent_field: "_parent_node",
	initial_depth: 1,
	after_datatable_render(datatable) {
		const headerRow = $(datatable.wrapper).find(".dt-header .dt-row-header");
		headerRow.css({ height: "52px", minHeight: "52px" });
		headerRow.find(".dt-cell--header").css({ height: "52px", minHeight: "52px" });
		headerRow.find(".dt-cell__content").css({
			whiteSpace: "normal",
			lineHeight: "1.15",
			height: "100%",
			maxHeight: "52px",
			overflow: "hidden",
			textOverflow: "clip",
			display: "flex",
			alignItems: "center",
			justifyContent: "center",
			textAlign: "center",
		});
		const headerPalette = {
			group_value: { background: "#4338ca", color: "#ffffff" },
			target_qty: { background: "#dbeafe", color: "#1e3a8a" },
			actual_qty: { background: "#bfdbfe", color: "#1e40af" },
			variance_qty: { background: "#c7d2fe", color: "#3730a3" },
			qty_achievement_percent: { background: "#ccfbf1", color: "#0f766e" },
			target_amount: { background: "#ede9fe", color: "#5b21b6" },
			actual_amount: { background: "#ddd6fe", color: "#6d28d9" },
			variance_amount: { background: "#f3e8ff", color: "#7e22ce" },
			amount_achievement_percent: { background: "#dcfce7", color: "#166534" },
			incentive_rate_percent: { background: "#fef3c7", color: "#92400e" },
			incentive_amount: { background: "#bbf7d0", color: "#166534" },
			pay_on: { background: "#e0f2fe", color: "#075985" },
			incentive_band: { background: "#ffedd5", color: "#9a3412" },
		};
		(frappe.query_report.columns || [])
			.filter((column) => !column.hidden)
			.forEach((column, index) => {
				const palette = headerPalette[column.fieldname || column.id];
				if (!palette) return;
				const cell = headerRow.children(".dt-cell").eq(index);
				cell.css({ backgroundColor: palette.background, color: palette.color });
				cell.find(".dt-cell__content").css({
					backgroundColor: palette.background,
					color: palette.color,
					fontWeight: 700,
				});
			});
		const rowBackgrounds = {
			period: "#eaf2ff",
			territory: "#f3ecff",
		};
		(frappe.query_report.data || []).forEach((row, index) => {
			const background = rowBackgrounds[row._node_type];
			if (background) {
				datatable.style.setStyle(`.dt-row-${index} .dt-cell`, { "background-color": background });
			}
		});
		if (frappe.query_report?.salesTargetTreeDepth !== undefined) {
			frappe.query_report.salesTargetTreeDepth = Number(frappe.query_report.report_settings.initial_depth) || 0;
		}
	},
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
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
			get_query() { return { query: "sales_performance.api.planning.item_group_query" }; },
		},
		{ fieldname: "customer_group", label: __("Customer Group"), fieldtype: "Link", options: "Customer Group", default: "" },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
	onload(report) {
		const filterForm = report.page.page_form;
		filterForm.find(".sales-target-primary-filters, .sales-target-secondary-filters").remove();
		const primaryRow = $('<div class="sales-target-primary-filters"></div>').css({
			display: "flex",
			width: "100%",
			flexWrap: "nowrap",
			alignItems: "flex-end",
			minHeight: "60px",
			flexShrink: 0,
			gap: "4px",
		});
		const secondaryRow = $('<div class="sales-target-secondary-filters"></div>').css({
			display: "flex",
			width: "100%",
			flexWrap: "nowrap",
			alignItems: "flex-end",
			position: "relative",
			zIndex: 1,
			minHeight: "60px",
			flexShrink: 0,
			gap: "8px",
		});
		filterForm.css({
			display: "flex",
			position: "relative",
			zIndex: 20,
			"flex-direction": "column",
			"align-items": "stretch",
			"flex-shrink": 0,
			height: "auto",
			"min-height": 0,
			"padding-bottom": "12px",
			"margin-bottom": "8px",
			gap: "4px",
			"overflow-x": "visible",
		});
		filterForm.append(primaryRow, secondaryRow);

		const secondaryFields = new Set([
			"sales_person",
			"item_group",
			"item",
			"customer_group",
			"territory",
		]);
		report.filters.forEach((filter) => {
			const wrapper = $(filter.wrapper);
			const secondary = secondaryFields.has(filter.fieldname);
			(secondary ? secondaryRow : primaryRow).append(wrapper);
			wrapper.css({
				flex: "1 1 0",
				width: "auto",
				minWidth: secondary ? 0 : "70px",
				padding: "0 2px",
				margin: "4px 0",
			});
			wrapper.find(".control-label").css({
				fontSize: "13px",
				fontWeight: 600,
				whiteSpace: "nowrap",
				overflow: "hidden",
				textOverflow: "ellipsis",
			}).attr("title", filter.label || "");
			wrapper.find(".form-control").css({
				minWidth: 0,
				width: "100%",
				height: "30px",
				fontSize: "13px",
				padding: "4px 6px",
			});
			if (filter.fieldname === "sales_person") {
				wrapper.css({ position: "relative", zIndex: 2 });
				wrapper.find(".awesomplete").css("z-index", 30);
				wrapper.find(".awesomplete > ul").css("z-index", 31);
			}
		});
		report.salesTargetTreeDepth = Number(report.report_settings.initial_depth) || 0;
		const treeControls = $('<div class="sales-target-tree-controls"></div>').css({
			display: "flex",
			justifyContent: "flex-start",
			alignItems: "center",
			gap: "6px",
			padding: "4px 16px",
		});
		const collapseOneLevel = $(`<button type="button" class="btn btn-default btn-xs" title="${__("Collapse")}" aria-label="${__("Collapse")}">${frappe.utils.icon("chevron-up", "sm")}</button>`);
		const expandOneLevel = $(`<button type="button" class="btn btn-default btn-xs" title="${__("Expand")}" aria-label="${__("Expand")}">${frappe.utils.icon("chevron-down", "sm")}</button>`);
		collapseOneLevel
			.css({ display: "inline-flex", alignItems: "center", gap: "5px", color: "#6d28d9", background: "#ede9fe", borderColor: "#c4b5fd", fontWeight: 600, padding: "5px 9px" })
			.append($("<span>").text(__("Collapse")));
		expandOneLevel
			.css({ display: "inline-flex", alignItems: "center", gap: "5px", color: "#0f766e", background: "#ccfbf1", borderColor: "#5eead4", fontWeight: 600, padding: "5px 9px" })
			.append($("<span>").text(__("Expand")));
		const changeTreeDepth = (direction) => {
			const rowManager = report.datatable?.rowmanager;
			if (!rowManager) return;
			const rows = rowManager.datamanager.getRows();
			const maxDepth = rows.reduce((max, row) => Math.max(max, row.meta.indent || 0), 0);
			report.salesTargetTreeDepth = Math.max(
				0,
				Math.min(maxDepth, report.salesTargetTreeDepth + direction)
			);
			rowManager.setTreeDepth(report.salesTargetTreeDepth);
		};
		collapseOneLevel.on("click", () => changeTreeDepth(-1));
		expandOneLevel.on("click", () => changeTreeDepth(1));
		const printReport = () => {
			if (!frappe.model.can_print(report.report_doc.ref_doctype)) {
				frappe.msgprint(__("You do not have permission to print this report."));
				return;
			}
			report.get_validated_visible_indexes();
			const originalData = report.data || [];
			const visibleRows = report.get_data_for_print();
			const groupCount = originalData.filter((row) => row.is_group_row && !row._parent_node).length;
			const itemRows = originalData.filter((row) => row._node_type === "item_group");
			const totalRow = originalData.find((row) => row.is_total_row) || {};
			const sum = (fieldname) => itemRows.reduce((total, row) => total + flt(row[fieldname]), 0);
			const summary = {
				target_qty: totalRow.target_qty ?? sum("target_qty"),
				actual_qty: totalRow.actual_qty ?? sum("actual_qty"),
				qty_achievement_percent: totalRow.qty_achievement_percent
					?? (sum("target_qty") ? sum("actual_qty") / sum("target_qty") * 100 : 0),
				target_amount: totalRow.target_amount ?? sum("target_amount"),
				actual_amount: totalRow.actual_amount ?? sum("actual_amount"),
				amount_achievement_percent: totalRow.amount_achievement_percent
					?? (sum("target_amount") ? sum("actual_amount") / sum("target_amount") * 100 : 0),
				incentive_amount: totalRow.incentive_amount ?? sum("incentive_amount"),
				incentive_rate_percent: totalRow.incentive_rate_percent ?? 0,
			};
			const expandedNodes = originalData
				.filter((row) => row.is_group_row)
				.filter((row) => visibleRows.some((visibleRow) => visibleRow._parent_node === row._node))
				.map((row) => row._node);
			frappe.render_grid({
				template: salesTargetByTerritoryPrintTemplate,
				title: __("Sales Target by Territory"),
				subtitle: null,
				filters: report.get_filter_values(),
				data: visibleRows,
				original_data: originalData,
				columns: report.columns,
				landscape: true,
				print_settings: { orientation: "Landscape" },
				summary,
				group_count: groupCount,
				item_count: itemRows.length,
				expanded_nodes: expandedNodes,
				updated: frappe.datetime.now_datetime(),
				search: "",
			});
		};
		report.page.remove_inner_button(__("Print"));
		report.page.add_inner_button(__("Print"), printReport, null, "primary");
		treeControls.append(collapseOneLevel, expandOneLevel);
		report.page.main.find(".sales-target-tree-controls").remove();
		const reportWrapper = report.$report || report.page.main.find(".report-wrapper");
		if (reportWrapper.length) reportWrapper.before(treeControls);
	},
	formatter(value, row, column, data, default_formatter) {
		const formatted = (window.sales_performance && sales_performance.report_formatter)
			? sales_performance.report_formatter(value, row, column, data, default_formatter)
			: default_formatter(value, row, column, data);
		if (!data) return formatted;

		if (data && data.is_total_row) {
			return `<strong style="color:#1e3a8a;background:#dbeafe;padding:3px 7px;border-radius:5px;display:inline-block">${formatted}</strong>`;
		}

		if (column.fieldname === "group_value") {
			const styles = {
				period: { label: __("PERIOD"), bg: "#dbeafe", fg: "#1e40af" },
				territory: { label: __("TERRITORY"), bg: "#ede9fe", fg: "#6d28d9" },
				item_group: { label: __("ITEM GROUP"), bg: "#ccfbf1", fg: "#0f766e" },
			};
			const style = styles[data._node_type] || { label: "", bg: "#f1f5f9", fg: "#334155" };
			const label = frappe.utils.escape_html(data._link_value || data.group_value || "");
			let content = label;
			const doctype = data._node_type === "territory" ? "Territory"
				: data._node_type === "item_group" ? "Item Group" : null;
			if (doctype && data._link_value && frappe.utils.get_form_link) {
				const href = frappe.utils.escape_html(frappe.utils.get_form_link(doctype, data._link_value));
				content = `<a href="${href}" style="color:${style.fg};font-weight:700;text-decoration:none">${label}</a>`;
			}
			const typeBadge = style.label
				? `<span style="font-size:9px;letter-spacing:.04em;font-weight:800;color:${style.fg};margin-right:7px">${style.label}</span>`
				: "";
			return `<span style="display:inline-flex;align-items:center;background:${style.bg};color:${style.fg};padding:3px 8px;border-radius:6px;font-weight:${data.is_group_row ? 700 : 600}">${typeBadge}${content}</span>`;
		}

		if (["qty_achievement_percent", "amount_achievement_percent"].includes(column.fieldname)) {
			const achievementFormatted = default_formatter(value, row, column, data);
			if (data[column.fieldname] == null || data[column.fieldname] === "") return achievementFormatted;
			const achievement = flt(data[column.fieldname]);
			const palette = achievement >= 100
				? { bg: "#dcfce7", fg: "#166534" }
				: achievement >= 80
					? { bg: "#fef3c7", fg: "#92400e" }
					: { bg: "#fee2e2", fg: "#b91c1c" };
			return `<span style="display:inline-block;background:${palette.bg};color:${palette.fg};padding:2px 7px;border-radius:999px;font-weight:700">${achievementFormatted}</span>`;
		}

		if (["variance_qty", "variance_amount"].includes(column.fieldname)) {
			const variance = flt(data[column.fieldname]);
			const color = variance >= 0 ? "#15803d" : "#dc2626";
			return `<span style="font-weight:700;color:${color}">${formatted}</span>`;
		}

		if (column.fieldname === "actual_qty") {
			return `<span style="color:#6d28d9;font-weight:650">${formatted}</span>`;
		}
		if (column.fieldname === "actual_amount") {
			return `<span style="color:#0369a1;font-weight:650">${formatted}</span>`;
		}
		if (column.fieldname === "incentive_amount" && flt(data.incentive_amount) > 0) {
			return `<span style="font-weight:700;color:#16833b;background:#dcfce7;padding:2px 7px;border-radius:5px">${formatted}</span>`;
		}
		if (column.fieldname === "incentive_band" && data.incentive_band) {
			const mixed = data.incentive_band === "Mixed";
			const palette = mixed ? { bg: "#fef3c7", fg: "#92400e" } : { bg: "#ede9fe", fg: "#6d28d9" };
			return `<span style="font-weight:650;color:${palette.fg};background:${palette.bg};padding:2px 7px;border-radius:5px">${formatted}</span>`;
		}
		if (column.fieldname === "incentive_rate_percent" && flt(data.incentive_rate_percent) > 0) {
			return `<span style="font-weight:700;color:#7c3aed">${formatted}</span>`;
		}

		return formatted;
	},
};
