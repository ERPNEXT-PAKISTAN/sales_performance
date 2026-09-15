frappe.ui.form.on("Sales Target Planning", {
	refresh(frm) {
		frm.trigger("set_indicators");
		frm.trigger("set_item_group_queries");
		const locked = ["Approved", "Cancelled", "Superseded"].includes(frm.doc.status);
		frm.set_df_property("proposal_details", "read_only", locked);
		frm.set_df_property("growth_rules", "read_only", locked);

		if (!locked) {
			frm.page.set_primary_action(__("Get Previous Year Sales"), () => fetch_previous_year_sales(frm));
		}

		render_previous_sales_table(frm);

		if (!frm.is_new() && !locked) {
			if (["Draft", "Calculated", "Rejected"].includes(frm.doc.status)) {
				frm.add_custom_button(__("Submit for Review"), () => {
					frappe.call({
						method: "sales_performance.api.planning.submit_for_review",
						args: { name: frm.doc.name },
						callback: () => frm.reload_doc(),
					});
				});
			}
			if (["Calculated", "Under Review"].includes(frm.doc.status)) {
				frm.add_custom_button(__("Approve"), () => {
					frappe.confirm(__("Approve this plan and sync ERPNext targets?"), () => {
						frappe.call({
							method: "sales_performance.api.planning.approve_plan",
							args: { name: frm.doc.name },
							freeze: true,
							callback: () => frm.reload_doc(),
						});
					});
				});
				frm.add_custom_button(__("Reject"), () => {
					frappe.prompt(
						{ fieldname: "reason", label: __("Reason"), fieldtype: "Small Text" },
						(values) => {
							frappe.call({
								method: "sales_performance.api.planning.reject_plan",
								args: { name: frm.doc.name, reason: values.reason },
								callback: () => frm.reload_doc(),
							});
						},
						__("Reject Plan")
					);
				});
			}
		}

		if (frm.doc.status === "Approved") {
			frm.add_custom_button(__("Create Revision"), () => {
				frappe.call({
					method: "sales_performance.api.planning.create_revision",
					args: { name: frm.doc.name },
					callback: (r) => frappe.set_route("Form", "Sales Target Planning", r.message),
				});
			});
			frm.add_custom_button(__("Apply ERPNext Targets"), () => {
				frappe.call({
					method: "sales_performance.api.planning.apply_targets",
					args: { name: frm.doc.name },
					freeze: true,
					callback: (r) => {
						frappe.show_alert({
							message: __("Synced {0} target rows", [(r.message && r.message.synced) || 0]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			});
		}

		frm.dashboard.clear_headline();
		if (frm.doc.summary_warnings) {
			frm.dashboard.set_headline_alert(frappe.utils.escape_html(frm.doc.summary_warnings), "orange");
		}
	},

	get_previous_year_sales(frm) {
		fetch_previous_year_sales(frm);
	},

	item_group(frm) {
		frm.trigger("set_item_group_queries");
	},

	set_item_group_queries(frm) {
		const query = "sales_performance.api.planning.item_group_query";
		frm.set_query("item_group", () => ({
			query,
			filters: {},
		}));
		frm.set_query("item_group", "growth_rules", () => ({
			query,
			filters: {
				parent_item_group: frm.doc.item_group || undefined,
			},
		}));
	},

	set_indicators(frm) {
		const colors = {
			Draft: "gray",
			Calculating: "blue",
			Calculated: "blue",
			"Under Review": "orange",
			Approved: "green",
			Rejected: "red",
			Cancelled: "red",
			Superseded: "yellow",
		};
		if (frm.doc.status) {
			frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "gray");
		}
	},
});

frappe.ui.form.on("Target Proposal Detail", {
	approved_target_qty(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
	approved_target_rate(frm, cdt, cdn) {
		recalc_row(frm, cdt, cdn);
	},
});

function fetch_previous_year_sales(frm) {
	if (!frm.doc.company || !frm.doc.fiscal_year) {
		frappe.msgprint(__("Company and Fiscal Year are required"));
		return;
	}
	if (!frm.doc.title) {
		frm.set_value("title", `${frm.doc.company} ${frm.doc.fiscal_year}`);
	}
	const run = () => {
		frappe.call({
			method: "sales_performance.api.planning.recalculate",
			args: { name: frm.doc.name },
			freeze: true,
			freeze_message: __("Loading previous year sales into the table..."),
			callback: () => frm.reload_doc(),
		});
	};
	if (frm.is_new() || frm.is_dirty()) {
		frm.save().then(run);
	} else {
		run();
	}
}

function render_previous_sales_table(frm) {
	const field = frm.get_field("previous_sales_html");
	if (!field) return;

	const rows = (frm.doc.proposal_details || []).slice();
	const period =
		frm.doc.from_date && frm.doc.to_date
			? `${frappe.datetime.str_to_user(frm.doc.from_date)} – ${frappe.datetime.str_to_user(frm.doc.to_date)}`
			: __("previous calendar year");
	const search_value = (frm._stp_search || "").trim().toLowerCase();
	const visible = rows.filter((row) => {
		if (!search_value) return true;
		return [row.item_group, row.customer_group, row.item_code, row.item_name, row.sales_person]
			.join(" ")
			.toLowerCase()
			.includes(search_value);
	});
	const groups = group_previous_sales(visible);

	field.$wrapper.html(`
		<style>
			.stp-panel { border: 1px solid var(--border-color); border-radius: 8px; background: var(--card-bg); overflow: hidden; }
			.stp-toolbar { display: flex; gap: 12px; align-items: center; justify-content: space-between; flex-wrap: wrap; padding: 10px 12px; border-bottom: 1px solid var(--border-color); }
			.stp-toolbar input { max-width: 260px; }
			.stp-hint { color: var(--text-muted); font-size: 12px; }
			.stp-empty { padding: 28px 12px; text-align: center; color: var(--text-muted); }
			.stp-wrap { overflow: auto; max-height: 560px; }
			.stp-table { width: 100%; border-collapse: collapse; font-size: 12px; }
			.stp-table th, .stp-table td { padding: 7px 8px; border-bottom: 1px solid var(--border-color); text-align: right; white-space: nowrap; }
			.stp-table th:nth-child(-n+3), .stp-table td:nth-child(-n+3) { text-align: left; }
			.stp-table thead th { position: sticky; top: 0; background: var(--fg-color); z-index: 1; }
			.stp-group td { background: var(--subtle-fg); font-weight: 600; cursor: pointer; text-align: left; }
			.stp-item { display: none; }
			.stp-item.open { display: table-row; }
			.stp-caret { display: inline-block; width: 14px; }
			.stp-total td { font-weight: 700; background: var(--fg-color); }
		</style>
		<div class="stp-panel">
			<div class="stp-toolbar">
				<div>
					<div class="stp-hint">${__("Yearly target = previous calendar year. Monthly = PY ÷ 12. Quarter = monthly × 3. Growth % applies on top of that average.")}</div>
					<div class="stp-hint">${period} · ${visible.length} ${__("items")} · ${__("Growth")} ${Number(flt(frm.doc.uniform_growth_percent) || 0).toFixed(1)}% · ${frappe.utils.escape_html(frm.doc.distribution_method || "")}</div>
				</div>
				<input type="search" class="form-control input-sm" id="stp-search" placeholder="${__("Search item / group")}" value="${frappe.utils.escape_html(frm._stp_search || "")}">
			</div>
			<div class="stp-table-host"></div>
		</div>
	`);

	const host = field.$wrapper.find(".stp-table-host");
	if (!rows.length) {
		host.html(`<div class="stp-empty">${__("Click Get Previous Year Sales to load previous calendar year sales.")}</div>`);
		return;
	}
	if (!visible.length) {
		host.html(`<div class="stp-empty">${__("No items match the search.")}</div>`);
		bind_search(frm, field);
		return;
	}

	const escape = (value) => frappe.utils.escape_html(String(value == null ? "" : value));
	const num = (value) =>
		window.sales_performance ? sales_performance.format_qty(value) : format_number(value || 0, null, 0);
	const money = (value) =>
		window.sales_performance
			? sales_performance.format_amount(value)
			: format_currency(value || 0, frappe.defaults.get_default("currency"), 0);
	const head = [
		__("Item Group / Item"),
		__("Sales Person"),
		__("Customer Group"),
		__("PY Qty"),
		__("Avg / Month"),
		__("Monthly Target"),
		__("Quarter Target"),
		__("Yearly Target"),
		__("Rate"),
		__("Target Amount"),
	]
		.map((label) => `<th>${label}</th>`)
		.join("");

	const avg_month = (qty) => flt(qty) / 12;
	const monthly_target = (row) => flt(row.calculated_target_qty) / 12;
	const quarter_target = (row) => monthly_target(row) * 3;

	const body = groups
		.map((group, index) => {
			const items = group.items
				.map(
					(row) => `
					<tr class="stp-item" data-parent="${index}">
						<td>${escape(row.item_name || row.item_code)}</td>
						<td>${escape(row.sales_person || __("Not Set"))}</td>
						<td>${escape(row.customer_group || __("Not Set"))}</td>
						<td>${num(row.previous_year_actual_qty)}</td>
						<td>${num(avg_month(row.previous_year_actual_qty))}</td>
						<td>${num(monthly_target(row))}</td>
						<td>${num(quarter_target(row))}</td>
						<td>${num(row.calculated_target_qty)}</td>
						<td>${money(row.target_selling_rate)}</td>
						<td>${money(row.calculated_target_amount)}</td>
					</tr>`
				)
				.join("");
			return `
				<tr class="stp-group" data-group="${index}">
					<td colspan="3"><span class="stp-caret">▶</span>${escape(group.item_group)} (${group.items.length})</td>
					<td>${num(group.previous_year_actual_qty)}</td>
					<td>${num(avg_month(group.previous_year_actual_qty))}</td>
					<td>${num(avg_month(group.calculated_target_qty))}</td>
					<td>${num(avg_month(group.calculated_target_qty) * 3)}</td>
					<td>${num(group.calculated_target_qty)}</td>
					<td></td>
					<td>${money(group.calculated_target_amount)}</td>
				</tr>${items}`;
		})
		.join("");

	const totals = sum_previous_sales(visible);
	host.html(`
		<div class="stp-wrap">
			<table class="stp-table">
				<thead><tr>${head}</tr></thead>
				<tbody>
					${body}
					<tr class="stp-total">
						<td colspan="3">${__("Grand Total")}</td>
						<td>${num(totals.previous_year_actual_qty)}</td>
						<td>${num(totals.previous_year_actual_qty / 12)}</td>
						<td>${num(totals.calculated_target_qty / 12)}</td>
						<td>${num((totals.calculated_target_qty / 12) * 3)}</td>
						<td>${num(totals.calculated_target_qty)}</td>
						<td></td>
						<td>${money(totals.calculated_target_amount)}</td>
					</tr>
				</tbody>
			</table>
		</div>
	`);

	host.find(".stp-group").on("click", function () {
		const index = this.dataset.group;
		const opening = !this.classList.contains("open");
		this.classList.toggle("open", opening);
		this.querySelector(".stp-caret").textContent = opening ? "▼" : "▶";
		host.find(`.stp-item[data-parent="${index}"]`).toggleClass("open", opening);
	});
	bind_search(frm, field);
}

function bind_search(frm, field) {
	field.$wrapper.find("#stp-search").on("input", function () {
		frm._stp_search = this.value;
		render_previous_sales_table(frm);
		const input = frm.get_field("previous_sales_html").$wrapper.find("#stp-search").get(0);
		if (input) {
			input.focus();
			input.setSelectionRange(input.value.length, input.value.length);
		}
	});
}

function group_previous_sales(rows) {
	const groups = [];
	const index = {};
	rows.forEach((row) => {
		const key = row.item_group || __("Ungrouped");
		if (!index[key]) {
			index[key] = {
				item_group: key,
				items: [],
				previous_year_actual_qty: 0,
				previous_year_actual_amount: 0,
				calculated_target_qty: 0,
				calculated_target_amount: 0,
			};
			groups.push(index[key]);
		}
		const group = index[key];
		group.items.push(row);
		group.previous_year_actual_qty += flt(row.previous_year_actual_qty);
		group.previous_year_actual_amount += flt(row.previous_year_actual_amount);
		group.calculated_target_qty += flt(row.calculated_target_qty);
		group.calculated_target_amount += flt(row.calculated_target_amount);
	});
	groups.sort((a, b) => b.previous_year_actual_qty - a.previous_year_actual_qty);
	return groups;
}

function sum_previous_sales(rows) {
	return rows.reduce(
		(sum, row) => {
			sum.previous_year_actual_qty += flt(row.previous_year_actual_qty);
			sum.previous_year_actual_amount += flt(row.previous_year_actual_amount);
			sum.calculated_target_qty += flt(row.calculated_target_qty);
			sum.calculated_target_amount += flt(row.calculated_target_amount);
			return sum;
		},
		{
			previous_year_actual_qty: 0,
			previous_year_actual_amount: 0,
			calculated_target_qty: 0,
			calculated_target_amount: 0,
		}
	);
}

function recalc_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const qty = flt(row.approved_target_qty);
	const rate = flt(row.approved_target_rate);
	row.approved_target_amount = qty * rate;
	const calc = flt(row.calculated_target_qty);
	row.override_percent = calc ? ((qty - calc) / calc) * 100 : 0;
	frm.refresh_field("proposal_details");
	render_previous_sales_table(frm);
}
