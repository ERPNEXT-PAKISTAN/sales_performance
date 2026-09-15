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
		this.loading_defaults = true;
		this.make_filters();
		this.bind();
		this.ready_filters().finally(() => {
			this.loading_defaults = false;
			this.refresh();
		});
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
		if (value === undefined || value === null || value === "") {
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
		return Promise.all([
			this.set_control_value(this.filters.company, this.default_company()),
			this.set_control_value(this.filters.period, "Monthly"),
			this.set_control_value(this.filters.group_by, "sales_person"),
		])
			.then(() => this.set_fiscal_year_default())
			.then(() => this.wait_for_required())
			.then(() => this.period_visibility());
	}

	make_filters() {
		const fields = [
			["company", "Link", __("Company"), "Company", this.default_company()],
			["fiscal_year", "Link", __("Fiscal Year"), "Fiscal Year", this.default_fiscal_year()],
			["period", "Select", __("Period"), "Monthly\nQuarterly\nAnnual", "Monthly"],
			["month", "Select", __("Month"), "\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12"],
			["quarter", "Select", __("Quarter"), "\n1\n2\n3\n4"],
			["group_by", "Select", __("Group By"), "sales_person\nterritory\nitem_group\nitem\nperiod", "sales_person"],
			["sales_person", "Link", __("Sales Person"), "Sales Person"],
			["territory", "Link", __("Territory"), "Territory"],
			["item_group", "Link", __("Item Group"), "Item Group"],
			["item", "Link", __("Item"), "Item"],
		];
		this.filters = {};
		const host = this.wrapper.querySelector("#id-filters");
		fields.forEach(([name, fieldtype, label, options, value]) => {
			const parent = document.createElement("div");
			host.appendChild(parent);
			const control = frappe.ui.form.make_control({
				parent: $(parent),
				render_input: true,
				df: { fieldname: name, fieldtype, label, options, default: value, change: () => this.period_visibility() },
			});
			this.filters[name] = control;
		});
		this.period_visibility();
	}

	period_visibility() {
		const period = this.filters.period.get_value();
		this.filters.month.df.hidden = period !== "Monthly";
		this.filters.quarter.df.hidden = period !== "Quarterly";
		this.filters.month.refresh();
		this.filters.quarter.refresh();
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
		this.page.set_indicator(__("Loading"), "orange");
		frappe.call({
			method: "sales_performance.sales_performance.page.incentive_dashboard.incentive_dashboard.get_dashboard_data",
			args,
			freeze: true,
			freeze_message: __("Loading incentive dashboard..."),
		}).then((response) => {
			this.data = response.message || {};
			this.render_summary();
			this.render_charts();
			this.render_table(this.wrapper.querySelector("#id-search").value);
			this.page.set_indicator(__("Updated"), "green");
		}).catch(() => this.page.set_indicator(__("Failed"), "red"));
	}

	n(value, precision = 2) {
		return Number(value || 0).toLocaleString(undefined, {
			minimumFractionDigits: precision,
			maximumFractionDigits: precision,
		});
	}

	render_summary() {
		const t = this.data.totals || {};
		const cards = [
			[__("Target Qty"), this.n(t.target_qty, 0), ""],
			[__("Actual Qty"), this.n(t.actual_qty, 0), ""],
			[__("Achievement %"), `${this.n(t.qty_achievement_percent, 1)}%`, "id-accent"],
			[__("Incentive on Amount"), this.n(t.incentive_on_amount), ""],
			[__("Incentive on Qty"), this.n(t.incentive_on_qty), ""],
			[__("Payable Incentive"), this.n(t.incentive_amount), "id-green"],
			[__("Accrued"), this.n(t.posted_incentive), ""],
			[__("Paid"), this.n(t.paid_incentive), "id-green"],
			[__("Not Paid"), this.n(t.unpaid_incentive), "id-orange"],
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
		host.innerHTML = "";
		if (!labels.length || typeof frappe.Chart === "undefined") {
			host.innerHTML = `<div class="id-empty" style="display:block">${__("No chart data")}</div>`;
			return;
		}
		this[selector] = new frappe.Chart(host, {
			data: { labels, datasets: [{ name: __("Incentive"), values }] },
			type: "bar",
			height: 220,
			colors: ["#2490ef"],
		});
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
				<td>${row.qty_achievement_percent == null ? "—" : `${this.n(row.qty_achievement_percent, 1)}%`}</td>
				<td>${this.n(row.target_amount)}</td>
				<td>${this.n(row.actual_amount)}</td>
				<td>${this.n(row.min_incentive_amount)}</td>
				<td>${this.n(row.max_incentive_amount)}</td>
				<td>${this.n(row.incentive_on_amount)}</td>
				<td>${this.n(row.incentive_on_qty)}</td>
				<td>${this.n(row.incentive_amount)}</td>
			</tr>`
			)
			.join("");
		const t = this.data.totals || {};
		host.innerHTML = `<div class="id-wrap"><table class="id-table">
			<thead><tr>
				<th>${__("Group")}</th><th>${__("Target Qty")}</th><th>${__("Actual Qty")}</th><th>${__("Ach %")}</th>
				<th>${__("Target Amt")}</th><th>${__("Actual Amt")}</th><th>${__("Min Incentive")}</th><th>${__("Max Incentive")}</th>
				<th>${__("Incentive on Amount")}</th><th>${__("Incentive on Qty")}</th><th>${__("Payable")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
			<tfoot><tr>
				<td>${__("Total")}</td>
				<td>${this.n(t.target_qty, 0)}</td>
				<td>${this.n(t.actual_qty, 0)}</td>
				<td>${this.n(t.qty_achievement_percent, 1)}%</td>
				<td>${this.n(t.target_amount)}</td>
				<td>${this.n(t.actual_amount)}</td>
				<td>${this.n(t.min_incentive_amount)}</td>
				<td>${this.n(t.max_incentive_amount)}</td>
				<td>${this.n(t.incentive_on_amount)}</td>
				<td>${this.n(t.incentive_on_qty)}</td>
				<td>${this.n(t.incentive_amount)}</td>
			</tr></tfoot>
		</table></div>`;
	}
}
