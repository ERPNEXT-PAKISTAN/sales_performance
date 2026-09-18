frappe.pages["monthly-incentives"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: __("Monthly Incentives"), single_column: true});
    new MonthlyIncentives(page);
};

class MonthlyIncentives {
    constructor(page) {
        this.page = page;
        this.expanded = new Set();
        this.sequence = 0;
        this.ready = false;
        this.filters = {};
        this.page.add_inner_button(__("Save View"), () => sales_performance.save_view("monthly_incentives", this.filters));
        this.page.add_inner_button(__("Load View"), () => sales_performance.restore_view("monthly_incentives", this.filters));
        this.body = $('<div class="monthly-incentives"><div class="mi-filters"></div><div class="mi-results"></div></div>').appendTo(page.body);
        const host = this.body.find(".mi-filters");
        for (const [fieldname, label, fieldtype, options, value, reqd] of [
            ["company", "Company", "Link", "Company", "", 1],
            ["fiscal_year", "Fiscal Year", "Link", "Fiscal Year", "", 1],
            ["sales_person", "Sales Person", "Link", "Sales Person"],
            ["item_group", "Item Group", "Link", "Item Group"],
            ["customer_group", "Customer Group", "Link", "Customer Group", "Market"],
            ["territory", "Territory", "Link", "Territory"],
            ["item", "Item", "Link", "Item"],
            ["incentive_status", "Incentive Achievement", "Select", "All\nAchieved\nNot Achieved", "All"],
            ["pay_on", "Incentive On", "Select", "Scheme Default\nQty\nAmount", "Scheme Default"],
            ["from_date", "From Date", "Date"],
            ["to_date", "To Date", "Date"],
        ]) {
            this.filters[fieldname] = frappe.ui.form.make_control({
                parent: $('<div class="mi-filter"></div>').appendTo(host), render_input: true,
                df: {fieldname, label: __(label), fieldtype, options, default: value, reqd,
                    change: () => {
                        if (!this.ready) return;
                        clearTimeout(this.filter_timer);
                        this.filter_timer = setTimeout(() => this.refresh(), 200);
                    }},
            });
        }
        this.results = this.body.find(".mi-results");
        page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
        page.add_inner_button(__("Expand All"), () => {
            (this.data?.groups || []).forEach((g) => this.expanded.add(g.sales_person));
            this.render();
        });
        page.add_inner_button(__("Explain Incentives"), () => this.explain());
        page.add_inner_button(__("Collapse All"), () => { this.expanded.clear(); this.render(); });
        this.body.on("click", "button[data-group]", (event) => {
            const index = Number(event.currentTarget.dataset.group);
            const person = this.data.groups[index].sales_person;
            this.expanded.has(person) ? this.expanded.delete(person) : this.expanded.add(person);
            this.render();
            this.body.find(`button[data-group="${index}"]`).trigger("focus");
        });
        this.body.on("click", "[data-detail-month]", (event) => {
            const el = event.currentTarget;
            const group = this.data.groups[Number(el.dataset.personIndex)];
            const item = group && el.dataset.itemIndex !== undefined ? group.items[Number(el.dataset.itemIndex)] : null;
            this.explain(Number(el.dataset.detailMonth), group?.sales_person, item);
        });
        this.set_defaults();
    }

    async set_defaults() {
        try {
            await Promise.all([
                this.filters.customer_group.set_value("Market"),
                this.filters.incentive_status.set_value("All"),
                this.filters.pay_on.set_value("Scheme Default"),
            ]);
            const defaults = frappe.boot.sysdefaults || {};
            await this.filters.company.set_value(frappe.defaults.get_user_default("Company") || defaults.company || "");
            let year = frappe.defaults.get_user_default("fiscal_year") || defaults.fiscal_year;
            if (!year) {
                const today = frappe.datetime.get_today();
                const years = await frappe.db.get_list("Fiscal Year", {
                    fields: ["name"], filters: {disabled: 0, year_start_date: ["<=", today], year_end_date: [">=", today]},
                    limit: 1, order_by: "year_start_date desc",
                });
                year = years[0]?.name;
            }
            await this.filters.fiscal_year.set_value(year || "");
        } catch (error) {
            // Leave filters editable if a default cannot be resolved.
        } finally {
            this.ready = true;
            this.refresh();
        }
    }

    async refresh() {
        const sequence = ++this.sequence;
        const args = Object.fromEntries(Object.entries(this.filters).map(([key, field]) => [key, field.get_value()]));
        this.data = null;
        if (!args.company || !args.fiscal_year) {
            this.message(__("Select Company and Fiscal Year to view monthly incentives."));
            return;
        }
        this.message(__("Loading monthly incentives…"));
        try {
            const response = await frappe.call({
                method: "sales_performance.sales_performance.page.monthly_incentives.monthly_incentives.get_data", args,
            });
            if (sequence !== this.sequence) return;
            this.data = response.message;
            this.page.set_indicator(this.data.provisional ? __("Provisional targets") : __("Approved targets"), this.data.provisional ? "orange" : "green");
            this.render();
        } catch (error) {
            if (sequence === this.sequence) this.message(__("Unable to load monthly incentives. Check the filters and try Refresh."));
        }
    }

