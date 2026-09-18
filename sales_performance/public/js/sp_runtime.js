(() => {
	frappe.provide("sales_performance");
	if (sales_performance.__runtime_ready) {
		return;
	}
	sales_performance.save_view = (key, filters) => {
		localStorage.setItem(`sp-view:${frappe.session.user}:${key}`, JSON.stringify(Object.fromEntries(Object.entries(filters).map(([name, field]) => [name, field.get_value()]))));
		frappe.show_alert({message: __("View saved"), indicator: "green"});
	};
	sales_performance.restore_view = async (key, filters) => {
		let values;
		try { values = JSON.parse(localStorage.getItem(`sp-view:${frappe.session.user}:${key}`) || "{}"); } catch (e) { values = {}; }
		for (const [name, value] of Object.entries(values)) if (filters[name]) await filters[name].set_value(value);
	};
	sales_performance.__runtime_ready = true;
	sales_performance.__number_display_ready = true;

	const QTY = 0;
	const AMT = 0;
	const PCT = 0;

	sales_performance.currency = () =>
		frappe.defaults.get_user_default("currency") ||
		(frappe.boot.sysdefaults && frappe.boot.sysdefaults.currency) ||
		"PKR";

	sales_performance.format_qty = (value) => format_number(value || 0, null, QTY);
	sales_performance.format_amount = (value, currency) =>
		format_currency(value || 0, currency || sales_performance.currency(), AMT);
	sales_performance.format_percent = (value) => format_number(value || 0, null, PCT);

	sales_performance.stampNow = () =>
		new Date().toLocaleString(undefined, {
			year: "numeric",
			month: "short",
			day: "2-digit",
			hour: "2-digit",
			minute: "2-digit",
			second: "2-digit",
		});

	sales_performance.makePageFullWidth = (wrapperOrElement) => {
		let node = wrapperOrElement;
		if (node && node.jquery) node = node[0];
		if (!node) return;
		const page = node.closest ? node.closest(".page-container") : null;
		const main =
			(node.querySelector && node.querySelector(".layout-main-section")) ||
			(node.closest && node.closest(".layout-main-section")) ||
			document.querySelector(".layout-main-section");
		const section =
			(node.querySelector && node.querySelector(".page-body")) ||
			(node.closest && node.closest(".page-body"));
		if (page) page.classList.add("sp-full-width-page");
		if (main) {
			main.style.maxWidth = "100%";
			main.style.width = "100%";
			main.style.flex = "1 1 auto";
		}
		if (section) {
			section.style.maxWidth = "100%";
			section.style.width = "100%";
		}
	};

	sales_performance.set_filter_visible = (control, show) => {
		if (!control) return;
		control.df.hidden = !show;
		const wrap = control.$wrapper && control.$wrapper[0];
		if (wrap) {
			wrap.classList.toggle("hide-control", !show);
		}
		const cell = wrap && wrap.closest(".sp-filter-item");
		if (cell) {
			cell.classList.toggle("is-hidden", !show);
		}
	};

	sales_performance.full_number = (value, precision = 0) =>
		format_number(value || 0, null, 0);

	sales_performance.chart_number_opts = (precision = 0) => ({
		valuesOverPoints: 1,
		axisOptions: {
			shortenYAxisNumbers: 0,
		},
		tooltipOptions: {
			formatTooltipY: (value) => sales_performance.full_number(value, precision),
		},
	});

	sales_performance.finish_chart = (chart) => {
		if (!chart || !chart.parent) {
			return;
		}
		const apply = () => {
			const data = chart.data || chart.realData;
			if (!data || !data.datasets) {
				return;
			}
			const values = [];
			data.datasets.forEach((ds) => {
				(ds.values || []).forEach((v) => values.push(v));
			});
			chart.parent.querySelectorAll("text.data-point-value").forEach((el, i) => {
				if (values[i] === undefined || values[i] === null) {
					return;
				}
				const next = sales_performance.full_number(values[i], 0);
				if (el.textContent !== next) {
					el.textContent = next;
				}
			});
		};
		requestAnimationFrame(apply);
		setTimeout(apply, 200);
	};

	sales_performance.explicit_precision = (df) => {
		if (!df || df.precision === undefined || df.precision === null || df.precision === "") {
			return null;
		}
		return cint(df.precision);
	};

	const orig_get_precision = frappe.meta.get_field_precision;
	frappe.meta.get_field_precision = function (df, doc) {
		const set = sales_performance.explicit_precision(df);
		if (set !== null) {
			return set;
		}
		return orig_get_precision.call(this, df, doc);
	};

	if (frappe.ui.form.ControlFloat) {
		const orig_float_precision = frappe.ui.form.ControlFloat.prototype.get_precision;
		frappe.ui.form.ControlFloat.prototype.get_precision = function () {
			const set = sales_performance.explicit_precision(this.df);
			if (set !== null) {
				return set;
			}
			return orig_float_precision.call(this);
		};
	}

	if (frappe.ui.form.ControlCurrency) {
		const orig_cur_precision = frappe.ui.form.ControlCurrency.prototype.get_precision;
		frappe.ui.form.ControlCurrency.prototype.get_precision = function () {
			const set = sales_performance.explicit_precision(this.df);
			if (set !== null) {
				return set;
			}
			return orig_cur_precision.call(this);
		};
	}

	const orig_float = frappe.form.formatters.Float;
	frappe.form.formatters.Float = function (value, docfield, options, doc) {
		const set = sales_performance.explicit_precision(docfield);
		if (set !== null) {
			if (value == null || value === "") {
				return "";
			}
			return frappe.form.formatters._right(format_number(value, null, set), options);
		}
		return orig_float(value, docfield, options, doc);
	};

	const orig_currency = frappe.form.formatters.Currency;
	frappe.form.formatters.Currency = function (value, docfield, options, doc) {
		const set = sales_performance.explicit_precision(docfield);
		if (set !== null) {
			if (value === null || value === undefined || value === "") {
				return "";
			}
			const currency = frappe.meta.get_field_currency(docfield, doc);
			value = format_currency(value, currency, set);
			if (options && options.only_value) {
				return value;
			}
			return frappe.form.formatters._right(value, options);
		}
		return orig_currency(value, docfield, options, doc);
	};

	sales_performance.report_formatter = (value, row, column, data, default_formatter) => {
		const raw = data && column && column.fieldname in data ? data[column.fieldname] : value;
		if (column.fieldtype === "Currency") {
			value = sales_performance.format_amount(value);
		} else if (column.fieldtype === "Float") {
			value = sales_performance.format_qty(value);
		} else if (column.fieldtype === "Percent") {
			value = value == null || value === "" ? "" : `${sales_performance.format_percent(value)}%`;
		} else {
			value = default_formatter(value, row, column, data);
		}
		return sales_performance.paint(value, column && column.fieldname, raw);
	};

	sales_performance.indicator_class = (fieldname, value) => {
		if (value == null || value === "" || !fieldname) {
			return "";
		}
		const name = String(fieldname);
		const n = Number(value);
		if (Number.isNaN(n)) {
			return "";
		}
		if (name.includes("achievement_percent")) {
			return n >= 100 ? "sp-ok" : "sp-bad";
		}
		if (name.includes("variance") || name.endsWith("_delta")) {
			if (n > 0) return "sp-ok";
			if (n < 0) return "sp-bad";
			return "";
		}
		if (name.startsWith("remaining_")) {
			return n > 0 ? "sp-bad" : "sp-ok";
		}
		if (
			name === "incentive_amount" ||
			name === "incentive_on_amount" ||
			name === "incentive_on_qty" ||
			name === "incentive_qty"
		) {
			return n > 0 ? "sp-ok" : "";
		}
		return "";
	};

	sales_performance.paint = (html, fieldname, value) => {
		const klass = sales_performance.indicator_class(fieldname, value);
		if (!klass || html == null || html === "") {
			return html;
		}
		if (String(html).indexOf("sp-ok") >= 0 || String(html).indexOf("sp-bad") >= 0) {
			return html;
		}
		return `<span class="${klass}">${html}</span>`;
	};

	const decorate = (orig) =>
		function (value, docfield, options, doc) {
			const formatted = orig(value, docfield, options, doc);
			const fieldname = docfield && docfield.fieldname;
			return sales_performance.paint(formatted, fieldname, value);
		};

	frappe.form.formatters.Float = decorate(frappe.form.formatters.Float);
	frappe.form.formatters.Currency = decorate(frappe.form.formatters.Currency);
	frappe.form.formatters.Percent = decorate(frappe.form.formatters.Percent);
})();
