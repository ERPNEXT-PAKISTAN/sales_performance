frappe.pages["performance-analytics"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Performance Analytics"),
		single_column: true,
	});
	page.body.html(frappe.render_template("performance_analytics", {}));
	new PerformanceAnalytics(wrapper, page);
};

class PerformanceAnalytics {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.tab = "overview";
		this.data = {};
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
			this.set_control_value(this.filters.period, "Annual"),
			this.set_control_value(this.filters.group_by, "sales_person"),
		])
			.then(() => this.set_fiscal_year_default())
			.then(() => this.wait_for_required());
	}

	make_filters() {
		const fy = this.default_fiscal_year();
		const fields = [
			["company", "Link", __("Company"), "Company", this.default_company()],
			["fiscal_year", "Link", __("Fiscal Year"), "Fiscal Year", fy],
			["period", "Select", __("Incentive Period"), "Monthly\nQuarterly\nAnnual", "Annual"],
			["group_by", "Select", __("Incentive Group"), "sales_person\nterritory\nitem_group\nitem\nperiod", "sales_person"],
			["month", "Select", __("Month"), "\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12"],
			["quarter", "Select", __("Quarter"), "\n1\n2\n3\n4"],
			["sales_person", "Link", __("Sales Person"), "Sales Person"],
			["territory", "Link", __("Territory"), "Territory"],
			["item_group", "Link", __("Item Group"), "Item Group"],
			["customer", "Link", __("Customer"), "Customer"],
			["item", "Link", __("Item"), "Item"],
		];
		this.filters = {};
		const host = this.wrapper.querySelector("#pa-filters");
		fields.forEach(([name, fieldtype, label, options, value]) => {
			const parent = document.createElement("div");
			host.appendChild(parent);
			const control = frappe.ui.form.make_control({
				parent: $(parent),
				render_input: true,
				df: { fieldname: name, fieldtype, label, options, default: value },
			});
			this.filters[name] = control;
		});
	}

	bind() {
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.wrapper.querySelector("#pa-refresh").addEventListener("click", () => this.refresh());
		this.wrapper.querySelector("#pa-planning").addEventListener("click", () => {
			frappe.new_doc("Sales Target Planning", {
				company: this.filters.company.get_value(),
				fiscal_year: this.filters.fiscal_year.get_value(),
			});
		});
		this.wrapper.querySelector("#pa-payout").addEventListener("click", () => {
			frappe.new_doc("Sales Incentive Payout", {
				company: this.filters.company.get_value(),
				fiscal_year: this.filters.fiscal_year.get_value(),
				sales_person: this.filters.sales_person.get_value(),
			});
		});
		this.wrapper.querySelector("#pa-search").addEventListener("input", () => this.render());
		this.wrapper.querySelectorAll(".pa-tab").forEach((btn) => {
			btn.addEventListener("click", () => {
				this.tab = btn.dataset.tab;
				this.wrapper.querySelectorAll(".pa-tab").forEach((el) => el.classList.toggle("active", el === btn));
				this.render();
			});
		});
	}

	args() {
		return {
			company: this.filters.company.get_value(),
			fiscal_year: this.filters.fiscal_year.get_value(),
			period: this.filters.period.get_value() || "Annual",
			month: this.filters.month.get_value(),
			quarter: this.filters.quarter.get_value(),
			sales_person: this.filters.sales_person.get_value(),
			territory: this.filters.territory.get_value(),
			item_group: this.filters.item_group.get_value(),
			customer: this.filters.customer.get_value(),
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
			method: "sales_performance.sales_performance.page.performance_analytics.performance_analytics.get_analytics",
			args,
			freeze: true,
			freeze_message: __("Loading analytics..."),
		}).then((r) => {
			this.data = r.message || {};
			this.render();
			this.page.set_indicator(__("Updated"), "green");
		}).catch(() => this.page.set_indicator(__("Failed"), "red"));
	}

	n(value, precision = 2) {
		return Number(value || 0).toLocaleString(undefined, {
			minimumFractionDigits: precision,
			maximumFractionDigits: precision,
		});
	}

	pct(value) {
		if (value == null || value === "") return "—";
		const n = Number(value);
		const klass = n > 0 ? "pa-up" : n < 0 ? "pa-down" : "";
		const arrow = n > 0 ? "↑" : n < 0 ? "↓" : "";
		return `<span class="${klass}">${arrow} ${this.n(Math.abs(n), 1)}%</span>`;
	}

	delta(value) {
		const n = Number(value || 0);
		const klass = n > 0 ? "pa-up" : n < 0 ? "pa-down" : "";
		return `<span class="${klass}">${this.n(n)}</span>`;
	}

	render() {
		this.render_kpis();
		this.render_charts();
		this.render_table();
	}

	summarize(rows) {
		const qty = rows.reduce((s, r) => s + Number(r.current_qty || 0), 0);
		const pq = rows.reduce((s, r) => s + Number(r.previous_qty || 0), 0);
		const amt = rows.reduce((s, r) => s + Number(r.current_amount || 0), 0);
		const pa = rows.reduce((s, r) => s + Number(r.previous_amount || 0), 0);
		const tq = rows.reduce((s, r) => s + Number(r.target_qty || 0), 0);
		const ta = rows.reduce((s, r) => s + Number(r.target_amount || 0), 0);
		const growthParts = rows
			.filter((r) => r.growth_percent != null && r.growth_percent !== "")
			.map((r) => [Number(r.growth_percent), Number(r.previous_qty || r.target_qty || 0) || 1]);
		const growthWeight = growthParts.reduce((s, part) => s + part[1], 0);
		const gw = growthParts.reduce((s, part) => s + part[0] * part[1], 0);
		const amtVar = amt - pa;
		return {
			previous_qty: pq,
			current_qty: qty,
			qty_variance: qty - pq,
			qty_variance_percent: pq ? ((qty - pq) / pq) * 100 : null,
			previous_amount: pa,
			current_amount: amt,
			amount_variance: amtVar,
			amount_variance_percent: pa ? (amtVar / pa) * 100 : null,
			target_qty: tq,
			target_amount: ta,
			growth_percent: growthWeight ? gw / growthWeight : null,
			qty_achievement_percent: tq ? (qty / tq) * 100 : null,
			amount_achievement_percent: ta ? (amt / ta) * 100 : null,
			up_count: rows.filter((r) => Number(r.amount_variance || 0) > 0).length,
			down_count: rows.filter((r) => Number(r.amount_variance || 0) < 0).length,
		};
	}

	plan_pct(value) {
		if (value == null || value === "") return "—";
		return `${this.n(Number(value), 1)}%`;
	}

	kpis_for_tab() {
		const i = (this.data.incentive && this.data.incentive.totals) || {};
		const p = (this.data.payout && this.data.payout.totals) || {};
		if (this.tab === "incentive") {
			return [
				[__("Incentive"), this.n(i.incentive_amount)],
				[__("Min band"), this.n(i.min_incentive_amount)],
				[__("Max band"), this.n(i.max_incentive_amount)],
				[__("Target Amt"), this.n(i.target_amount)],
				[__("Actual Amt"), this.n(i.actual_amount)],
				[__("Qty Ach %"), `${this.n(i.qty_achievement_percent, 1)}%`],
			];
		}
		if (this.tab === "payout") {
			return [
				[__("Payouts"), this.n(p.count, 0)],
				[__("Draft"), this.n(p.draft)],
				[__("Accrued"), this.n(p.accrued)],
				[__("Paid"), this.n(p.paid)],
				[__("Not Paid"), this.n(p.unpaid)],
				[__("Incentive calc"), this.n(i.incentive_amount)],
			];
		}
		const o = this.summarize(this.tab_rows());
		return [
			[__("Previous Year Amt"), this.n(o.previous_amount)],
			[__("This Year Amt"), this.n(o.current_amount)],
			[__("Amount Δ"), this.delta(o.amount_variance)],
			[__("Amount %"), this.pct(o.amount_variance_percent)],
			[__("Plan Growth %"), this.plan_pct(o.growth_percent)],
			[__("Up / Down"), `${o.up_count || 0} / ${o.down_count || 0}`],
		];
	}

	render_kpis() {
		this.wrapper.querySelector("#pa-summary").innerHTML = this.kpis_for_tab()
			.map(([label, value]) => `<div class="pa-card"><span>${label}</span><strong>${value}</strong></div>`)
			.join("");
	}

	incentive_rows() {
		const inc = this.data.incentive || {};
		const map = {
			sales_person: "by_sales_person",
			territory: "by_territory",
			item_group: "by_item_group",
			item: "by_item",
			period: "by_period",
		};
		const key = map[this.filters.group_by && this.filters.group_by.get_value()] || "by_sales_person";
		return inc[key] || [];
	}

	sales_rows(dimension) {
		return ((this.data.sales || {})[dimension] || []).slice();
	}

	tab_rows() {
		const map = {
			overview: this.sales_rows("sales_person"),
			sales: this.sales_rows("item"),
			salesperson: this.sales_rows("sales_person"),
			territory: this.sales_rows("territory"),
			itemgroup: this.sales_rows("item_group"),
			item: this.sales_rows("item"),
			customer: this.sales_rows("customer"),
			incentive: this.incentive_rows(),
			payout: this.data.payout && this.data.payout.by_sales_person,
		};
		return (map[this.tab] || []).slice();
	}

	render_charts() {
		const trend = this.data.trend || [];
		this.wrapper.querySelector("#pa-chart-a-title").textContent = __("Monthly amount: this year vs previous year");
		this.chart("#pa-chart-a", trend.map((r) => r.dimension), [
			{ name: __("This Year"), values: trend.map((r) => Number(r.current_amount || 0)) },
			{ name: __("Previous Year"), values: trend.map((r) => Number(r.previous_amount || 0)) },
		], "axis-mixed");
		const movers = this.tab_rows().slice(0, 12);
		const changeKey = this.tab === "incentive" || this.tab === "payout" ? "incentive_amount" : "amount_variance";
		this.wrapper.querySelector("#pa-chart-b-title").textContent =
			this.tab === "incentive" || this.tab === "payout" ? __("Incentive by sales person") : __("Largest amount change");
		this.chart("#pa-chart-b", movers.map((r) => r.dimension), [
			{ name: __("Change"), values: movers.map((r) => Number(r[changeKey] || r.amount_variance || 0)) },
		], "bar");
	}

	chart(selector, labels, datasets, type) {
		const host = this.wrapper.querySelector(selector);
		host.innerHTML = "";
		if (!labels.length || typeof frappe.Chart === "undefined") {
			host.innerHTML = `<div class="pa-empty" style="display:block">${__("No chart data")}</div>`;
			return;
		}
		new frappe.Chart(host, { data: { labels, datasets }, type: type === "bar" ? "bar" : "line", height: 240, colors: ["#2490ef", "#98d1ff"] });
	}

	render_table() {
		const term = String(this.wrapper.querySelector("#pa-search").value || "").toLowerCase();
		const rows = this.tab_rows().filter((r) => !term || String(r.dimension || r.name || "").toLowerCase().includes(term));
		const titles = {
			overview: __("Sales Person — PY vs this year vs target"),
			sales: __("Item — PY vs this year vs target"),
			incentive: __("Incentive by sales person"),
			payout: __("Accrued incentive by sales person"),
			salesperson: __("Sales Person"),
			territory: __("Territory"),
			itemgroup: __("Item Group"),
			item: __("Item"),
			customer: __("Customer"),
		};
		this.wrapper.querySelector("#pa-table-title").textContent = titles[this.tab] || __("Detail");
		this.wrapper.querySelector("#pa-row-count").textContent = `${rows.length} ${__("rows")}`;
		const host = this.wrapper.querySelector("#pa-table");
		const empty = this.wrapper.querySelector("#pa-empty");
		if (!rows.length) {
			host.innerHTML = "";
			empty.style.display = "block";
			return;
		}
		empty.style.display = "none";
		if (this.tab === "incentive") {
			host.innerHTML = this.incentive_table(rows);
			return;
		}
		if (this.tab === "payout") {
			host.innerHTML = this.payout_table(rows);
			return;
		}
		const esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));
		const tot = this.summarize(rows);
		const body = rows
			.map(
				(r) => `<tr>
				<td>${esc(r.dimension)}</td>
				<td>${this.plan_pct(r.growth_percent)}</td>
				<td>${this.n(r.previous_qty, 0)}</td>
				<td>${this.n(r.current_qty, 0)}</td>
				<td>${this.delta(r.qty_variance)}</td>
				<td>${this.pct(r.qty_variance_percent)}</td>
				<td>${this.n(r.previous_amount)}</td>
				<td>${this.n(r.current_amount)}</td>
				<td>${this.delta(r.amount_variance)}</td>
				<td>${this.pct(r.amount_variance_percent)}</td>
				<td>${this.n(r.target_amount)}</td>
				<td>${r.amount_achievement_percent == null ? "—" : `${this.n(r.amount_achievement_percent, 1)}%`}</td>
			</tr>`
			)
			.join("");
		host.innerHTML = `<div class="pa-wrap"><table class="pa-table">
			<thead><tr>
				<th>${__("Name")}</th>
				<th>${__("Growth %")}</th>
				<th>${__("PY Qty")}</th><th>${__("TY Qty")}</th><th>${__("Qty Δ")}</th><th>${__("Qty %")}</th>
				<th>${__("PY Amt")}</th><th>${__("TY Amt")}</th><th>${__("Amt Δ")}</th><th>${__("Amt %")}</th>
				<th>${__("Target Amt")}</th><th>${__("Amt Ach %")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
			<tfoot><tr>
				<td>${__("Total")}</td>
				<td>${this.plan_pct(tot.growth_percent)}</td>
				<td>${this.n(tot.previous_qty, 0)}</td>
				<td>${this.n(tot.current_qty, 0)}</td>
				<td>${this.delta(tot.qty_variance)}</td>
				<td>${this.pct(tot.qty_variance_percent)}</td>
				<td>${this.n(tot.previous_amount)}</td>
				<td>${this.n(tot.current_amount)}</td>
				<td>${this.delta(tot.amount_variance)}</td>
				<td>${this.pct(tot.amount_variance_percent)}</td>
				<td>${this.n(tot.target_amount)}</td>
				<td>${tot.amount_achievement_percent == null ? "—" : `${this.n(tot.amount_achievement_percent, 1)}%`}</td>
			</tr></tfoot>
		</table></div>`;
	}

	incentive_table(rows) {
		const esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));
		const body = rows
			.map(
				(r) => `<tr>
				<td>${esc(r.dimension)}</td>
				<td>${this.n(r.target_qty, 0)}</td>
				<td>${this.n(r.actual_qty, 0)}</td>
				<td>${r.qty_achievement_percent == null ? "—" : `${this.n(r.qty_achievement_percent, 1)}%`}</td>
				<td>${this.n(r.target_amount)}</td>
				<td>${this.n(r.actual_amount)}</td>
				<td>${this.n(r.min_incentive_amount)}</td>
				<td>${this.n(r.max_incentive_amount)}</td>
				<td>${this.n(r.incentive_on_amount)}</td>
				<td>${this.n(r.incentive_on_qty)}</td>
				<td>${this.n(r.incentive_amount)}</td>
			</tr>`
			)
			.join("");
		return `<div class="pa-wrap"><table class="pa-table">
			<thead><tr>
				<th>${__("Name")}</th>
				<th>${__("Target Qty")}</th><th>${__("Actual Qty")}</th><th>${__("Qty Ach %")}</th>
				<th>${__("Target Amt")}</th><th>${__("Actual Amt")}</th>
				<th>${__("Min Incentive")}</th><th>${__("Max Incentive")}</th>
				<th>${__("Incentive on Amount")}</th><th>${__("Incentive on Qty")}</th><th>${__("Payable")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table></div>`;
	}

	payout_table(rows) {
		const esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));
		const docs = ((this.data.payout || {}).documents || []).filter((d) => {
			const term = String(this.wrapper.querySelector("#pa-search").value || "").toLowerCase();
			if (!term) return true;
			return String(d.name || "").toLowerCase().includes(term) || String(d.sales_person || "").toLowerCase().includes(term);
		});
		const byPerson = rows
			.map(
				(r) => `<tr>
				<td>${esc(r.dimension)}</td>
				<td>${this.n(r.rows, 0)}</td>
				<td>${this.n(r.incentive_amount)}</td>
			</tr>`
			)
			.join("");
		const docRows = docs
			.map(
				(d) => `<tr>
				<td>${esc(d.name)}</td>
				<td>${esc(d.sales_person)}</td>
				<td>${esc(d.period || "")} ${esc(d.month || "")}</td>
				<td>${esc(d.payment_status || (d.docstatus === 1 ? "Submitted" : "Draft"))}</td>
				<td>${this.n(d.total_incentive_amount)}</td>
			</tr>`
			)
			.join("");
		return `<div class="pa-wrap">
			<table class="pa-table">
				<thead><tr>
					<th>${__("Sales Person")}</th><th>${__("Lines")}</th><th>${__("Incentive Amt")}</th>
				</tr></thead>
				<tbody>${byPerson}</tbody>
			</table>
			<table class="pa-table" style="margin-top:16px">
				<thead><tr>
					<th>${__("Payout")}</th><th>${__("Sales Person")}</th><th>${__("Period")}</th>
					<th>${__("Status")}</th><th>${__("Amount")}</th>
				</tr></thead>
				<tbody>${docRows || `<tr><td colspan="5">${__("No payout documents")}</td></tr>`}</tbody>
			</table>
		</div>`;
	}
}