    async explain(month = null, person = null, item = null) {
        const args = Object.fromEntries(Object.entries(this.filters).map(([key, field]) => [key, field.get_value()]));
        const response = await frappe.call({method: "sales_performance.sales_performance.page.monthly_incentives.monthly_incentives.get_data", args: {...args, include_details: 1, detail_month: month}});
        const data = response.message;
        const rows = (data.details || []).filter(row => (!person || row.sales_person === person) && (!item || ["item_code", "territory", "customer_group", "item_group"].every(key => (row[key] || "") === (item[key] || ""))) && (month || row.incentive_amount > 0));
        const dialog = new frappe.ui.Dialog({title: __("Incentive calculation details"), size: "extra-large", fields: [{fieldtype: "HTML", fieldname: "detail"}]});
        const metric = data.pay_on === "Qty" ? "qty" : "amount";
        dialog.fields_dict.detail.$wrapper.html(`<p>${__("Calculation for the selected cells and filters. Grouped schemes allocate the group payout across eligible items; zero values mean no allocated incentive.")}</p><div style="max-height:65vh;overflow:auto"><table class="table"><thead><tr>${["Sales Person","Item","Month","Target","Actual","Surplus","Rate %","Incentive","Plan"].map(h=>`<th>${__(h)}</th>`).join("")}</tr></thead><tbody>${rows.map(row=>`<tr>${[row.sales_person,row.item_code,row.period,format_number(row["target_"+metric],null,0),format_number(row["actual_"+metric],null,0),format_number(Math.max(0,row["actual_"+metric]-row["target_"+metric]),null,0),format_number(row.incentive_rate_percent,null,0),format_number(row.incentive_amount,null,0),row.planning].map(v=>`<td>${this.escape(v)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
        dialog.show();
    }

    escape(value) { return frappe.utils.escape_html(String(value ?? "")); }
    message(text) { this.results.html(`<div class="mi-message text-muted">${this.escape(text)}</div>`); }
    cells(values, total, personIndex = null, itemIndex = null) {
        return [...this.data.month_numbers.map((month) => values[month - 1]), total].map((value, index) => {
            const number = this.escape(format_number(value, null, 0));
            const month = this.data.month_numbers[index];
            const button = month ? `<button type="button" class="mi-value" data-detail-month="${month}" ${personIndex !== null ? `data-person-index="${personIndex}"` : ""} ${itemIndex !== null ? `data-item-index="${itemIndex}"` : ""} aria-label="${this.escape(__("Explain incentive"))}">${number}</button>` : number;
            return `<td class="mi-number ${index === this.data.month_numbers.length ? "mi-total" : ""}">${button}</td>`;
        }).join("");
    }

    render() {
        if (!this.data) return;
        const data = this.data;
        if (!data.groups.length) {
            this.message(__("No incentive data found for these filters. Check the sales target plans for this company and fiscal year."));
            return;
        }
        const rows = data.groups.map((group, index) => {
            const open = this.expanded.has(group.sales_person);
            const heading = `<tr class="mi-person"><th scope="row"><button type="button" class="mi-toggle" data-group="${index}" aria-expanded="${open}"><span aria-hidden="true">${open ? "▾" : "▸"}</span> ${this.escape(group.sales_person || __("Unallocated"))} <small class="text-muted">(${group.items.length})</small></button></th>${this.cells(group.months, group.total, index)}</tr>`;
            if (!open) return heading;
            return heading + group.items.map((item, itemIndex) => {
                const details = [item.item_group, item.territory, item.customer_group].filter(Boolean).map((v) => this.escape(v)).join(" · ");
                return `<tr class="mi-item"><th scope="row"><div>${this.escape(item.item_code || __("Unallocated item"))}</div><small class="text-muted">${details}</small></th>${this.cells(item.months, item.total, index, itemIndex)}</tr>`;
            }).join("");
        }).join("");
        const unit = data.pay_on === "Qty" ? __("Incentive quantity") : `${__("Incentive amount")} (${this.escape(data.currency)})`;
        this.results.html(`<div class="mi-summary"><strong>${unit}</strong><span class="text-muted">${__("Expand a sales person to see item details. Total is the sum of monthly incentives.")}</span></div>
            <div class="mi-scroll" tabindex="0" role="region" aria-label="${this.escape(__("Monthly incentives table"))}"><table class="table mi-table"><colgroup><col class="mi-label-column">${data.month_numbers.map(() => "<col>").join("")}<col></colgroup><thead><tr><th scope="col">${__("Sales Person / Item")}</th>${data.month_numbers.map((month) => `<th scope="col" title="${this.escape(__(data.months[month - 1]))}"><button type="button" class="mi-value" data-detail-month="${month}">${this.escape(__(data.months[month - 1]).slice(0, 3))}</button></th>`).join("")}<th scope="col">${__("Total")}</th></tr></thead><tbody>${rows}</tbody><tfoot><tr><th scope="row">${__("Grand Total")}</th>${this.cells(data.months_total, data.total)}</tr></tfoot></table></div>
            <p class="mi-note text-muted">${__("Dates limit actual sales; targets remain full monthly targets. Achieved means a positive item incentive in the selected range. Display values are rounded to whole numbers.")}</p>`);
    }
}
