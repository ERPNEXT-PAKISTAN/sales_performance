const salesTargetAchievementPrintTemplate = `
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
var detail_rows = source_rows.filter(function(row) { return !row.is_group_row && !row.is_total_row; });
var sum_field = function(fieldname) { return detail_rows.reduce(function(total, row) { return total + Number(row[fieldname] || 0); }, 0); };
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
var visible_groups = typeof group_count === "number" ? group_count : data.filter(function(row) { return row.is_group_row && !row._parent_node; }).length;
var visible_items = typeof item_count === "number" ? item_count : detail_rows.length;
var expanded = typeof expanded_nodes !== "undefined" ? expanded_nodes : source_rows.filter(function(row) {
	return row.is_group_row && data.some(function(visibleRow) { return visibleRow._parent_node === row._node; });
}).map(function(row) { return row._node; });
var updated_text = typeof updated !== "undefined" ? updated : frappe.datetime.now_datetime();
var hierarchy = filters.group_by || "Month → Sales Person → Territory → Item Group";
var parent_level = filters.period === "Annual" ? 0 : 1;
var filter_value = function(key, value) { return ["from_date", "to_date"].includes(key) ? frappe.datetime.str_to_user(value) : value; };
var currency = function(value) { return frappe.format(value || 0, {fieldtype: "Currency", precision: 0}, {for_print: true}); };
var incentive_currency = function(value) { return frappe.format(value || 0, {fieldtype: "Currency", precision: 2}, {for_print: true}); };
var quantity = function(value) { return frappe.format(value || 0, {fieldtype: "Float", precision: 0}, {for_print: true}); };
var percent = function(value) { return frappe.format(value || 0, {fieldtype: "Percent", precision: 2}, {for_print: true}); };
var include_col = function(col) { return col.name && !col.hidden && col._id !== "_check" && !["pay_on", "incentive_band", "customer_group", "planning"].includes(col.fieldname || col.id); };
var print_column_style = function(col) { return ["group_value", "item_code"].includes(col.fieldname || col.id) && col.width ? "width:" + Number(col.width) + "px;" : ""; };
%}
<style>
.sta-print{--accent:#4f46e5;--accent-dark:#312e81;color:#334155;font-family:Arial,sans-serif;font-size:10px;width:100%;}
.sta-print *{box-sizing:border-box;}
.sta-print .hero{display:flex;align-items:center;gap:12px;min-height:48px;padding:8px 14px;margin-bottom:10px;border-radius:8px;background:linear-gradient(105deg,#312e81 0%,#4f46e5 62%,#7c3aed 100%)!important;color:#fff!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sta-print .eyebrow{color:#ddd6fe;font-size:9px;font-weight:700;letter-spacing:1px;white-space:nowrap;}
.sta-print h2{margin:0;color:#fff!important;font-size:18px;font-weight:700;white-space:nowrap;}
.sta-print .description{color:#ede9fe;font-size:10px;}
.sta-print .filter-panel,.sta-print .report-panel{margin-bottom:10px;border:1px solid #dbe4e8;border-radius:8px;overflow:hidden;}
.sta-print .panel-title{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:7px 11px;border-bottom:1px solid #dbe4e8;}
.sta-print .panel-title strong,.sta-print .toolbar strong{color:#312e81;font-size:11px;}
.sta-print .panel-title span{color:#64748b;font-size:9px;}
.sta-print .filters{padding:7px 11px;color:#334155;line-height:1.8;}
.sta-print .filters span{display:inline-block;margin-right:16px;}
.sta-print .filters strong{color:#475569;font-weight:600;}
.sta-print .filters .filter-sales_person,.sta-print .filters .filter-territory{font-size:11px;font-weight:700;}
.sta-print .filters .filter-sales_person strong,.sta-print .filters .filter-territory strong{color:#4338ca;font-size:11px;font-weight:800;}
.sta-print .kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin-bottom:10px;}
.sta-print .kpi{min-width:0;padding:7px 10px;border:1px solid #dbe4e8;border-top:3px solid #4f46e5;border-radius:7px;background:#eef2ff!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sta-print .kpi:nth-child(2){border-top-color:#0891b2;background:#ecfeff!important;}
.sta-print .kpi:nth-child(3){border-top-color:#c026d3;background:#fdf4ff!important;}
.sta-print .kpi:nth-child(4){border-top-color:#ea580c;background:#fff7ed!important;}
.sta-print .kpi-label{color:#64748b;font-size:9px;}
.sta-print .kpi-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:4px;}
.sta-print .kpi-metric-label{display:block;margin-bottom:2px;color:#64748b;font-size:8px;}
.sta-print .kpi-value{display:block;color:#312e81;font-size:15px;font-weight:700;line-height:1.1;white-space:nowrap;}
.sta-print .toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:8px 11px;}
.sta-print .count{margin-top:2px;color:#64748b;font-size:9px;}
.sta-print .details{width:100%;border-collapse:separate;border-spacing:0;font-size:8px;table-layout:auto;}
.sta-print .details th{position:sticky;top:0;background:#4338ca!important;color:#fff!important;font-size:8px;font-weight:700;white-space:normal;line-height:1.15;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sta-print .details th,.sta-print .details td{padding:4px 5px;border-bottom:1px solid #e2e8f0;vertical-align:middle;overflow-wrap:anywhere;}
.sta-print .details tbody td:nth-child(even){background:#eef2ff!important;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sta-print .details td.number{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums;}
.sta-print .details tr.period td{background:#dbeafe!important;color:#1e3a8a;font-weight:700;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sta-print .details tr.parent td{background:#ffedd5!important;color:#9a3412;font-weight:700;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sta-print .details tr.subgroup td{background:#fae8ff!important;color:#86198f;font-weight:700;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sta-print .details tr.child td:first-child{color:#475569;}
.sta-print .group-label{display:inline-block;white-space:nowrap;}
.sta-print .details tr.total td{background:#312e81!important;color:#fff!important;font-weight:700;print-color-adjust:exact;-webkit-print-color-adjust:exact;}
.sta-print .details tr.total td strong{color:#312e81!important;background:#e0e7ff!important;}
.sta-print .footer{display:flex;justify-content:space-between;gap:12px;padding:7px 11px;color:#64748b;font-size:9px;}
.sta-print thead{display:table-header-group;}
.sta-print tr{break-inside:avoid;}
.sta-print .kpis,.sta-print .filter-panel{break-inside:avoid;}
@media print{.print-format{max-width:none!important;padding:0!important;}.sta-print{font-size:8px;}.sta-print .details{font-size:7px;} }
</style>
<div class="sta-print">
  <div class="hero"><span class="eyebrow">{{ __("SALES PERFORMANCE · TARGET ACHIEVEMENT") }}</span><h2>{{ __("Sales Target Achievement") }}</h2><span class="description">{{ __("Salesperson, territory and item performance") }}</span></div>
  <section class="filter-panel">
    <div class="panel-title"><strong>{{ __("Report filters") }}</strong><span>{{ esc(__(hierarchy)) }}</span></div>
    <div class="filters"><span><strong>{{ __("Group By") }}:</strong> {{ esc(__(hierarchy)) }}</span>
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
    <div class="toolbar"><div><strong>{{ __("Achievement details") }}</strong><div class="count">{{ __("{0} groups · {1} item rows · Grouped by {2}", [num(visible_groups), num(visible_items), __(hierarchy)]) }}</div></div></div>
    <table class="details"><thead><tr>
      {% columns.forEach(function(col) { if (include_col(col)) { %}<th class="{{ frappe.model.is_numeric_field(col.fieldtype) ? "number" : "" }}" style="{{ print_column_style(col) }}">{{ esc(__(col.name)) }}</th>{% } }); %}
    </tr></thead><tbody>
      {% data.forEach(function(row) { var is_group = !!row.is_group_row; var row_class = row.is_total_row ? "total" : row._node_type === "period" ? "period" : is_group ? (Number(row._level || 0) === parent_level ? "parent" : "subgroup") : "child"; var indent = row.is_total_row ? 0 : Number(row.indent || 0) * 18; %}<tr class="{{ row_class }}">
        {% columns.forEach(function(col) { if (include_col(col)) { var key = col.fieldname || col.id; var value = col.fieldname ? row[col.fieldname] : row[col.id]; var is_number = frappe.model.is_numeric_field(col.fieldtype); %}
          <td class="{{ is_number ? "number" : "" }}" style="{{ print_column_style(col) }}{% if col._index === 0 %}padding-left:{{indent + 7}}px;{% endif %}">
            {% if (row.is_total_row && col._index === 0) { %}{{ __("Total") }}
            {% } else if (is_group && key === "group_value") { %}<span class="group-label">{{ expanded.includes(row._node) ? "▾" : "▸" }} {{ esc(value) }}</span>
            {% } else if (key === "group_value") { %}{{ esc(value) }}
            {% } else if (col.fieldtype === "Check") { %}{{ value == 1 ? "✓" : "✗" }}
            {% } else { %}{{ col.format ? col.format(value, row, col, row, true) : col.docfield ? frappe.format(value, col.docfield) : esc(value) }}{% } %}
          </td>
        {% } }); %}
      </tr>{% }); %}
    </tbody></table>
    <div class="footer"><span>{{ __("Group rows roll up the visible item-level results.") }}</span><span>{{ esc(updated_text) }}</span></div>
  </section>
</div>`;

