frappe.pages["target-achievement"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Target Achievement"),
		single_column: true,
	});
	page.body.html(frappe.render_template("target_achievement", {}));
	if (window.sales_performance && sales_performance.makePageFullWidth) {
		sales_performance.makePageFullWidth(page.body[0] || wrapper);
	}
	new TargetAchievement(wrapper, page);
};

class TargetAchievement {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.data = {};
		this.loading_defaults = true;
		this.make_filters();
        this.page.add_inner_button(__("Save View"), () => sales_performance.save_view("target_achievement", this.filters));
        this.page.add_inner_button(__("Load View"), () => sales_performance.restore_view("target_achievement", this.filters));
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
			this.set_control_value(this.filters.period, "Annual"),
			this.set_control_value(this.filters.judge, "Qty"),
		]))
			.then(() => this.set_fiscal_year_default())
			.then(() => this.load_filter_options())
			.then(() => this.set_control_value(this.filters.customer_group, "Market"))
			.then(async () => {
                const values = frappe.route_options || {}; frappe.route_options = null;
                for (const [key,value] of Object.entries(values)) if (this.filters[key]) await this.filters[key].set_value(value);
            })
            .then(() => this.wait_for_required())
			.then(() => this.period_visibility());
	}

	make_filters() {
		const fields = [
			["company", "Select", __("Company"), "", this.default_company()],
			["fiscal_year", "Select", __("Fiscal Year"), "", this.default_fiscal_year()],
			["period", "Select", __("Period"), "Monthly\nQuarterly\nAnnual", "Annual"],
			["month", "Select", __("Month"), "\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12"],
			["quarter", "Select", __("Quarter"), "\n1\n2\n3\n4"],
			["judge", "Select", __("Judge By"), "Qty\nAmount\nBoth", "Qty"],
			["sales_person", "Select", __("Sales Person"), ""],
			["territory", "Select", __("Territory"), ""],
			["item_group", "Select", __("Item Group"), ""],
			["customer_group", "Select", __("Customer Group"), "\nMarket", "Market"],
			["item", "Select", __("Item"), ""],
		];
		this.filters = {};
		const host = this.wrapper.querySelector("#ta-filters");
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
		this.wrapper.querySelector("#ta-refresh").addEventListener("click", () => this.refresh());
		this.wrapper.querySelector("#ta-reset").addEventListener("click", () => this.reset_filters());
		this.wrapper.querySelector("#ta-graphics").addEventListener("click", () => {
			frappe.route_options = Object.fromEntries(Object.entries(this.filters).map(([k,f])=>[k,f.get_value()]));
			frappe.set_route("achievement-graphics");
		});
		this.wrapper.querySelector("#ta-search").addEventListener("input", () => this.render());
	}

	reset_filters() {
		this.set_control_value(this.filters.company, this.default_company());
		this.set_control_value(this.filters.period, "Annual");
		this.set_control_value(this.filters.judge, "Qty");
		["month", "quarter", "sales_person", "territory", "item_group", "customer_group", "item"].forEach((name) => {
			this.set_control_value(this.filters[name], name === "customer_group" ? "Market" : "");
		});
		this.set_fiscal_year_default().then(() => {
			this.period_visibility();
			this.refresh();
		});
	}

	set_loading(on) {
		const el = this.wrapper.querySelector("#ta-loading");
		if (el) el.style.display = on ? "block" : "none";
	}

	set_error(msg) {
		const el = this.wrapper.querySelector("#ta-error");
		if (!el) return;
		el.style.display = msg ? "block" : "none";
		el.textContent = msg || "";
	}

	args() {
		return {
			company: this.filters.company.get_value(),
			fiscal_year: this.filters.fiscal_year.get_value(),
			period: this.filters.period.get_value() || "Annual",
			month: this.filters.month.get_value(),
			quarter: this.filters.quarter.get_value(),
			judge: this.filters.judge.get_value() || "Qty",
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
		this.set_loading(true);
		this.set_error("");
		frappe.call({
			method: "sales_performance.sales_performance.page.target_achievement.target_achievement.get_achievement_board",
			args,
			freeze: true,
			freeze_message: __("Loading target achievement..."),
			callback: (r) => {
				if (request_id !== this.request_id) return;
				this.data = r.message || {};
				this.render();
				this.page.set_indicator(__("Updated"), "green");
				const stamp = this.wrapper.querySelector("#ta-last-refresh");
				if (stamp) {
					stamp.textContent = sales_performance.stampNow
						? sales_performance.stampNow()
						: frappe.datetime.now_datetime();
				}
			},
			error: () => {
				this.set_error(__("Failed to load target achievement"));
				this.page.set_indicator(__("Failed"), "red");
			},
			always: () => this.set_loading(false),
		});
	}

	n(value, precision = 0) {
		if (precision === 1) {
			return window.sales_performance
				? sales_performance.format_percent(value)
				: format_number(value || 0, null, 0);
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

	delta(value, as_money = false) {
		const n = Number(value || 0);
		const klass = n > 0 ? "sp-ok" : n < 0 ? "sp-bad" : "";
		return `<span class="${klass}">${as_money ? this.money(n) : this.n(n)}</span>`;
	}

	render() {
		const t = this.data.totals || {};
		const set_stat = (id, value) => {
			const el = this.wrapper.querySelector(id);
			if (el) el.textContent = String(value || 0);
		};
		set_stat("#ta_stat_g_ok", t.item_groups_achieved);
		set_stat("#ta_stat_g_miss", t.item_groups_missed);
		set_stat("#ta_stat_i_ok", t.items_achieved);
		set_stat("#ta_stat_i_miss", t.items_missed);

		const term = String(this.wrapper.querySelector("#ta-search").value || "").toLowerCase();
		const match = (row) =>
			!term ||
			String(row.dimension || "").toLowerCase().includes(term) ||
			String(row.item_name || "").toLowerCase().includes(term);

		this.fill_table("ta-g-ok", "ta-g-ok-count", (this.data.item_groups_achieved || []).filter(match), false);
		this.fill_table("ta-g-miss", "ta-g-miss-count", (this.data.item_groups_missed || []).filter(match), false);
		this.fill_table("ta-i-ok", "ta-i-ok-count", (this.data.items_achieved || []).filter(match), true);
		this.fill_table("ta-i-miss", "ta-i-miss-count", (this.data.items_missed || []).filter(match), true);
	}

	fill_table(host_id, count_id, rows, is_item) {
		this.wrapper.querySelector(`#${count_id}`).textContent = `${rows.length} ${__("rows")}`;
		const host = this.wrapper.querySelector(`#${host_id}`);
		if (!rows.length) {
			host.innerHTML = `<div class="sp-empty">${__("No rows")}</div>`;
			return;
		}
		const esc = (v) => frappe.utils.escape_html(String(v == null ? "" : v));
		const name_header = is_item ? __("Item") : __("Item Group");
		const body = rows
			.map((r) => {
				const name = is_item ? r.item_name || r.dimension : r.dimension;
				const extra = is_item && r.dimension && r.item_name && r.dimension !== r.item_name
					? `<div class="text-muted">${esc(r.dimension)}</div>`
					: "";
				const qty_var = Number(r.actual_qty || 0) - Number(r.target_qty || 0);
				const amt_var = Number(r.actual_amount || 0) - Number(r.target_amount || 0);
				return `<tr>
					<td>${esc(name)}${extra}</td>
					<td>${this.n(r.target_qty, 0)}</td>
					<td>${this.n(r.actual_qty, 0)}</td>
					<td>${this.delta(qty_var)}</td>
					<td>${this.ach(r.qty_achievement_percent)}</td>
					<td>${this.money(r.target_amount)}</td>
					<td>${this.money(r.actual_amount)}</td>
					<td>${this.delta(amt_var, true)}</td>
					<td>${this.ach(r.amount_achievement_percent)}</td>
				</tr>`;
			})
			.join("");
		const targetQty = rows.reduce((sum, row) => sum + Number(row.target_qty || 0), 0);
		const actualQty = rows.reduce((sum, row) => sum + Number(row.actual_qty || 0), 0);
		const targetAmount = rows.reduce((sum, row) => sum + Number(row.target_amount || 0), 0);
		const actualAmount = rows.reduce((sum, row) => sum + Number(row.actual_amount || 0), 0);
		const qtyAchievement = targetQty ? (actualQty / targetQty) * 100 : null;
		const amountAchievement = targetAmount ? (actualAmount / targetAmount) * 100 : null;
		host.innerHTML = `<div class="sp-table-wrap"><table class="sp-table">
			<thead><tr>
				<th>${name_header}</th>
				<th>${__("Target Qty")}</th><th>${__("Actual Qty")}</th><th>${__("Qty Δ")}</th><th>${__("Qty Ach %")}</th>
				<th>${__("Target Amt")}</th><th>${__("Actual Amt")}</th><th>${__("Amt Δ")}</th><th>${__("Amt Ach %")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
			<tfoot><tr class="sp-total-row">
				<td><strong>${__("Total")}</strong></td>
				<td><strong>${this.n(targetQty, 0)}</strong></td>
				<td><strong>${this.n(actualQty, 0)}</strong></td>
				<td><strong>${this.delta(actualQty - targetQty)}</strong></td>
				<td><strong>${this.ach(qtyAchievement)}</strong></td>
				<td><strong>${this.money(targetAmount)}</strong></td>
				<td><strong>${this.money(actualAmount)}</strong></td>
				<td><strong>${this.delta(actualAmount - targetAmount, true)}</strong></td>
				<td><strong>${this.ach(amountAchievement)}</strong></td>
			</tr></tfoot>
		</table></div>`;
	}
}
