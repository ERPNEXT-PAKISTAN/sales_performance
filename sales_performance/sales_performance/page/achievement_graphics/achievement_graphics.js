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
	wrapper.achievement_graphics = new AchievementGraphics(wrapper, page);
};

class AchievementGraphics {
	constructor(wrapper, page) {
		this.wrapper = wrapper;
		this.page = page;
		this.data = {};
		this.charts = {};
		this.loading_defaults = true;
		this.make_filters();
		this.init_tables();
        this.page.add_inner_button(__("Save View"), () => sales_performance.save_view("achievement_graphics", this.filters));
        this.page.add_inner_button(__("Load View"), () => sales_performance.restore_view("achievement_graphics", this.filters));
		this.bind();
		Promise.all([this.ready_filters(), this.load_chart_library()]).then(() => {
			this.loading_defaults = false;
			this.refresh();
		}).catch(() => {
			this.loading_defaults = false;
			this.set_error(__("Could not load dashboard filters. Reload the page to retry."));
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
			this.set_control_value(this.filters.ranking, "Largest target gap"),
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
			["ranking", "Select", __("Show"), "Largest target gap\nLowest achievement\nHighest achievement", "Largest target gap"],
			["customer_group", "Select", __("Customer Group"), "\nMarket", "Market"],
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
		this.wrapper.querySelector("#ag-filters-toggle").addEventListener("click", (event) => {
			const panel = this.wrapper.querySelector("#ag-filters-panel");
			panel.hidden = !panel.hidden;
			event.currentTarget.setAttribute("aria-expanded", String(!panel.hidden));
		});
		this.wrapper.querySelectorAll(".ag-tab").forEach((button) => button.addEventListener("click", () => this.show_tab(button.dataset.tab)));
		this.wrapper.querySelectorAll("[data-summary]").forEach((button) => button.addEventListener("click", () => {
			const kind = button.dataset.summary.startsWith("item_groups") ? "groups" : "items";
			const status = button.dataset.summary.endsWith("_achieved") ? "achieved" : "missed";
			this.table_state[kind].status = status;
			this.table_state[kind].search = "";
			this.table_state[kind].page = 1;
			this.wrapper.querySelector("#ag-panel-" + kind + " [data-status]").value = status;
			this.wrapper.querySelector("#ag-panel-" + kind + " [data-search]").value = "";
			this.render_table(kind);
			this.show_tab(kind);
		}));
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.wrapper.querySelector("#ag-refresh").addEventListener("click", () => this.refresh());
		this.wrapper.querySelector("#ag-reset").addEventListener("click", () => this.reset_filters());
		this.wrapper.querySelector("#ag-tables").addEventListener("click", () => {
			frappe.route_options = Object.fromEntries(Object.entries(this.filters).map(([k,f])=>[k,f.get_value()]));
			frappe.set_route("target-achievement");
		});
	}

	reset_filters() {
		this.set_control_value(this.filters.company, this.default_company());
		this.set_control_value(this.filters.period, "Annual");
		this.set_control_value(this.filters.judge, "Qty");
		this.set_control_value(this.filters.ranking, "Largest target gap");
		["month", "quarter", "sales_person", "territory", "item_group", "customer_group", "item"].forEach((name) => {
			this.set_control_value(this.filters[name], name === "customer_group" ? "Market" : "");
		});
		this.set_fiscal_year_default().then(() => {
			this.period_visibility();
			this.refresh();
		});
	}

	set_loading(on) {
		const el = this.wrapper.querySelector("#ag-loading");
		if (el) el.hidden = !on;
		this.wrapper.querySelector("#ag-refresh").disabled = on;
		this.wrapper.querySelector("#ag_dashboard_root").setAttribute("aria-busy", String(on));
	}

	set_error(msg) {
		const el = this.wrapper.querySelector("#ag-error");
		if (!el) return;
		el.hidden = !msg;
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

	async refresh() {
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
		await this.load_chart_library();
		if (request_id !== this.request_id) return;
		frappe.call({
			method: "sales_performance.sales_performance.page.achievement_graphics.achievement_graphics.get_graphics_data",
			args,
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
				if (request_id !== this.request_id) return;
				this.set_error(__("Failed to load graphics"));
				this.page.set_indicator(__("Failed"), "red");
			},
			always: () => { if (request_id === this.request_id) this.set_loading(false); },
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
		return text;
	}

	rank(a, b) {
		const mode = this.filters.ranking.get_value();
		if (mode === "Highest achievement") return this.score(b) - this.score(a);
		if (mode === "Lowest achievement") return this.score(a) - this.score(b);
		const metric = this.filters.judge.get_value() === "Amount" ? "amount" : "qty";
		return Math.max(0, b["target_" + metric] - b["actual_" + metric]) - Math.max(0, a["target_" + metric] - a["actual_" + metric]);
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

		this.table_rows = {};
		[["groups", "item_groups"], ["items", "items"]].forEach(([kind, key]) => {
			this.table_rows[kind] = [
				...(this.data[key + "_achieved"] || []).map((row) => ({ ...row, _status: "achieved" })),
				...(this.data[key + "_missed"] || []).map((row) => ({ ...row, _status: "missed" }))
			].sort((a, b) => this.rank(a, b));
			this.table_state[kind].page = 1;
			this.render_table(kind);
			this.wrapper.querySelector(kind === "groups" ? "#ag-group-count" : "#ag-item-count").textContent = this.n(this.table_rows[kind].length);
			["achieved", "missed"].forEach((status) => {
				const count = Number(t[key + "_" + status] || 0);
				const total = this.table_rows[kind].length;
				this.wrapper.querySelector('[data-share="' + key + "_" + status + '"]').textContent = total ? __("{0}% of {1}", [this.n(count / total * 100), this.n(total)]) : __("No data");
			});
		});
		this.wrapper.querySelectorAll(".ag-ranking-note").forEach((el) => { el.textContent = __("Up to 30") + " · " + __(this.filters.ranking.get_value() || "Largest target gap"); });

		this.pie("#ag-pie-groups", [__("Achieved"), __("Not Achieved")], [g_ok, g_miss]);
		this.pie("#ag-pie-items", [__("Achieved"), __("Not Achieved")], [i_ok, i_miss]);
		this.percent("#ag-pct-groups", [__("Achieved"), __("Not Achieved")], [g_ok, g_miss]);
		this.percent("#ag-pct-items", [__("Achieved"), __("Not Achieved")], [i_ok, i_miss]);

		const groups = []
			.concat(this.data.item_groups_achieved || [], this.data.item_groups_missed || [])
			.sort((a, b) => this.rank(a, b))
			.slice(0, 30);
		this.group_chart_rows = groups;
		const items = []
			.concat(this.data.items_achieved || [], this.data.items_missed || [])
			.sort((a, b) => this.rank(a, b))
			.slice(0, 30);

		this.item_chart_rows = items;
		this.bar(
			"#ag-bar-groups",
			groups.map((r) => this.label(r, false)),
			[{ name: __("Achievement %"), values: groups.map((r) => this.score(r)) }],
			["rgba(41,121,255,.75)"],
			1
		);
		this.bar(
			"#ag-bar-items",
			items.map((r) => this.label(r, true)),
			[{ name: __("Achievement %"), values: items.map((r) => this.score(r)) }],
			["rgba(0,150,136,.72)"],
			1
		);
		this.bar(
			"#ag-vs-groups",
			groups.map((r) => this.label(r, false)),
			[
				{ name: __("Target Amt"), values: groups.map((r) => Number(r.target_amount || 0)) },
				{ name: __("Actual Amt"), values: groups.map((r) => Number(r.actual_amount || 0)) },
			],
			["rgba(41,121,255,.75)", "rgba(0,150,136,.72)"]
		);
		this.bar(
			"#ag-vs-items",
			items.map((r) => this.label(r, true)),
			[
				{ name: __("Target Amt"), values: items.map((r) => Number(r.target_amount || 0)) },
				{ name: __("Actual Amt"), values: items.map((r) => Number(r.actual_amount || 0)) },
			],
			["rgba(41,121,255,.75)", "rgba(0,150,136,.72)"]
		);
	}

	load_chart_library() {
		if (window.Chart) return Promise.resolve();
		if (AchievementGraphics.chart_loading) return AchievementGraphics.chart_loading;
		AchievementGraphics.chart_loading = new Promise((resolve, reject) => {
			const script = document.createElement("script");
			const timeout = setTimeout(() => { script.remove(); reject(new Error("Chart library timed out")); }, 15000);
			script.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js";
			script.onload = () => { clearTimeout(timeout); resolve(); };
			script.onerror = () => { clearTimeout(timeout); script.remove(); reject(new Error("Chart library unavailable")); };
			document.head.appendChild(script);
		}).catch(() => {
			// Keep indicators, filters and tables usable if the chart CDN cannot be reached.
			AchievementGraphics.chart_loading = null;
		});
		return AchievementGraphics.chart_loading;
	}

	show_tab(tab) {
		this.active_tab = tab;
		this.wrapper.querySelectorAll(".ag-tab").forEach((button) => {
			const active = button.dataset.tab === tab;
			button.classList.toggle("active", active);
			button.setAttribute("aria-pressed", String(active));
		});
		["overview", "groups", "items"].forEach((name) => {
			this.wrapper.querySelector("#ag-panel-" + name).hidden = name !== tab;
		});
		if (tab === "overview") requestAnimationFrame(() => Object.values(this.charts).forEach((chart) => chart.resize()));
	}

	init_tables() {
		this.table_state = { groups: { page: 1, search: "", status: "" }, items: { page: 1, search: "", status: "" } };
		const esc = (value) => frappe.utils.escape_html(String(value));
		["groups", "items"].forEach((kind) => {
			const panel = this.wrapper.querySelector("#ag-panel-" + kind);
			const title = kind === "items" ? __("Items") : __("Item Groups");
			panel.innerHTML = `<article class="ag-card">
				<div class="ag-card-head"><h3>${esc(title)}</h3><span class="ag-card-period">${esc(__("Selected period"))}</span></div>
				<div class="ag-table-tools"><input type="search" data-search="${kind}" placeholder="${esc(__("Search by name or code"))}" aria-label="${esc(__("Search") + " " + title)}">
				<select data-status="${kind}" aria-label="${esc(__("Achievement status"))}"><option value="">${esc(__("All statuses"))}</option><option value="achieved">${esc(__("Achieved"))}</option><option value="missed">${esc(__("Not Achieved"))}</option></select></div>
				<div class="ag-table-wrap" tabindex="0" role="region" aria-label="${esc(title)}"><table class="ag-table">
				<thead><tr><th scope="col">${esc(title)}</th><th scope="col">${esc(__("Status"))}</th>${["Target Qty", "Actual Qty", "Qty %", "Target Amount", "Actual Amount", "Amount %"].map((label) => `<th scope="col" class="ag-number">${esc(__(label))}</th>`).join("")}</tr></thead>
				<tbody></tbody></table></div><div class="ag-pagination"><span class="ag-page-info"></span><button type="button" class="ag-btn ag-btn-muted" data-page="-1">${esc(__("Previous"))}</button><button type="button" class="ag-btn ag-btn-muted" data-page="1">${esc(__("Next"))}</button></div></article>`;
			panel.querySelector("[data-search]").addEventListener("input", (event) => {
				this.table_state[kind].search = event.target.value;
				this.table_state[kind].page = 1;
				this.render_table(kind);
			});
			panel.querySelector("[data-status]").addEventListener("change", (event) => {
				this.table_state[kind].status = event.target.value;
				this.table_state[kind].page = 1;
				this.render_table(kind);
			});
			panel.addEventListener("click", (event) => {
				const pager = event.target.closest("[data-page]");
				if (pager) { this.table_state[kind].page += Number(pager.dataset.page); this.render_table(kind); }
				const link = event.target.closest("[data-row]");
				if (link) this.open_report(this.table_rows[kind][Number(link.dataset.row)], kind === "items");
			});
		});
	}

	render_table(kind) {
		const panel = this.wrapper.querySelector("#ag-panel-" + kind);
		const state = this.table_state[kind];
		const rows = (this.table_rows?.[kind] || []).map((row, index) => ({ row, index })).filter(({row}) =>
			(!state.status || state.status === row._status) &&
			(!state.search || `${row.dimension || ""} ${row.item_name || ""}`.toLowerCase().includes(state.search.toLowerCase()))
		);
		const page_size = kind === "items" ? 100 : Math.max(1, rows.length);
		const pages = Math.max(1, Math.ceil(rows.length / page_size));
		state.page = Math.min(pages, Math.max(1, state.page));
		const start = (state.page - 1) * page_size;
		const esc = (value) => frappe.utils.escape_html(String(value ?? ""));
		panel.querySelector("tbody").innerHTML = rows.slice(start, start + page_size).map(({row, index}) => {
			const name = kind === "items" ? row.item_name || row.dimension : row.dimension;
			const percent = (value) => value == null ? "—" : esc(this.n(value)) + "%";
			return `<tr><td><button type="button" class="ag-row-link" data-row="${index}">${esc(name)}</button>${name !== row.dimension ? `<span class="ag-row-sub">${esc(row.dimension)}</span>` : ""}</td>
				<td><span class="ag-badge ${row._status}">${esc(row._status === "achieved" ? __("Achieved") : __("Not Achieved"))}</span></td>
				<td class="ag-number">${esc(this.n(row.target_qty))}</td><td class="ag-number">${esc(this.n(row.actual_qty))}</td><td class="ag-number">${percent(row.qty_achievement_percent)}</td>
				<td class="ag-number">${esc(this.n(row.target_amount))}</td><td class="ag-number">${esc(this.n(row.actual_amount))}</td><td class="ag-number">${percent(row.amount_achievement_percent)}</td></tr>`;
		}).join("") || `<tr><td colspan="8"><div class="ag-empty">${esc(__("No matching achievement data"))}</div></td></tr>`;
		panel.querySelector(".ag-page-info").textContent = rows.length ? __("Showing {0}–{1} of {2}", [start + 1, Math.min(start + page_size, rows.length), rows.length]) : __("0 rows");
		panel.querySelectorAll("[data-page]").forEach((button) => { button.hidden = kind === "groups"; });
		panel.querySelector('[data-page="-1"]').disabled = state.page <= 1;
		panel.querySelector('[data-page="1"]').disabled = state.page >= pages;
	}

	open_report(row, item) {
		if (!row) return;
		frappe.route_options = Object.fromEntries(Object.entries(this.filters).filter(([key]) => key !== "ranking").map(([key, field]) => [key, field.get_value()]));
		frappe.route_options[item ? "item" : "item_group"] = row.dimension;
		frappe.set_route("query-report", "Sales Target Achievement");
	}

	clear_chart(selector) {
		if (this.charts[selector]) {
			this.charts[selector].destroy();
			delete this.charts[selector];
		}
		const host = this.wrapper.querySelector(selector);
		host.replaceChildren();
		return host;
	}

	empty(host, message = __("No chart data")) {
		const element = document.createElement("div");
		element.className = "ag-empty";
		element.textContent = message;
		host.appendChild(element);
	}

	chart_canvas(host, label, min_width = 0) {
		const canvas = document.createElement("canvas");
		canvas.setAttribute("role", "img");
		canvas.setAttribute("aria-label", label);
		if (min_width) {
			const surface = document.createElement("div");
			surface.className = "ag-canvas-surface";
			surface.style.minWidth = min_width + "px";
			surface.appendChild(canvas);
			host.appendChild(surface);
		} else {
			host.appendChild(canvas);
		}
		return canvas;
	}

	chart_options() {
		const root = this.wrapper.querySelector("#ag_dashboard_root");
		const styles = getComputedStyle(root);
		const color = styles.getPropertyValue("--ag-muted").trim();
		return {
			responsive: true, maintainAspectRatio: false,
			animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 250 },
			color,
			font: { family: 'Inter, "Segoe UI", sans-serif' },
			plugins: {
				datalabels: { display: false },
				legend: { position: "bottom", labels: { color, usePointStyle: true, boxWidth: 8, padding: 18, font: { size: 11 } } },
				tooltip: { backgroundColor: "#1a1e2e", padding: 12, cornerRadius: 7 }
			}
		};
	}

	pie(selector, labels, values) {
		const host = this.clear_chart(selector);
		if (!values.some((v) => Number(v) > 0)) return this.empty(host);
		if (!window.Chart) return this.empty(host, __("Charts could not load. Use the table tabs or refresh to retry."));
		const total = values.reduce((sum, value) => sum + Number(value), 0);
		const options = this.chart_options();
		options.plugins.tooltip.callbacks = { label: (ctx) => ` ${ctx.label}: ${this.n(ctx.raw)} (${this.n(ctx.raw / total * 100)}%)` };
		this.charts[selector] = new Chart(this.chart_canvas(host, labels.map((label, index) => label + ": " + this.n(values[index])).join(", ")), {
			type: "pie",
			data: { labels, datasets: [{ data: values, backgroundColor: ["#26a69a", "#ffa726"], borderWidth: 2, borderColor: "#fff" }] },
			options,
			plugins: [{
				id: "achievementPieLabels",
				afterDatasetsDraw: (chart) => {
					const ctx = chart.ctx;
					ctx.save(); ctx.fillStyle = "#fff"; ctx.font = "700 12px Inter, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
					chart.getDatasetMeta(0).data.forEach((arc, index) => {
						const percent = values[index] / total * 100;
						if (percent < 5 || !chart.getDataVisibility(index)) return;
						const point = arc.tooltipPosition();
						ctx.fillText(this.n(percent) + "%", point.x, point.y);
					});
					ctx.restore();
				}
			}]
		});
	}

	percent(selector, labels, values) {
		const host = this.clear_chart(selector);
		const total = values.reduce((sum, value) => sum + Number(value), 0);
		const percent = total ? Number(values[0]) / total * 100 : 0;
		const esc = (value) => frappe.utils.escape_html(String(value));
		host.innerHTML = `<div class="ag-rate-label"><span>${esc(__("Hit rate"))}</span><strong>${total ? esc(this.n(percent)) + "%" : "—"}</strong></div>
			<div class="ag-rate-track" role="img" aria-label="${esc(__("{0} of {1} achieved", [this.n(values[0]), this.n(total)]))}"><span class="ag-rate-fill" style="width:${percent}%"></span></div>`;
	}

	bar(selector, labels, datasets, colors, precision = 0) {
		const host = this.clear_chart(selector);
		if (!labels.length) return this.empty(host);
		if (!window.Chart) return this.empty(host, __("Charts could not load. Use the table tabs or refresh to retry."));
		host.style.height = "620px";
		const grouped = datasets.length > 1;
		const is_item = selector.includes("items");
		const rows = is_item ? this.item_chart_rows : this.group_chart_rows;
		const options = this.chart_options();
		options.indexAxis = "x";
		options.layout = { padding: { top: grouped ? 96 : 24, right: 16, bottom: 20 } };
		options.plugins.legend.display = datasets.length > 1;
		// Each metric uses the same filled line and translucent bars as Selling Dashboard.
		options.plugins.legend.labels.filter = (entry, data) => data.datasets[entry.datasetIndex].type === "line";
		options.plugins.legend.onClick = (_event, entry, legend) => {
			const chart = legend.chart;
			const series = chart.data.datasets[entry.datasetIndex].achievementSeries;
			const visible = !chart.isDatasetVisible(entry.datasetIndex);
			chart.data.datasets.forEach((dataset, index) => {
				if (dataset.achievementSeries === series) chart.setDatasetVisibility(index, visible);
			});
			chart.update();
		};
		options.interaction = { mode: "index", intersect: false };
		options.plugins.tooltip.filter = (context) => context.dataset.type === "line";
		options.plugins.tooltip.callbacks = {
			title: (items) => { const row = rows[items[0]?.dataIndex]; return row ? (row.item_name || row.dimension) : ""; },
			label: (ctx) => ` ${ctx.dataset.label}: ${this.n(ctx.raw)}${precision ? "%" : ""}`
		};
		options.scales = {
			x: {
				grid: { display: false },
				ticks: {
					color: options.color, font: { size: 11 }, autoSkip: false,
					minRotation: 45, maxRotation: 45, padding: 12,
					callback: function (value) {
						const name = String(this.getLabelForValue(value));
						return name.match(/.{1,32}(?:\s|$)|.{1,32}/g) || name;
					}
				},
				afterFit: (scale) => { scale.height = Math.max(scale.height, 180); },
				border: { display: false }
			},
			y: { beginAtZero: true, grid: { color: "rgba(128,128,128,.12)" }, ticks: { color: options.color, font: { size: 10 }, maxTicksLimit: 5, callback: (v) => this.n(v) + (precision ? "%" : "") }, border: { display: false } }
		};
		options.onClick = (_event, elements) => { if (elements.length) this.open_report(rows[elements[0].index], is_item); };
		options.onHover = (event, elements) => { if (event.native?.target) event.native.target.style.cursor = elements.length ? "pointer" : "default"; };
		this.charts[selector] = new Chart(this.chart_canvas(host, host.closest(".ag-card").querySelector("h3").textContent + ". " + __("Details available in the table tabs."), Math.max(640, labels.length * (grouped ? 56 : 44))), {
			type: "bar",
			data: { labels, datasets: datasets.flatMap((dataset, index) => {
				const color = colors?.[index] || "rgba(41,121,255,1)";
				const with_alpha = (alpha) => color.replace(/rgba\(([^,]+),([^,]+),([^,]+),[^)]+\)/, "rgba($1,$2,$3," + alpha + ")");
				const shared = { label: dataset.name, data: dataset.values, achievementSeries: index };
				return [
					{ ...shared, type: "line", borderColor: with_alpha(1), backgroundColor: with_alpha(.18),
						tension: .35, fill: true, borderWidth: 2, pointRadius: 3, order: 1 },
					{ ...shared, type: "bar", backgroundColor: with_alpha(.55),
						borderRadius: 6, borderSkipped: false, order: 2,
						categoryPercentage: .8, barPercentage: grouped ? 1 : .9 }
				];
			}) },
			options,
			plugins: [{
				id: "achievementBarLabels",
				afterDatasetsDraw: (chart) => {
					const ctx = chart.ctx;
					ctx.save();
					ctx.fillStyle = getComputedStyle(this.wrapper.querySelector("#ag_dashboard_root")).getPropertyValue("--ag-text").trim();
					ctx.font = "600 10px Inter, sans-serif";
					ctx.textAlign = "center";
					ctx.textBaseline = "top";
					const placed = [];
					chart.data.datasets.forEach((dataset, index) => {
						if (dataset.type !== (grouped ? "bar" : "line") || !chart.isDatasetVisible(index)) return;
						chart.getDatasetMeta(index).data.forEach((point, row) => {
							const label = this.n(dataset.data[row]) + (precision ? "%" : "");
							if (grouped) {
								// Anchor each vertical value to its own bar, not the shared category center.
								const positive = Number(dataset.data[row]) >= 0;
								ctx.save();
								ctx.translate(point.x, point.y + (positive ? -5 : 5));
								ctx.rotate(positive ? -Math.PI / 2 : Math.PI / 2);
								ctx.textAlign = "left";
								ctx.textBaseline = "middle";
								ctx.fillText(label, 0, 0);
								ctx.restore();
								return;
							}
							const width = ctx.measureText(label).width;
							const x = Math.max(width / 2 + 4, Math.min(chart.width - width / 2 - 4, point.x));
							const y = point.y + (dataset.achievementSeries % 2 ? 6 : -18);
							const box = { left: x - width / 2, right: x + width / 2, top: y, bottom: y + 12 };
							// Keep labels horizontal like the reference; crowded values remain in tooltips.
							if (box.top < 0 || box.bottom > chart.chartArea.bottom ||
								placed.some((other) => box.left < other.right + 4 && box.right > other.left - 4 &&
									box.top < other.bottom + 2 && box.bottom > other.top - 2)) return;
							placed.push(box);
							ctx.fillText(label, x, y);
						});
					});
					ctx.restore();
				}
			}]
		});
	}

}