const monthlyAchievementHierarchy = "Month → Sales Person → Territory → Item Group";

frappe.query_reports["Sales Target Achievement"] = {
	tree: true,
	name_field: "_node",
	parent_field: "_parent_node",
	initial_depth: 4,
	html_format: salesTargetAchievementPrintTemplate,
	after_datatable_render(datatable) {
		const headerRow = $(datatable.wrapper).find(".dt-header .dt-row-header");
		headerRow.css({ height: "52px", minHeight: "52px" });
		headerRow.find(".dt-cell--header").css({ height: "52px", minHeight: "52px" });
		headerRow.find(".dt-cell__content").css({
			whiteSpace: "normal", lineHeight: "1.15", height: "100%", maxHeight: "52px",
			overflow: "hidden", textOverflow: "clip", display: "flex", alignItems: "center",
			justifyContent: "center", textAlign: "center",
		});
		const headerPalette = {
			group_value: { background: "#6d28d9", color: "#ffffff" },
			period: { background: "#dbeafe", color: "#1e3a8a" },
			sales_person: { background: "#fee2e2", color: "#991b1b" },
			territory: { background: "#ffedd5", color: "#9a3412" },
			item_group: { background: "#fae8ff", color: "#86198f" },
			customer_group: { background: "#dbeafe", color: "#1e40af" },
			item_code: { background: "#cffafe", color: "#155e75" },
			growth_percent: { background: "#fef3c7", color: "#92400e" },
			target_qty: { background: "#e0e7ff", color: "#3730a3" },
			actual_qty: { background: "#c7d2fe", color: "#3730a3" },
			variance_qty: { background: "#ddd6fe", color: "#5b21b6" },
			qty_achievement_percent: { background: "#ede9fe", color: "#6b21a8" },
			target_amount: { background: "#dcfce7", color: "#166534" },
			actual_amount: { background: "#bbf7d0", color: "#166534" },
			variance_amount: { background: "#a7f3d0", color: "#065f46" },
			amount_achievement_percent: { background: "#d1fae5", color: "#065f46" },
			pay_on: { background: "#e0e7ff", color: "#3730a3" },
			incentive_rate_percent: { background: "#fed7aa", color: "#9a3412" },
			incentive_amount: { background: "#fde68a", color: "#854d0e" },
			planning: { background: "#fae8ff", color: "#86198f" },
		};
		(frappe.query_report.columns || []).filter((column) => !column.hidden).forEach((column, index) => {
			const palette = headerPalette[column.fieldname || column.id];
			if (!palette) return;
			const cell = headerRow.children(".dt-cell").eq(index);
			cell.css({ backgroundColor: palette.background, color: palette.color });
			cell.find(".dt-cell__content").css({ backgroundColor: palette.background, color: palette.color, fontWeight: 700 });
		});
		const rowBackgrounds = {
			period: "#dbeafe", territory: "#ffedd5", sales_person: "#fee2e2",
			customer_group: "#dbeafe", item_group: "#fae8ff",
		};
		(frappe.query_report.data || []).forEach((row, index) => {
			const background = row.is_total_row ? "#e0e7ff" : rowBackgrounds[row._node_type];
			if (background) datatable.style.setStyle(`.dt-row-${index} .dt-cell`, { "background-color": background });
		});
		if (frappe.query_report?.salesAchievementTreeDepth !== undefined) {
			frappe.query_report.salesAchievementTreeDepth = Number(frappe.query_report.report_settings.initial_depth) || 0;
		}
	},
	filters: [
		{
			fieldname: "group_by", label: __("Group By"), fieldtype: "Select",
			options: ["Territory → Item Group", "Sales Person → Item Group", "Customer Group → Item Group", "Item Group → Item", monthlyAchievementHierarchy],
			default: monthlyAchievementHierarchy,
			on_change(report) {
				if (report.get_filter_value("group_by") === monthlyAchievementHierarchy && report.get_filter_value("period") !== "Monthly") {
					frappe.show_alert({ message: __("Month grouping uses the Monthly period. Period was set to Monthly."), indicator: "blue" });
					report.set_filter_value("period", "Monthly");
					return;
				}
				report.refresh();
			},
		},
		{
			fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "fiscal_year", label: __("Fiscal Year"), fieldtype: "Link", options: "Fiscal Year", reqd: 1,
			default: frappe.defaults.get_user_default("fiscal_year") || (frappe.boot.current_fiscal_year && frappe.boot.current_fiscal_year[0]),
		},
		{ fieldname: "pay_on", label: __("Pay Incentive On"), fieldtype: "Select", options: "Amount\nQty", default: "Amount", reqd: 1 },
		{
			fieldname: "period", label: __("Period"), fieldtype: "Select", options: ["Annual", "Monthly", "Quarterly"], default: "Monthly",
			on_change(report) {
				if (report.get_filter_value("period") !== "Monthly" && report.get_filter_value("group_by") === monthlyAchievementHierarchy) {
					frappe.show_alert({ message: __("Month grouping requires the Monthly period. Group By was reset."), indicator: "blue" });
					report.set_filter_value("group_by", "Territory → Item Group");
					return;
				}
				report.refresh();
			},
		},
		{ fieldname: "month", label: __("Month"), fieldtype: "Int", depends_on: "eval:doc.period === 'Monthly'" },
		{ fieldname: "quarter", label: __("Quarter"), fieldtype: "Int", depends_on: "eval:doc.period === 'Quarterly'" },
		{ fieldname: "incentive_band", label: __("Incentive Achievement"), fieldtype: "Select", options: "All\nMin\nMax\nNot Achieve", default: "All" },
		{ fieldname: "sales_person", label: __("Sales Person"), fieldtype: "Link", options: "Sales Person" },
		{ fieldname: "territory", label: __("Territory"), fieldtype: "Link", options: "Territory" },
		{
			fieldname: "item_group", label: __("Item Group"), fieldtype: "Link", options: "Item Group",
			get_query() { return { query: "sales_performance.api.planning.item_group_query" }; },
		},
		{ fieldname: "customer_group", label: __("Customer Group"), fieldtype: "Link", options: "Customer Group", default: "" },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
	],
	onload(report) {
		const filterForm = report.page.page_form;
		filterForm.find(".achievement-primary-filters, .achievement-secondary-filters").remove();
		const primaryRow = $('<div class="achievement-primary-filters"></div>').css({
			display: "flex", width: "100%", flexWrap: "nowrap", alignItems: "flex-end",
			minHeight: "60px", flexShrink: 0, gap: "4px",
		});
		const secondaryRow = $('<div class="achievement-secondary-filters"></div>').css({
			display: "flex", width: "100%", flexWrap: "nowrap", alignItems: "flex-end",
			position: "relative", zIndex: 1, minHeight: "60px", flexShrink: 0, gap: "8px",
		});
		filterForm.css({
			display: "flex", position: "relative", zIndex: 20, flexDirection: "column",
			alignItems: "stretch", flexShrink: 0, height: "auto", minHeight: 0,
			paddingBottom: "12px", marginBottom: "8px", gap: "4px", overflowX: "visible",
		});
		filterForm.append(primaryRow, secondaryRow);
		const secondaryFields = new Set(["sales_person", "item_group", "item", "customer_group", "territory"]);
		report.filters.forEach((filter) => {
			const wrapper = $(filter.wrapper);
			const secondary = secondaryFields.has(filter.fieldname);
			(secondary ? secondaryRow : primaryRow).append(wrapper);
			wrapper.css({ flex: "1 1 0", width: "auto", minWidth: secondary ? 0 : "70px", padding: "0 2px", margin: "4px 0" });
			wrapper.find(".control-label").css({ fontSize: "13px", fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }).attr("title", filter.label || "");
			wrapper.find(".form-control").css({ minWidth: 0, width: "100%", height: "30px", fontSize: "13px", padding: "4px 6px" });
			if (["sales_person", "territory"].includes(filter.fieldname)) {
				wrapper.css({ position: "relative", zIndex: 2 });
				wrapper.find(".awesomplete").css("z-index", 30);
				wrapper.find(".awesomplete > ul").css("z-index", 31);
			}
		});
		report.salesAchievementTreeDepth = Number(report.report_settings.initial_depth) || 0;
		const controls = $('<div class="achievement-tree-controls"></div>').css({ display: "flex", justifyContent: "flex-start", alignItems: "center", gap: "6px", padding: "4px 16px" });
		const collapseButton = $(`<button type="button" class="btn btn-default btn-xs" title="${__("Collapese")}" aria-label="${__("Collapese")}">${frappe.utils.icon("chevron-up", "sm")}</button>`)
			.css({ display: "inline-flex", alignItems: "center", gap: "5px", color: "#9a3412", background: "#ffedd5", borderColor: "#fdba74", fontWeight: 600, padding: "5px 9px" })
			.append($("<span>").text(__("Collapese")));
		const expandButton = $(`<button type="button" class="btn btn-default btn-xs" title="${__("Expand")}" aria-label="${__("Expand")}">${frappe.utils.icon("chevron-down", "sm")}</button>`)
			.css({ display: "inline-flex", alignItems: "center", gap: "5px", color: "#4338ca", background: "#e0e7ff", borderColor: "#a5b4fc", fontWeight: 600, padding: "5px 9px" })
			.append($("<span>").text(__("Expand")));
		const changeTreeDepth = (direction) => {
			const rowManager = report.datatable?.rowmanager;
			if (!rowManager) return;
			const rows = rowManager.datamanager.getRows();
			const maxDepth = rows.reduce((max, row) => Math.max(max, row.meta.indent || 0), 0);
			report.salesAchievementTreeDepth = Math.max(0, Math.min(maxDepth, report.salesAchievementTreeDepth + direction));
			rowManager.setTreeDepth(report.salesAchievementTreeDepth);
		};
		collapseButton.on("click", () => changeTreeDepth(-1));
		expandButton.on("click", () => changeTreeDepth(1));
		const printReport = () => {
			if (!frappe.model.can_print(report.report_doc.ref_doctype)) {
				frappe.msgprint(__("You do not have permission to print this report."));
				return;
			}
			report.get_validated_visible_indexes();
			const originalData = report.data || [];
			const visibleRows = report.get_data_for_print();
			const detailRows = originalData.filter((row) => !row.is_group_row && !row.is_total_row);
			const totalRow = originalData.find((row) => row.is_total_row) || {};
			const sum = (fieldname) => detailRows.reduce((total, row) => total + flt(row[fieldname]), 0);
			const payOn = report.get_filter_value("pay_on") || "Amount";
			const metric = payOn === "Qty" ? "qty" : "amount";
			const surplus = detailRows.reduce((total, row) => total + Math.max(flt(row[`actual_${metric}`]) - flt(row[`target_${metric}`]), 0), 0);
			const summary = {
				target_qty: totalRow.target_qty ?? sum("target_qty"),
				actual_qty: totalRow.actual_qty ?? sum("actual_qty"),
				qty_achievement_percent: totalRow.qty_achievement_percent ?? (sum("target_qty") ? sum("actual_qty") / sum("target_qty") * 100 : 0),
				target_amount: totalRow.target_amount ?? sum("target_amount"),
				actual_amount: totalRow.actual_amount ?? sum("actual_amount"),
				amount_achievement_percent: totalRow.amount_achievement_percent ?? (sum("target_amount") ? sum("actual_amount") / sum("target_amount") * 100 : 0),
				incentive_amount: totalRow.incentive_amount ?? sum("incentive_amount"),
				incentive_rate_percent: totalRow.incentive_rate_percent ?? (surplus ? sum("incentive_amount") / surplus * 100 : 0),
			};
			const rootGroups = originalData.filter((row) => row.is_group_row && !row._parent_node).length;
			const expandedNodes = originalData.filter((row) => row.is_group_row)
				.filter((row) => visibleRows.some((visibleRow) => visibleRow._parent_node === row._node))
				.map((row) => row._node);
			frappe.render_grid({
				template: salesTargetAchievementPrintTemplate,
				title: __("Sales Target Achievement"), subtitle: null,
				filters: report.get_filter_values(), data: visibleRows, original_data: originalData,
				columns: report.columns, landscape: true, print_settings: { orientation: "Landscape" },
				summary, group_count: rootGroups, item_count: detailRows.length,
				expanded_nodes: expandedNodes, updated: frappe.datetime.now_datetime(), search: "",
			});
		};
		report.page.remove_inner_button(__("Print"));
		report.page.add_inner_button(__("Print"), printReport, null, "primary");
		controls.append(collapseButton, expandButton);
		report.page.main.find(".achievement-tree-controls").remove();
		const reportWrapper = report.$report || report.page.main.find(".report-wrapper");
		if (reportWrapper.length) reportWrapper.before(controls);
	},
	formatter(value, row, column, data, default_formatter) {
		let formatted = (window.sales_performance && sales_performance.report_formatter)
			? sales_performance.report_formatter(value, row, column, data, default_formatter)
			: default_formatter(value, row, column, data);
		if (column.fieldname === "incentive_rate_percent") {
			const raw = data && data.incentive_rate_percent != null ? data.incentive_rate_percent : value;
			formatted = raw == null || raw === "" ? "" : `${format_number(Number(raw), null, 2)}%`;
		}
		if (!data) return formatted;
		if (data.is_total_row) {
			return `<strong style="color:#312e81;background:#e0e7ff;padding:3px 7px;border-radius:5px;display:inline-block">${formatted}</strong>`;
		}
		if (column.fieldname === "group_value") {
			if (!data.is_group_row) return "";
			const styles = {
				period: { label: __("PERIOD"), bg: "#dbeafe", fg: "#1e3a8a" },
				territory: { label: __("TERRITORY"), bg: "#ffedd5", fg: "#9a3412" },
				sales_person: { label: __("SALES PERSON"), bg: "#fee2e2", fg: "#991b1b" },
				customer_group: { label: __("CUSTOMER GROUP"), bg: "#dbeafe", fg: "#1e40af" },
				item_group: { label: __("ITEM GROUP"), bg: "#fae8ff", fg: "#86198f" },
				item_code: { label: __("ITEM"), bg: "#cffafe", fg: "#155e75" },
			};
			const style = styles[data._node_type] || { label: "", bg: "#f1f5f9", fg: "#334155" };
			const label = frappe.utils.escape_html(data._link_value || data.group_value || "");
			const doctype = { territory: "Territory", sales_person: "Sales Person", customer_group: "Customer Group", item_group: "Item Group", item_code: "Item" }[data._node_type];
			let content = label;
			if (doctype && data._link_value && frappe.utils.get_form_link) {
				const href = frappe.utils.escape_html(frappe.utils.get_form_link(doctype, data._link_value));
				content = `<a href="${href}" style="color:${style.fg};font-weight:700;text-decoration:none">${label}</a>`;
			}
			return `<span style="display:inline-flex;align-items:center;background:${style.bg};color:${style.fg};padding:3px 8px;border-radius:6px;font-weight:700"><span style="font-size:9px;letter-spacing:.04em;font-weight:800;margin-right:7px;color:#000000">${style.label}</span>${content}</span>`;
		}
		if (["qty_achievement_percent", "amount_achievement_percent"].includes(column.fieldname) && data[column.fieldname] != null) {
			const achievement = flt(data[column.fieldname]);
			const palette = achievement >= 100 ? { bg: "#dcfce7", fg: "#166534" } : achievement >= 80 ? { bg: "#fef3c7", fg: "#92400e" } : { bg: "#fee2e2", fg: "#b91c1c" };
			return `<span style="display:inline-block;background:${palette.bg};color:${palette.fg};padding:2px 7px;border-radius:999px;font-weight:700">${formatted}</span>`;
		}
		if (["variance_qty", "variance_amount"].includes(column.fieldname)) {
			return `<span style="font-weight:700;color:${flt(data[column.fieldname]) >= 0 ? "#15803d" : "#dc2626"}">${formatted}</span>`;
		}
		if (["incentive_amount", "incentive_rate_percent", "growth_percent"].includes(column.fieldname) && flt(data[column.fieldname]) > 0) {
			return `<span style="font-weight:700;color:${column.fieldname === "incentive_amount" ? "#b45309" : "#7c3aed"}">${formatted}</span>`;
		}
		return formatted;
	},
};
