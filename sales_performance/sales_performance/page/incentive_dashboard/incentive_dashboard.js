frappe.pages["incentive-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Incentive Dashboard"),
		single_column: true,
	});
	page.body.html(frappe.render_template("incentive_dashboard", {}));
	new IncentiveDashboard(wrapper, page);
};

class IncentiveDashboard {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.data = { rows: [], grouped: [], totals: {}, month_chart: [] };
		this.charts = {};
		this.loading_defaults = true;
		this.make_filters();
		this.bind();
		this.ready_filters().then(
			() => {
				this.loading_defaults = false;
				this.refresh();
			},
			() => {
				this.loading_defaults = false;
				this.refresh();
			}
		);
	}

	default_company() {
		return (
			frappe.defaults.get_user_default("Company") ||
			frappe.defaults.get_default("company") ||
			(frappe.boot.sysdefaults && frappe.boot.sysdefaults.company)
		);
	}

	default_fiscal_year() {
		return (
			frappe.defaults.get_user_default("fiscal_year") ||
			frappe.defaults.get_default("fiscal_year") ||
			(frappe.boot.sysdefaults && frappe.boot.sysdefaults.fiscal_year) ||
			(frappe.boot.current_fiscal_year && frappe.boot.current_fiscal_year[0])
		);
	}

	set_control_value(control, value) {
		if (value === undefined || value === null) {
			return Promise.resolve();
		}
		return Promise.resolve(control.set_value(value));
	}

	wait_for_required(tries = 20) {
		if (this.filters.company.get_value() && this.filters.fiscal_year.get_value()) {
			return Promise.resolve();
		}
		if (tries <= 0) {
			return Promise.resolve();
		}
		return new Promise((resolve) => setTimeout(resolve, 50)).then(() => this.wait_for_required(tries - 1));
	}

	set_fiscal_year_default() {
		const current = this.filters.fiscal_year.get_value() || this.default_fiscal_year();
		if (current && !String(current).startsWith("_Test")) {
			return this.set_control_value(this.filters.fiscal_year, current);
		}
		return frappe.db
			.get_list("Fiscal Year", {
				fields: ["name", "year_start_date", "year_end_date"],
				filters: { disabled: 0 },
				limit: 50,
				order_by: "year_start_date desc",
			})
			.then((list) => {
				const today = frappe.datetime.get_today();
				const hit =
					(list || []).find(
						(y) =>
							!String(y.name).startsWith("_Test") &&
							y.year_start_date <= today &&
							y.year_end_date >= today
					) || (list || []).find((y) => !String(y.name).startsWith("_Test"));
				if (hit) {
					return this.set_control_value(this.filters.fiscal_year, hit.name);
				}
			});
	}

	ready_filters() {
		return this.load_filter_options().then(() => Promise.all([
			this.set_control_value(this.filters.company, this.default_company()),
			this.set_control_value(this.filters.period, "Monthly"),
			this.set_control_value(this.filters.group_by, "sales_person"),
		]))
			.then(() => this.set_fiscal_year_default())
			.then(() => this.load_filter_options())
			.then(() => this.wait_for_required())
			.then(() => this.period_visibility());
	}

	make_filters() {
		const fields = [
			["company", "Select", __("Company"), "", this.default_company()],
			["fiscal_year", "Select", __("Fiscal Year"), "", this.default_fiscal_year()],
			["period", "Select", __("Period"), "Monthly\nQuarterly\nAnnual", "Monthly"],
			["month", "Select", __("Month"), "\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12"],
			["quarter", "Select", __("Quarter"), "\n1\n2\n3\n4"],
			["group_by", "Select", __("Group By"), "sales_person\nterritory\nitem_group\ncustomer_group\nitem\nperiod", "sales_person"],
			["sales_person", "Select", __("Sales Person"), ""],
			["territory", "Select", __("Territory"), ""],
			["item_group", "Select", __("Item Group"), ""],
			["customer_group", "Select", __("Customer Group"), ""],
			["item", "Select", __("Item"), ""],
		];
		this.filters = {};
		const host = this.wrapper.querySelector("#id-filters");
		fields.forEach(([name, fieldtype, label, options, value]) => {
			const parent = document.createElement("div");
			parent.className = "sp-filter-item";
			host.appendChild(parent);
			const control = frappe.ui.form.make_control({
				parent: $(parent),
				render_input: true,
				df: { fieldname: name, fieldtype, label, options, default: value, change: () => this.on_filter_change() },
			});
			this.filters[name] = control;
		});
		this.period_visibility();
	}

	load_filter_options() {
		return Promise.resolve(frappe.call({ method: "sales_performance.sales_performance.page.performance_analytics.performance_analytics.get_filter_options", args: { company: this.filters.company.get_value(), fiscal_year: this.filters.fiscal_year.get_value() } })).then((r) => {
			const lists = r.message || {};
			const fields = { company: "companies", fiscal_year: "fiscal_years", sales_person: "sales_persons", territory: "territories", item_group: "item_groups", customer_group: "customer_groups", item: "items" };
			Object.entries(fields).forEach(([field, key]) => { const control = this.filters[field]; const value = control.get_value(); control.df.options = ["", ...(lists[key] || [])].join("\n"); control.refresh(); if (value) control.set_value(value); });
		});
	}

	period_visibility() {
		const period = this.filters.period.get_value();
		sales_performance.set_filter_visible(this.filters.month, period === "Monthly");
		sales_performance.set_filter_visible(this.filters.quarter, period === "Quarterly");
	}

	on_filter_change() {
		this.period_visibility();
		if (this.loading_defaults) return;
		clearTimeout(this.filter_timer);
		this.filter_timer = setTimeout(() => this.refresh(), 150);
	}

	bind() {
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.wrapper.querySelector("#id-refresh").addEventListener("click", () => this.refresh());
		this.wrapper.querySelector("#id-payout").addEventListener("click", () => {
			frappe.new_doc("Sales Incentive Payout", {
				company: this.filters.company.get_value(),
				fiscal_year: this.filters.fiscal_year.get_value(),
				period: this.filters.period.get_value(),
				month: this.filters.month.get_value(),
				quarter: this.filters.quarter.get_value(),
				sales_person: this.filters.sales_person.get_value(),
				customer_group: this.filters.customer_group.get_value(),
			});
		});
		this.wrapper.querySelector("#id-search").addEventListener("input", (event) => this.render_table(event.target.value));
	}

	args() {
		return {
			company: this.filters.company.get_value(),
			fiscal_year: this.filters.fiscal_year.get_value(),
			period: this.filters.period.get_value() || "Monthly",
			month: this.filters.month.get_value(),
			quarter: this.filters.quarter.get_value(),
			group_by: this.filters.group_by.get_value() || "sales_person",
			sales_person: this.filters.sales_person.get_value(),
			territory: this.filters.territory.get_value(),
			item_group: this.filters.item_group.get_value(),
			customer_group: this.filters.customer_group.get_value(),
			item: this.filters.item.get_value(),
		};
	}

	refresh() {
		const args = this.args();
		if (!args.company || !args.fiscal_year) {
			if (this.loading_defaults) {
				return;
			}
			return frappe.msgprint(__("Company and Fiscal Year are required"));
		}
		const request_id = (this.request_id || 0) + 1;
		this.request_id = request_id;
		this.page.set_indicator(__("Loading"), "orange");
		frappe.call({
			method: "sales_performance.sales_performance.page.incentive_dashboard.incentive_dashboard.get_dashboard_data",
			args,
			freeze: true,
			freeze_message: __("Loading incentive dashboard..."),
			callback: (response) => {
				if (request_id !== this.request_id) return;
				this.data = response.message || {};
				this.render_summary();
				this.render_charts();
				this.render_table(this.wrapper.querySelector("#id-search").value);
				this.page.set_indicator(__("Updated"), "green");
			},
			error: () => this.page.set_indicator(__("Failed"), "red"),
		});
	}

	n(value, precision = 0) {
		if (precision === 1) {
			return window.sales_performance
				? sales_performance.format_percent(value)
				: format_number(value || 0, null, 1);
		}
		return window.sales_performance
			? sales_performance.format_qty(value)
			: format_number(value || 0, null, 0);
	}

	money(value) {
		return window.sales_performance
			? sales_performance.format_amount(value)
			: format_currency(value || 0, frappe.defaults.get_default("currency"), 0);
	}

	ach(value) {
		if (value == null || value === "") return "—";
		const n = Number(value);
		const klass = n >= 100 ? "sp-ok" : "sp-bad";
		return `<span class="${klass}">${this.n(n, 1)}%</span>`;
	}

	inc(value, as_money = false) {
		const n = Number(value || 0);
		const html = as_money ? this.money(n) : this.n(n);
		return n > 0 ? `<span class="sp-ok">${html}</span>` : html;
	}

	render_summary() {
		const t = this.data.totals || {};
		const cards = [
			[__("Target Qty"), this.n(t.target_qty, 0), ""],
			[__("Actual Qty"), this.n(t.actual_qty, 0), ""],
			[__("Achievement %"), this.ach(t.qty_achievement_percent), "id-accent"],
			[__("Incentive on Amount"), this.inc(t.incentive_on_amount, true), ""],
			[__("Incentive on Qty"), this.inc(t.incentive_on_qty), ""],
			[__("Payable Incentive"), this.inc(t.incentive_amount, true), "id-green"],
			[__("Accrued"), this.money(t.posted_incentive), ""],
			[__("Paid"), this.money(t.paid_incentive), "id-green"],
			[__("Not Paid"), this.money(t.unpaid_incentive), "id-orange"],
		];
		this.wrapper.querySelector("#id-summary").innerHTML = cards
			.map(([label, value, klass]) => `<div class="id-card ${klass}"><span>${label}</span><strong>${value}</strong></div>`)
			.join("");
	}

	render_charts() {
		const month_rows = this.data.month_chart || [];
		const dim_rows = this.data.grouped || [];
		this.draw_chart("#id-chart-month", month_rows.map((r) => r.dimension), month_rows.map((r) => Number(r.incentive_amount || 0)));
		this.wrapper.querySelector("#id-chart-dim-title").textContent = `${__("Incentive by")} ${__(this.filters.group_by.get_value() || "sales_person")}`;
		this.draw_chart("#id-chart-dim", dim_rows.slice(0, 12).map((r) => r.dimension), dim_rows.slice(0, 12).map((r) => Number(r.incentive_amount || 0)));
	}

	draw_chart(selector, labels, values) {
		const host = this.wrapper.querySelector(selector);
		if (!host) {
			return;
		}
		if (this.charts && this.charts[selector] && this.charts[selector].destroy) {
			try {
				this.charts[selector].destroy();
			} catch (e) {
				/* ignore */
			}
		}
		this.charts = this.charts || {};
		host.innerHTML = "";
		if (!labels.length || typeof frappe.Chart === "undefined") {
			host.innerHTML = `<div class="id-empty" style="display:block">${__("No chart data")}</div>`;
			return;
		}
		const number_opts =
			window.sales_performance && sales_performance.chart_number_opts
				? sales_performance.chart_number_opts(0)
				: { valuesOverPoints: 1, axisOptions: { shortenYAxisNumbers: 0 } };
		try {
			this.charts[selector] = new frappe.Chart(
				host,
				Object.assign(
					{
						data: { labels, datasets: [{ name: __("Incentive"), values }] },
						type: "bar",
						height: 280,
						colors: ["#2490ef"],
					},
					number_opts
				)
			);
			if (sales_performance.finish_chart) {
				sales_performance.finish_chart(this.charts[selector]);
			}
		} catch (e) {
			console.error(e);
			host.innerHTML = `<div class="id-empty" style="display:block">${__("No chart data")}</div>`;
		}
	}

	render_table(search) {
		const term = String(search || "").toLowerCase();
		const rows = (this.data.grouped || []).filter((row) => !term || String(row.dimension || "").toLowerCase().includes(term));
		const host = this.wrapper.querySelector("#id-table");
		const empty = this.wrapper.querySelector("#id-empty");
		this.wrapper.querySelector("#id-row-count").textContent = `${rows.length} ${__("groups")}`;
		if (!rows.length) {
			host.innerHTML = "";
			empty.style.display = "block";
			return;
		}
		empty.style.display = "none";
		const esc = (value) => frappe.utils.escape_html(String(value == null ? "" : value));
		const body = rows
			.map(
				(row) => `<tr>
				<td>${esc(row.dimension)}</td>
				<td>${this.n(row.target_qty, 0)}</td>
				<td>${this.n(row.actual_qty, 0)}</td>
				<td>${this.ach(row.qty_achievement_percent)}</td>
				<td>${this.money(row.target_amount)}</td>
				<td>${this.money(row.actual_amount)}</td>
				<td>${this.ach(row.amount_achievement_percent)}</td>
				<td>${this.inc(row.min_incentive_amount, true)}</td>
				<td>${this.inc(row.max_incentive_amount, true)}</td>
				<td>${this.inc(row.incentive_on_amount, true)}</td>
				<td>${this.inc(row.incentive_on_qty)}</td>
				<td>${this.inc(row.incentive_amount, true)}</td>
			</tr>`
			)
			.join("");
		const t = this.data.totals || {};
		host.innerHTML = `<div class="id-wrap"><table class="id-table">
			<thead><tr>
				<th>${__("Group")}</th><th>${__("Target Qty")}</th><th>${__("Actual Qty")}</th><th>${__("Qty Ach %")}</th>
				<th>${__("Target Amt")}</th><th>${__("Actual Amt")}</th><th>${__("Amt Ach %")}</th>
				<th>${__("Min Incentive")}</th><th>${__("Max Incentive")}</th>
				<th>${__("Incentive on Amount")}</th><th>${__("Incentive on Qty")}</th><th>${__("Payable")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
			<tfoot><tr>
				<td>${__("Total")}</td>
				<td>${this.n(t.target_qty, 0)}</td>
				<td>${this.n(t.actual_qty, 0)}</td>
				<td>${this.ach(t.qty_achievement_percent)}</td>
				<td>${this.money(t.target_amount)}</td>
				<td>${this.money(t.actual_amount)}</td>
				<td>${this.ach(t.amount_achievement_percent)}</td>
				<td>${this.inc(t.min_incentive_amount, true)}</td>
				<td>${this.inc(t.max_incentive_amount, true)}</td>
				<td>${this.inc(t.incentive_on_amount, true)}</td>
				<td>${this.inc(t.incentive_on_qty)}</td>
				<td>${this.inc(t.incentive_amount, true)}</td>
			</tr></tfoot>
		</table></div>`;
	}
}
