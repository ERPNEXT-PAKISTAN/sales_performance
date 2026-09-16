frappe.pages["achievement-graphics"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Achievement Graphics"),
		single_column: true,
	});
	page.body.html(frappe.render_template("achievement_graphics", {}));
	if (window.sales_performance && sales_performance.makePageFullWidth) {
		sales_performance.makePageFullWidth(page.body[0] || wrapper);
	}
	new AchievementGraphics(wrapper, page);
};

class AchievementGraphics {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.data = {};
		this.charts = {};
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
			["customer_group", "Select", __("Customer Group"), ""],
			["item", "Select", __("Item"), ""],
		];
		this.filters = {};
		const host = this.wrapper.querySelector("#ag-filters");
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
		this.wrapper.querySelector("#ag-refresh").addEventListener("click", () => this.refresh());
		this.wrapper.querySelector("#ag-reset").addEventListener("click", () => this.reset_filters());
		this.wrapper.querySelector("#ag-tables").addEventListener("click", () => {
			frappe.set_route("target-achievement");
		});
	}

	reset_filters() {
		this.set_control_value(this.filters.company, this.default_company());
		this.set_control_value(this.filters.period, "Annual");
		this.set_control_value(this.filters.judge, "Qty");
		["month", "quarter", "sales_person", "territory", "item_group", "customer_group", "item"].forEach((name) => {
			this.set_control_value(this.filters[name], "");
		});
		this.set_fiscal_year_default().then(() => {
			this.period_visibility();
			this.refresh();
		});
	}

	set_loading(on) {
		const el = this.wrapper.querySelector("#ag-loading");
		if (el) el.style.display = on ? "block" : "none";
	}

	set_error(msg) {
		const el = this.wrapper.querySelector("#ag-error");
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
			method: "sales_performance.sales_performance.page.achievement_graphics.achievement_graphics.get_graphics_data",
			args,
			freeze: true,
			freeze_message: __("Loading graphics..."),
			callback: (r) => {
				if (request_id !== this.request_id) return;
				this.data = r.message || {};
				this.render();
				this.page.set_indicator(__("Updated"), "green");
				const stamp = this.wrapper.querySelector("#ag-last-refresh");
				if (stamp) {
					stamp.textContent = sales_performance.stampNow
						? sales_performance.stampNow()
						: frappe.datetime.now_datetime();
				}
			},
			error: () => {
				this.set_error(__("Failed to load graphics"));
				this.page.set_indicator(__("Failed"), "red");
			},
			always: () => this.set_loading(false),
		});
	}

	n(value) {
		return window.sales_performance ? sales_performance.format_qty(value) : format_number(value || 0, null, 0);
	}

	score(row) {
		const judge = (this.filters.judge && this.filters.judge.get_value()) || "Qty";
		if (judge === "Amount") {
			return Number(row.amount_achievement_percent || 0);
		}
		return Number(row.qty_achievement_percent || 0);
	}

	label(row, is_item) {
		const raw = is_item ? row.item_name || row.dimension : row.dimension;
		const text = String(raw || "");
		return text.length > 22 ? `${text.slice(0, 20)}…` : text;
	}

	render() {
		const t = this.data.totals || {};
		const g_ok = t.item_groups_achieved || 0;
		const g_miss = t.item_groups_missed || 0;
		const i_ok = t.items_achieved || 0;
		const i_miss = t.items_missed || 0;
		const set_stat = (id, value) => {
			const el = this.wrapper.querySelector(id);
			if (el) el.textContent = this.n(value);
		};
		set_stat("#ag_stat_g_ok", g_ok);
		set_stat("#ag_stat_g_miss", g_miss);
		set_stat("#ag_stat_i_ok", i_ok);
		set_stat("#ag_stat_i_miss", i_miss);

		this.pie("#ag-pie-groups", [__("Achieved"), __("Not Achieved")], [g_ok, g_miss]);
		this.pie("#ag-pie-items", [__("Achieved"), __("Not Achieved")], [i_ok, i_miss]);
		this.percent("#ag-pct-groups", [__("Achieved"), __("Not Achieved")], [g_ok, g_miss]);
		this.percent("#ag-pct-items", [__("Achieved"), __("Not Achieved")], [i_ok, i_miss]);

		const groups = []
			.concat(this.data.item_groups_achieved || [], this.data.item_groups_missed || [])
			.sort((a, b) => this.score(b) - this.score(a))
			.slice(0, 14);
		const items = []
			.concat(this.data.items_achieved || [], this.data.items_missed || [])
			.sort((a, b) => this.score(b) - this.score(a))
			.slice(0, 14);

		this.bar(
			"#ag-bar-groups",
			groups.map((r) => this.label(r, false)),
			[{ name: __("Achievement %"), values: groups.map((r) => this.score(r)) }],
			["#2490ef"],
			1
		);
		this.bar(
			"#ag-bar-items",
			items.map((r) => this.label(r, true)),
			[{ name: __("Achievement %"), values: items.map((r) => this.score(r)) }],
			["#2490ef"],
			1
		);
		this.bar(
			"#ag-vs-groups",
			groups.map((r) => this.label(r, false)),
			[
				{ name: __("Target Amt"), values: groups.map((r) => Number(r.target_amount || 0)) },
				{ name: __("Actual Amt"), values: groups.map((r) => Number(r.actual_amount || 0)) },
			],
			["#98d1ff", "#16833b"]
		);
		this.bar(
			"#ag-vs-items",
			items.map((r) => this.label(r, true)),
			[
				{ name: __("Target Amt"), values: items.map((r) => Number(r.target_amount || 0)) },
				{ name: __("Actual Amt"), values: items.map((r) => Number(r.actual_amount || 0)) },
			],
			["#98d1ff", "#16833b"]
		);
	}

	clear_chart(selector) {
		const host = this.wrapper.querySelector(selector);
		host.innerHTML = "";
		if (this.charts[selector] && this.charts[selector].destroy) {
			try {
				this.charts[selector].destroy();
			} catch (e) {
				/* ignore */
			}
		}
		return host;
	}

	empty(host) {
		host.innerHTML = `<div class="sp-empty">${__("No chart data")}</div>`;
	}

	pie(selector, labels, values) {
		const host = this.clear_chart(selector);
		if (!values.some((v) => Number(v) > 0) || typeof frappe.Chart === "undefined") {
			this.empty(host);
			return;
		}
		this.charts[selector] = new frappe.Chart(
			host,
			Object.assign(
				{
					data: { labels, datasets: [{ values }] },
					type: "donut",
					height: 240,
					colors: ["#16833b", "#c0392b"],
				},
				sales_performance.chart_number_opts(0)
			)
		);
		if (sales_performance.finish_chart) {
			sales_performance.finish_chart(this.charts[selector]);
		}
	}

	percent(selector, labels, values) {
		const host = this.clear_chart(selector);
		if (!values.some((v) => Number(v) > 0) || typeof frappe.Chart === "undefined") {
			this.empty(host);
			return;
		}
		this.charts[selector] = new frappe.Chart(
			host,
			Object.assign(
				{
					data: { labels, datasets: [{ values }] },
					type: "percentage",
					height: 80,
					colors: ["#16833b", "#c0392b"],
				},
				sales_performance.chart_number_opts(1)
			)
		);
		if (sales_performance.finish_chart) {
			sales_performance.finish_chart(this.charts[selector]);
		}
	}

	bar(selector, labels, datasets, colors, precision = 0) {
		const host = this.clear_chart(selector);
		if (!labels.length || typeof frappe.Chart === "undefined") {
			this.empty(host);
			return;
		}
		this.charts[selector] = new frappe.Chart(
			host,
			Object.assign(
				{
					data: { labels, datasets },
					type: "bar",
					height: 280,
					colors: colors || ["#2490ef"],
				},
				sales_performance.chart_number_opts(precision)
			)
		);
		if (sales_performance.finish_chart) {
			sales_performance.finish_chart(this.charts[selector]);
		}
	}
}
