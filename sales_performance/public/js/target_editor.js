/* One editor for draft targets and pending amendments to an approved plan. */
(() => {
    if (window.sales_target_editor) return;
    const api = "sales_performance.api.target_editing.";
    const headers = ["title", "sales_person", "territory", "item_group", "customer_group", "target_source", "entry_basis", "value_basis", "growth_method", "uniform_growth_percent", "pricing_method", "price_list", "distribution_method", "notes", "incentive_calculation_level"];
    const tables = ["proposal_details", "monthly_details", "growth_rules", "custom_percents"];
    const esc = value => frappe.utils.escape_html(String(value ?? ""));
    const canApprove = () => frappe.session.user === "Administrator" || ["Sales Target Approver", "Sales Performance Admin", "System Manager"].some(r => frappe.user.has_role(r));
    const canAmend = () => frappe.session.user === "Administrator" || ["Sales Target Editor", "Sales Target Manager", "Sales Performance Admin", "System Manager"].some(r => frappe.user.has_role(r));
    const canReject = () => canApprove() || frappe.user.has_role("Sales Target Manager");
    const call = async (method, args) => (await frappe.call({method: api + method, args, freeze: true})).message;
    const payload = frm => Object.fromEntries([...headers, ...tables].map(f => [f, frm.doc[f]]));
    const monthOptions = Array.from({length: 12}, (_, i) => String(i + 1)).join("\n");
    const historicalMarker = "[Historical target retained]";

    function refreshHistoricalRows(frm) {
        guardGridNavigation(frm);
        const grid = frm.fields_dict.proposal_details?.grid;
        if (!grid) return;
        for (const row of grid.grid_rows || []) {
            const historical = String(row.doc?.remarks || "").startsWith(historicalMarker);
            const node = row.wrapper?.[0] || row.wrapper;
            if (node?.style) node.style.display = historical && !frm._show_historical_targets ? "none" : "";
        }
    }

    function guardGridNavigation(frm) {
        for (const key of tables) {
            const grid = frm.fields_dict[key]?.grid;
            const wrapper = grid?.wrapper?.[0];
            if (!wrapper || wrapper._targetNavigationGuard) continue;
            wrapper._targetNavigationGuard = true;
            wrapper.addEventListener("keydown", event => {
                if (event.ctrlKey || event.metaKey || event.altKey || !["ArrowUp", "ArrowDown", "Tab"].includes(event.key)) return;
                const node = event.target.closest(".grid-row");
                const row = (grid.grid_rows || []).find(row => row?.wrapper?.[0] === node);
                if (!row) return;
                const backwards = event.key === "ArrowUp" || (event.key === "Tab" && event.shiftKey);
                const index = Number(row.doc.idx) - 1 + (backwards ? -1 : 1);
                // Frappe indexes adjacent rows even when pagination has not rendered them.
                if (index >= 0 && index < grid.get_data().length && !grid.grid_rows[index]) {
                    event.stopImmediatePropagation();
                    if (event.key !== "Tab") event.preventDefault();
                }
            }, true);
        }
    }

    function apply(frm, data) {
        for (const key of headers) if (key in data) frm.doc[key] = data[key];
        for (const key of tables) {
            if (!(key in data)) continue;
            // Amendment payloads created by older app versions may not include
            // read-only history/calculation fields. Preserve those from the
            // live approved row before replacing the grid contents.
            const existing = key === "proposal_details"
                ? new Map((frm.doc.proposal_details || []).filter(r => r.row_key).map(r => [r.row_key, r]))
                : key === "monthly_details"
                    ? new Map((frm.doc.monthly_details || []).map(r => [`${r.row_key}|${r.month_number}`, r]))
                : null;
            frm.clear_table(key);
            for (const row of data[key]) {
                const previous = key === "monthly_details"
                    ? existing?.get(`${row.row_key}|${row.month_number}`)
                    : existing?.get(row.row_key);
                const values = previous ? {...previous, ...row} : row;
                if (previous) {
                    for (const field of ["previous_year_target_qty", "previous_year_actual_qty", "previous_year_target_amount", "previous_year_actual_amount", "growth_percent", "calculated_target_qty", "source_rate", "calculated_target_amount", "price_source", "price_reference", "requires_review", "review_reason"]) {
                        if (values[field] == null) values[field] = previous[field];
                    }
                }
                if (key === "monthly_details" && previous && values.distribution_percent == null) {
                    values.distribution_percent = previous.distribution_percent;
                }
                frm.add_child(key, values);
            }
        }
        refreshTotals(frm);
        frm.dirty();
        frm.refresh_fields();
        frm.fields_dict.proposal_details?.grid?.refresh();
        editor.refresh(frm);
    }
    async function ensureSaved(frm) {
        if (frm.is_new() || (frm.is_dirty() && !frm._target_amendment)) await frm.save();
    }
    async function preview(frm, operation, options = {}, sourcePayload = payload(frm)) {
        if (frm.is_new()) await frm.save();
        return call("preview_edit", {name: frm.doc.name, payload: {...sourcePayload, company: frm.doc.company, fiscal_year: frm.doc.fiscal_year}, operation, options});
    }
    function dialog(title, fields, action, label = __("Continue")) {
        const d = new frappe.ui.Dialog({title, fields, primary_action_label: label,
            primary_action: async values => {
                d.disable_primary_action();
                try { await action(values, d); }
                catch (error) {
                    // Frappe already displays validation and request errors in a message dialog.
                    if (!error?.status && !error?._server_messages && !error?.exc && !frappe.msg_dialog?.is_visible) {
                        frappe.msgprint(esc(error?.message || __("The action could not be completed. Please try again.")));
                    }
                } finally { d.enable_primary_action(); }
            }});
        d.show();
        return d;
    }
    async function saveAmendment(frm, submit = false) {
        const a = frm._target_amendment;
        const result = await call("save_amendment", {name: frm.doc.name, amendment: a.name, modified: a.modified, payload: payload(frm), submit: submit ? 1 : 0});
        frm._target_amendment = result;
        apply(frm, result.payload);
        frm.doc.__unsaved = 0;
        editor.refresh(frm);
        frappe.show_alert({message: submit ? __("Amendment submitted for review; live targets are unchanged") : __("Amendment saved; live targets are unchanged"), indicator: "green"});
        return result;
    }
    async function showPreview(frm, amendment, approve = false) {
        const data = await call("amendment_preview", {name: frm.doc.name, amendment});
        const cols = ["sales_person", "territory", "item_code", "customer_group", "month", "before_qty", "after_qty", "before_amount", "after_amount"];
        const monthlyChanges = data.changes || [];
        const inputChanges = data.row_changes || [];
        const limit = 100;
        const html = `<p>${esc(data.reason)}</p><p>${esc(data.notice)}</p>
            ${data.settings.length ? `<ul>${data.settings.map(s => `<li>${esc(s.field)}: ${esc(s.before)} → ${esc(s.after)}</li>`).join("")}</ul>` : ""}
            <p>${__("Changed monthly targets: {0}. Changed proposal inputs: {1}.", [monthlyChanges.length, inputChanges.length])}</p>
            ${monthlyChanges.length ? `<div style="overflow:auto;max-height:45vh"><table class="table table-bordered"><thead><tr>${cols.map(c => `<th>${esc(frappe.unscrub(c))}</th>`).join("")}</tr></thead><tbody>${monthlyChanges.slice(0, limit).map(row => `<tr>${cols.map(c => `<td>${esc(row[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>${monthlyChanges.length > limit ? `<p class="text-muted">${__("Showing the first {0} monthly changes.", [limit])}</p>` : ""}</div>` : ""}
            <details><summary>${__("Changed Inputs ({0})", [inputChanges.length])}</summary><div style="overflow:auto;max-height:40vh"><table class="table"><thead><tr><th>${__("Table / Row")}</th><th>${__("Sales Person")}</th><th>${__("Field")}</th><th>${__("Before")}</th><th>${__("After")}</th></tr></thead><tbody>${inputChanges.slice(0, limit).map(r => `<tr><td>${esc(r.table)} / ${esc(r.row)}</td><td>${esc(r.sales_person)}</td><td>${esc(r.field)}</td><td>${esc(r.before)}</td><td>${esc(r.after)}</td></tr>`).join("")}</tbody></table>${inputChanges.length > limit ? `<p class="text-muted">${__("Showing the first {0} changed inputs.", [limit])}</p>` : ""}</div></details>`;
        dialog(__("Target Amendment Preview"), [{fieldname: "preview", fieldtype: "HTML", options: html}], async (_, d) => {
            if (approve) {
                const a = frm._target_amendment;
                await call("approve_amendment", {name: frm.doc.name, amendment: a.name, modified: a.modified});
                delete frm._target_amendment;
                delete frm._pending_target_amendment;
                frm.doc.__unsaved = 0;
                await frm.reload_doc();
                frappe.show_alert({message: __("Changes applied. Refresh open reports to see the updated targets."), indicator: "green"});
            }
            d.hide();
        }, approve ? __("Apply Changes to Plan & Reports") : __("Close"));
    }
    async function startAmendment(frm) {
        const pending = await call("pending_amendment", {name: frm.doc.name});
        if (pending) {
            const result = await call("start_amendment", {name: frm.doc.name});
            frm._target_amendment = result;
            apply(frm, result.payload);
            frm.doc.__unsaved = 0;
            return;
        }
        dialog(__("Amend Approved Targets"), [
            {fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1},
            {fieldname: "effective_month", fieldtype: "Select", options: monthOptions, label: __("Effective From Calendar Month"), default: "1", reqd: 1,
                description: __("1 allows an entire-year correction. Earlier months are protected for other selections. An existing pending amendment will be resumed.")},
        ], async (values, d) => {
            const result = await call("start_amendment", {name: frm.doc.name, ...values});
            frm._target_amendment = result;
            apply(frm, result.payload);
            frm.doc.__unsaved = 0;
            d.hide();
        }, __("Open Amendment"));
    }
    function transferTargets(frm) {
        const selectedRows = frm.fields_dict.proposal_details.grid.get_selected_children();
        const person = row => row.sales_person || frm.doc.sales_person;
        const sources = [...new Set((frm.doc.proposal_details || []).map(person).filter(Boolean))].sort();
        if (!sources.length) {
            frappe.msgprint(__("There are no salesperson target rows in this editor. Add or restore the intended proposal rows first."));
            return;
        }
        if (selectedRows.some(r => !r.row_key)) {
            frappe.msgprint(__("Use Prepare / Refresh Targets before selecting newly added rows for transfer."));
            return;
        }
        const selected = selectedRows.map(r => r.row_key);
        const selectedPeople = [...new Set(selectedRows.map(person).filter(Boolean))];
        dialog(__("Transfer Targets"), [
            {fieldname: "source", fieldtype: "Select", options: ["", ...sources].join("\n"), label: __("From Sales Person"), reqd: 1,
                default: selectedPeople.length === 1 ? selectedPeople[0] : sources.length === 1 ? sources[0] : "",
                description: __("Only people with rows in the current editor are listed. Already reassigned or removed people are absent.")},
            {fieldname: "destination", fieldtype: "Link", options: "Sales Person", label: __("To Sales Person"), reqd: 1, get_query: () => ({filters: {enabled: 1}})},
            {fieldname: "start_month", fieldtype: "Select", options: monthOptions, label: __("Effective From Calendar Month"), default: String(frm._target_amendment?.effective_month || Math.min(new Date().getMonth() + 2, 12)), reqd: 1},
            {fieldname: "percent", fieldtype: "Percent", label: __("Percentage of Remaining Targets"), default: 100, reqd: 1},
            {fieldname: "scope", fieldtype: "Select", options: "All Matching Rows\nSelected Rows", default: selected.length ? "Selected Rows" : "All Matching Rows", label: __("Scope")},
            {fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1},
            {fieldtype: "HTML", options: `<p class="text-muted">${__("Targets move from the selected month through December. Actual sales and posted payouts remain with their original salesperson. Month 1 changes the entire year.")}</p>`},
        ], async (values, d) => {
            if (values.scope === "Selected Rows" && !selected.length) { frappe.msgprint(__("Select proposal rows first, or choose All Matching Rows.")); return; }
            if (values.scope === "Selected Rows" && selectedRows.some(r => person(r) !== values.source)) {
                frappe.msgprint(__("Selected rows must all belong to the From Sales Person. Select that person's rows again, or choose All Matching Rows.")); return;
            }
            if (values.source === values.destination) { frappe.msgprint(__("Choose two different Sales Persons.")); return; }
            if (frm._target_amendment && Number(values.start_month) < Number(frm._target_amendment.effective_month)) {
                frappe.msgprint(__("The transfer month cannot be earlier than this amendment's effective month ({0}).", [frm._target_amendment.effective_month])); return;
            }
            const result = await preview(frm, "transfer", {...values, row_keys: values.scope === "Selected Rows" ? selected : []});
            frappe.confirm(__("Transfer {0} quantity and {1} amount across {2} target rows from {3} to {4}?", [result.summary.quantity, result.summary.amount, result.summary.rows, esc(values.source), esc(values.destination)]), () => {
                apply(frm, result.payload);
                d.hide();
            });
        }, __("Preview Transfer"));
    }
    function template(monthly) {
        const columns = ["sales_person", "territory", "item_code", "customer_group", ...(monthly ? ["month"] : []), "target_qty", "target_rate", "target_amount", "remarks"];
        const link = document.createElement("a");
        const url = URL.createObjectURL(new Blob([columns.join(",") + "\r\n"], {type: "text/csv;charset=utf-8"}));
        link.href = url; link.download = monthly ? "monthly_targets.csv" : "annual_targets.csv"; link.click(); URL.revokeObjectURL(url);
    }
    async function importTargets(frm) {
        await ensureSaved(frm);
        const d = dialog(__("Import Excel / CSV Targets"), [
            {fieldname: "layout", fieldtype: "Select", options: "Annual\nMonthly", label: __("Template"), default: "Annual", reqd: 1},
            {fieldname: "mode", fieldtype: "Select", options: "Append\nUpdate Matching Rows", label: __("Import Mode"), default: "Append", reqd: 1},
            {fieldname: "download", fieldtype: "Button", label: __("Download Template"), click: () => template(d.get_value("layout") === "Monthly")},
            {fieldname: "upload", fieldtype: "Button", label: __("Upload Excel / CSV"), click: () => new frappe.ui.FileUploader({doctype: frm.doctype, docname: frm.doc.name, is_private: 1,
                restrictions: {allowed_file_types: [".xlsx", ".csv"]}, on_success: file => d.set_value("file_url", file.file_url)})},
            {fieldname: "file_url", fieldtype: "Data", label: __("Uploaded File"), read_only: 1, reqd: 1},
            {fieldtype: "HTML", options: `<p>${__("Use month numbers 1–12. Enter Target Qty and either Target Rate or Target Amount. Matching uses Sales Person, Territory, Item and Customer Group, plus Month for monthly imports. Annual imports use equal monthly distribution.")}</p>`},
        ], async (values, modal) => {
            const result = await preview(frm, "import", values);
            const rows = result.payload.proposal_details;
            const columns = ["sales_person", "territory", "item_code", "customer_group", "approved_target_qty", "approved_target_amount"];
            dialog(__("Import Preview"), [{fieldtype: "HTML", options: `<p>${__("Validated {0} imported rows. Resulting annual targets are shown below (first 50). Save or approve separately to activate changes.", [result.summary.imported_rows])}</p><div style="overflow:auto;max-height:55vh"><table class="table"><thead><tr>${columns.map(c => `<th>${esc(frappe.unscrub(c))}</th>`).join("")}</tr></thead><tbody>${rows.slice(0,50).map(r => `<tr>${columns.map(c => `<td>${esc(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`}], async (_, confirmation) => {
                apply(frm, result.payload); confirmation.hide(); modal.hide();
            }, __("Apply to Editor"));
        }, __("Validate & Preview"));
    }
    async function history(frm) {
        const rows = await call("history", {name: frm.doc.name});
        const d = new frappe.ui.Dialog({title: __("Amendment History"), size: "large", fields: [{fieldname: "history", fieldtype: "HTML"}]});
        d.fields_dict.history.$wrapper.html(`<table class="table"><thead><tr><th>${__("Status")}</th><th>${__("Reason")}</th><th>${__("Effective Month")}</th><th>${__("Requested By")}</th><th>${__("Approved By")}</th><th></th></tr></thead><tbody>${rows.map((r, i) => `<tr><td>${esc(r.status)} ${r.amendment_number || ""}</td><td>${esc(r.reason)}</td><td>${esc(r.effective_month)}</td><td>${esc(r.owner)}</td><td>${esc(r.approved_by || "")}</td><td><button class="btn btn-xs btn-default" data-amendment="${i}">${__("View Changes")}</button></td></tr>`).join("")}</tbody></table>`);
        d.fields_dict.history.$wrapper.on("click", "[data-amendment]", e => showPreview(frm, rows[Number(e.currentTarget.dataset.amendment)].name));
        d.show();
    }
    const editor = window.sales_target_editor = {
        async load(frm) {
            // A form reload contains the live document, never the pending JSON snapshot.
            delete frm._target_amendment;
            const name = frm.doc.name;
            frm._pending_target_amendment = null;
            if (!frm.is_new() && frm.doc.status === "Approved" && !frm._target_amendment) {
                const pending = await call("pending_amendment", {name});
                if (frm.doc.name !== name) return;
                frm._pending_target_amendment = pending;
            }
            editor.refresh(frm);
        },
        refresh(frm) {
            frm.clear_custom_buttons();
            const amendment = frm._target_amendment;
            if (!amendment) frm.dashboard.clear_headline();
            const locked = ["Approved", "Cancelled", "Superseded"].includes(frm.doc.status) && !amendment;
            for (const field of [...headers, ...tables]) frm.set_df_property(field, "read_only", locked ? 1 : 0);
            for (const field of ["company", "fiscal_year"]) frm.set_df_property(field, "read_only", locked || amendment ? 1 : 0);
            frm.toggle_display("get_previous_year_sales", !locked && !amendment && (!frm.doc.target_source || frm.doc.target_source === "Previous Year"));
            // Proposal Details is the one target table in both approved and editing views.
            frm.toggle_display("previous_sales_html", false);
            frm.toggle_display("proposal_details", true);
            frm.toggle_display("proposal_edit_section", true);
            const monthly = frm.doc.entry_basis === "Monthly";
            const amount = frm.doc.value_basis === "Quantity and Amount";
            const pg = frm.fields_dict.proposal_details.grid;
            const historicalCount = (frm.doc.proposal_details || []).filter(row => String(row.remarks || "").startsWith(historicalMarker)).length;
            if (historicalCount) frm.add_custom_button(
                frm._show_historical_targets ? __("Hide Historical Rows") : __("Show Historical Rows ({0})", [historicalCount]),
                () => { frm._show_historical_targets = !frm._show_historical_targets; editor.refresh(frm); }, __("More")
            );
            pg.update_docfield_property("approved_target_qty", "read_only", monthly && !amendment ? 1 : 0);
            pg.update_docfield_property("approved_target_rate", "read_only", amount || (monthly && !amendment) ? 1 : 0);
            pg.update_docfield_property("approved_target_amount", "read_only", !amount || (monthly && !amendment) ? 1 : 0);
            const mg = frm.fields_dict.monthly_details.grid;
            for (const f of ["sales_person", "territory", "item_code", "customer_group", "month_number"]) mg.update_docfield_property(f, "read_only", 1);
            mg.cannot_add_rows = true;
            mg.cannot_delete_rows = true;
            for (const f of ["target_qty", "target_rate", "target_amount"]) mg.update_docfield_property(f, "read_only", !(monthly || frm.doc.distribution_method === "Manual Monthly") || (f === "target_rate" && amount) || (f === "target_amount" && !amount) ? 1 : 0);
            if (locked || amendment) frm.disable_save(); else frm.enable_save();
            if (!frm.is_new()) frm.add_custom_button(__("Amendment History"), () => history(frm), __("More"));
            if (locked) {
                frm.page.clear_primary_action();
                if (frm.doc.status === "Approved") {
                    frm.dashboard.set_headline_alert(frm._pending_target_amendment
                        ? __("Showing approved targets used by reports. Saved changes are waiting: click Continue Editing, then Apply Changes to update the plan and reports.")
                        : __("Showing approved targets used by reports. Use Amend Targets to make changes."), frm._pending_target_amendment ? "orange" : "blue");
                }
                if (frm.doc.status === "Approved" && frm.perm.some(p => p.write) && canAmend()) {
                    const editLabel = frm._pending_target_amendment ? __("Continue Editing") : __("Amend Targets");
                    frm.page.set_primary_action(editLabel, () => startAmendment(frm));
                    if (canApprove() && !frm._pending_target_amendment) frm.add_custom_button(__("Apply ERPNext Targets"), async () => {
                        await frappe.call({method: "sales_performance.api.planning.apply_targets", args: {name: frm.doc.name}, freeze: true});
                        await frm.reload_doc();
                        frappe.show_alert({message: __("ERPNext targets synchronized"), indicator: "green"});
                    });
                }
                refreshHistoricalRows(frm);
                return;
            }
            frm.add_custom_button(__("Prepare / Refresh Targets"), async () => { const r = await preview(frm, "normalize"); apply(frm, r.payload); }, __("More"));
            frm.add_custom_button(__("Update Zero Target Qty"), () => {
                const rows = (frm.doc.proposal_details || []).filter(row => flt(row.approved_target_qty) === 0);
                if (!rows.length) {
                    frappe.msgprint(__("There are no rows with Approved Target Qty equal to zero."));
                    return;
                }
                const html = `<p>${__("Enter the Approved Target Qty for each item. Leave a box empty to skip that item. Monthly entry plans will split each entered quantity across that item’s months.")}</p>
                    <div style="max-height:55vh;overflow:auto"><table class="table table-bordered"><thead><tr><th>${__("Item")}</th><th>${__("Sales Person")}</th><th>${__("Calculated Target Qty")}</th><th>${__("Approved Target Qty")}</th></tr></thead><tbody>${rows.map((row, index) => `<tr><td>${esc(row.item_code)}</td><td>${esc(row.sales_person || row.territory || "")}</td><td>${esc(row.calculated_target_qty ?? 0)}</td><td><input type="number" min="0" step="any" class="form-control" data-zero-target-row="${index}" aria-label="${esc(__("Approved Target Qty for {0}", [row.item_code]))}"></td></tr>`).join("")}</tbody></table></div>`;
                const d = dialog(__("Update Zero Approved Target Quantities"), [{fieldname: "targets", fieldtype: "HTML", options: html}], async () => {
                    const updates = [];
                    const inputs = d.fields_dict.targets.$wrapper[0].querySelectorAll("input[data-zero-target-row]");
                    for (const input of inputs) {
                        if (!input.value.trim()) continue;
                        const qty = Number(input.value);
                        if (!Number.isFinite(qty) || qty < 0) {
                            frappe.msgprint(__("Enter a valid non-negative quantity for each filled item."));
                            return;
                        }
                        const row = rows[Number(input.dataset.zeroTargetRow)];
                        updates.push({row_key: row.row_key, qty});
                    }
                    if (!updates.length) {
                        frappe.msgprint(__("Enter a quantity for at least one item."));
                        return;
                    }
                    const data = JSON.parse(JSON.stringify(payload(frm)));
                    const amountPrecision = Number(frappe.boot.sysdefaults.currency_precision || 2);
                    for (const update of updates) {
                        const row = data.proposal_details.find(part => part.row_key === update.row_key);
                        const source = rows.find(part => part.row_key === update.row_key);
                        if (!row || !source) continue;
                        const uom = source.uom ? await frappe.db.get_value("UOM", source.uom, "must_be_whole_number") : null;
                        const qtyPrecision = uom?.message?.must_be_whole_number ? 0 : Number(frappe.boot.sysdefaults.float_precision || 3);
                        const oldQty = flt(source.calculated_target_qty);
                        const rate = flt(source.approved_target_rate || source.target_selling_rate || source.source_rate || (oldQty ? flt(source.calculated_target_amount) / oldQty : 0));
                        row.approved_target_qty = update.qty;
                        row.approved_target_rate = rate;
                        row.approved_target_amount = flt(update.qty * rate, amountPrecision);
                        if (frm.doc.entry_basis !== "Monthly") continue;
                        let months = data.monthly_details.filter(part => part.row_key === update.row_key).sort((a, b) => Number(a.month_number) - Number(b.month_number));
                        const existingMonths = new Set(months.map(part => Number(part.month_number)));
                        for (let month = 1; month <= 12; month++) {
                            if (!existingMonths.has(month)) {
                                months.push({row_key: update.row_key, month_number: month, sales_person: row.sales_person, territory: row.territory, item_code: row.item_code, customer_group: row.customer_group, target_qty: 0, target_rate: rate, target_amount: 0});
                            }
                        }
                        months.sort((a, b) => Number(a.month_number) - Number(b.month_number));
                        const startMonth = Number(frm._target_amendment?.effective_month || 1);
                        const activeMonths = months.filter(part => Number(part.month_number) >= startMonth);
                        const weights = activeMonths.map(part => Math.max(flt(part.distribution_percent), 0));
                        const weightTotal = weights.reduce((sum, value) => sum + value, 0);
                        let assigned = 0;
                        activeMonths.forEach((part, index) => {
                            const available = Math.max(0, flt(update.qty - assigned, qtyPrecision));
                            const partQty = index === activeMonths.length - 1
                                ? available
                                : Math.min(available, flt(update.qty * (weightTotal ? weights[index] / weightTotal : 1 / activeMonths.length), qtyPrecision));
                            assigned += partQty;
                            part.target_qty = partQty;
                            part.target_rate = rate;
                            part.target_amount = flt(partQty * rate, amountPrecision);
                        });
                        data.monthly_details = data.monthly_details.filter(part => part.row_key !== update.row_key).concat(months);
                    }
                    const result = await preview(frm, "normalize", {}, data);
                    apply(frm, result.payload);
                    d.hide();
                    frappe.show_alert({message: __("Updated Approved Target Qty for {0} items. Save the plan to keep the changes.", [result.summary.rows]), indicator: "green"});
                }, __("Update Targets"));
            }, __("More"));
            frm.add_custom_button(__("Distribute Annual Targets"), () => frappe.confirm(__("Replace monthly allocations using the annual targets and selected distribution method?"), async () => { const r = await preview(frm, "distribute"); apply(frm, r.payload); }), __("More"));
            frm.add_custom_button(__("Transfer Targets"), () => transferTargets(frm), __("More"));
            frm.add_custom_button(__("Import Excel / CSV"), () => importTargets(frm), __("More"));
            if (amendment) {
                frm.add_custom_button(__("Remove All Rows for Sales Person"), () => {
                    const personOf = row => row.sales_person || frm.doc.sales_person;
                    const people = [...new Set((frm.doc.proposal_details || []).map(personOf).filter(Boolean))].sort();
                    if (!people.length) {
                        frappe.msgprint(__("There are no salesperson target rows to remove."));
                        return;
                    }
                    dialog(__("Remove Sales Person Targets"), [
                        {fieldname: "sales_person", fieldtype: "Select", label: __("Sales Person"), options: people.join("\n"), reqd: 1},
                        {fieldtype: "HTML", options: `<p class="text-danger">${__("This removes every target row for the selected salesperson for the full fiscal year, including past months. The change will be applied when you click Save & Apply Changes.")}</p>`},
                    ], async (values, d) => {
                        const selected = values.sales_person;
                        const rows = (frm.doc.proposal_details || []).filter(row => personOf(row) === selected);
                        if (!rows.length) {
                            frappe.msgprint(__("No rows were found for {0}.", [selected]));
                            return;
                        }
                        const keys = new Set(rows.map(row => row.row_key));
                        const qty = rows.reduce((sum, row) => sum + flt(row.approved_target_qty), 0);
                        const amount = rows.reduce((sum, row) => sum + flt(row.approved_target_amount), 0);
                        if (Number(amendment.effective_month) > 1) {
                            // An all-year deletion cannot be represented by a later effective month.
                            // Replace the pending amendment with a month-one amendment, keeping
                            // the current editor values in memory for this full-year action.
                            await call("discard_amendment", {name: frm.doc.name, amendment: amendment.name, modified: amendment.modified});
                            const reason = [amendment.reason, __("Removed all target rows for {0}", [selected])].filter(Boolean).join("; ");
                            frm._target_amendment = await call("start_amendment", {name: frm.doc.name, reason, effective_month: 1});
                        }
                        for (const row of [...(frm.doc.proposal_details || [])]) {
                            if (keys.has(row.row_key)) frappe.model.clear_doc(row.doctype, row.name);
                        }
                        for (const row of [...(frm.doc.monthly_details || [])]) {
                            if (keys.has(row.row_key)) frappe.model.clear_doc(row.doctype, row.name);
                        }
                        (frm.doc.proposal_details || []).forEach((row, index) => row.idx = index + 1);
                        (frm.doc.monthly_details || []).forEach((row, index) => row.idx = index + 1);
                        frm.dirty();
                        refreshTotals(frm);
                        frm.refresh_field("proposal_details");
                        frm.refresh_field("monthly_details");
                        d.hide();
                        editor.refresh(frm);
                        frappe.show_alert({message: __("Removed {0} target rows for {1} ({2} qty, {3} amount). Click Save & Apply Changes to finish.", [rows.length, selected, qty, amount]), indicator: "orange"}, 8);
                    }, __("Remove All Rows"));
                }, __("More"));
                frm.dashboard.set_headline_alert(__("Editing pending changes. Removed rows are absent here; reports change only after Apply Changes. Effective from month {0}.", [amendment.effective_month]), "orange");
                frm.page.set_primary_action(__("Save & Apply Changes"), async () => {
                    const amendment = frm._target_amendment;
                    frappe.confirm(__("Apply these changes to the approved plan and refresh its reports now?"), async () => {
                        const reason = amendment.reason || __("Approved target amendment");
                        for (const row of frm.doc.proposal_details || []) {
                            if (flt(row.override_percent) && !String(row.override_reason || "").trim()) row.override_reason = reason;
                        }
                        frm.refresh_field("proposal_details");
                        await call("apply_amendment", {name: frm.doc.name, amendment: amendment.name,
                            modified: amendment.modified, payload: payload(frm)});
                        delete frm._target_amendment;
                        delete frm._pending_target_amendment;
                        frm.doc.__unsaved = 0;
                        await frm.reload_doc();
                        frappe.show_alert({message: __("Changes applied to the plan and reports."), indicator: "green"});
                    });
                });
                frm.add_custom_button(__("Exit Amendment"), () => frappe.confirm(__("Return to approved targets? Saved changes stay pending."), async () => { delete frm._target_amendment; frm.doc.__unsaved = 0; await frm.reload_doc(); }), __("More"));
                frm.add_custom_button(__("Discard Amendment"), () => frappe.confirm(__("Discard all saved pending changes? This cannot be undone."), async () => {
                    const a = frm._target_amendment;
                    await call("discard_amendment", {name: frm.doc.name, amendment: a.name, modified: a.modified});
                    delete frm._target_amendment; frm.doc.__unsaved = 0; await frm.reload_doc();
                }), __("More"));
            } else {
                frm.page.set_primary_action(__("Save"), () => frm.save());
                if (frm.doc.target_source === "Copy Existing Plan") frm.add_custom_button(__("Copy Targets from Plan"), () => dialog(__("Copy Targets"), [{fieldname: "source", fieldtype: "Link", options: "Sales Target Planning", label: __("Source Plan"), reqd: 1}], async (v, d) => { const r = await preview(frm, "copy", v); apply(frm, r.payload); d.hide(); }));
                if (!frm.is_new()) {
                    if (["Draft", "Calculated", "Rejected"].includes(frm.doc.status)) frm.add_custom_button(__("Submit for Review"), async () => { await ensureSaved(frm); await frappe.call({method: "sales_performance.api.planning.submit_for_review", args: {name: frm.doc.name}}); await frm.reload_doc(); });
                    if (canReject() && ["Calculated", "Under Review"].includes(frm.doc.status)) frm.add_custom_button(__("Reject"), () => dialog(__("Reject Plan"), [
                        {fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1},
                    ], async (values, d) => {
                        await ensureSaved(frm);
                        await frappe.call({method: "sales_performance.api.planning.reject_plan", args: {name: frm.doc.name, reason: values.reason}, freeze: true});
                        d.hide();
                        await frm.reload_doc();
                    }, __("Reject")));
                    if (canApprove() && ["Calculated", "Under Review"].includes(frm.doc.status)) frm.add_custom_button(__("Approve"), () => frappe.confirm(__("Approve these targets and synchronize ERPNext?"), async () => { await ensureSaved(frm); await frappe.call({method: "sales_performance.api.planning.approve_plan", args: {name: frm.doc.name}, freeze: true}); await frm.reload_doc(); }));
                }
            }
            refreshHistoricalRows(frm);
        },
    };
    frappe.ui.form.on("Sales Target Planning", {
        before_save(frm) { if (frm._target_amendment) frappe.throw(__("Use Apply Changes to update the plan and reports.")); },
        target_source: frm => editor.refresh(frm), entry_basis: frm => editor.refresh(frm), value_basis: frm => editor.refresh(frm), distribution_method: frm => editor.refresh(frm),
    });
    frappe.ui.form.on("Sales Target Monthly Detail", {
        target_qty: monthlyChange, target_rate: monthlyChange, target_amount: monthlyChange,
    });
    frappe.ui.form.on("Target Proposal Detail", {
        approved_target_qty(frm, cdt, cdn) { proposalValueChanged(frm, cdt, cdn); },
        approved_target_rate(frm, cdt, cdn) { proposalValueChanged(frm, cdt, cdn); },
        approved_target_amount(frm, cdt, cdn) { proposalValueChanged(frm, cdt, cdn); },
        proposal_details_remove(frm) {
            const keys = new Set((frm.doc.proposal_details || []).map(r => r.row_key).filter(Boolean));
            const removed = (frm.doc.monthly_details || []).filter(r => !keys.has(r.row_key));
            const amendment = frm._target_amendment;
            const startMonth = Number(amendment?.effective_month || 1);
            const historicalKeys = new Set(removed.filter(row => Number(row.month_number) < startMonth && (flt(row.target_qty) || flt(row.target_amount))).map(row => row.row_key));
            const sourceRows = new Map((amendment?.payload?.proposal_details || []).map(row => [row.row_key, row]));
            const retainedKeys = new Set();
            const restoredKeys = new Set();
            for (const rowKey of historicalKeys) {
                const source = sourceRows.get(rowKey);
                if (!source) continue;
                const excluded = new Set(["name", "doctype", "parent", "parenttype", "parentfield", "idx", "creation", "modified", "owner", "modified_by", "docstatus", "__islocal", "__unsaved"]);
                const data = Object.fromEntries(Object.entries(source).filter(([field]) => !excluded.has(field)));
                if (frm.doc.entry_basis !== "Monthly" && frm.doc.distribution_method !== "Manual Monthly") {
                    frm.add_child("proposal_details", data);
                    restoredKeys.add(rowKey);
                    continue;
                }
                const past = removed.filter(row => row.row_key === rowKey && Number(row.month_number) < startMonth);
                const qty = past.reduce((sum, row) => sum + flt(row.target_qty), 0);
                const amount = past.reduce((sum, row) => sum + flt(row.target_amount), 0);
                data.approved_target_qty = qty;
                data.approved_target_amount = amount;
                data.approved_target_rate = qty ? amount / qty : flt(source.approved_target_rate);
                data.override_reason = amendment?.reason || __("Historical target retained while closing future targets");
                data.remarks = `${historicalMarker} ${__("Historical target retained through month {0}", [startMonth - 1])}${source.remarks ? ` · ${source.remarks}` : ""}`;
                frm.add_child("proposal_details", data);
                retainedKeys.add(rowKey);
                restoredKeys.add(rowKey);
            }
            for (const row of removed) {
                if (retainedKeys.has(row.row_key) && Number(row.month_number) < startMonth || restoredKeys.has(row.row_key) && !retainedKeys.has(row.row_key)) continue;
                frappe.model.clear_doc(row.doctype, row.name);
            }
            (frm.doc.monthly_details || []).forEach((row, i) => row.idx = i + 1);
            frm.refresh_field("monthly_details");
            frm.refresh_field("proposal_details");
            refreshTotals(frm);
            if (retainedKeys.size) {
                frm._historical_delete_count = (frm._historical_delete_count || 0) + retainedKeys.size;
                if (!frm._historical_delete_timer) frm._historical_delete_timer = setTimeout(() => {
                    frappe.show_alert({message: __("{0} removed rows were hidden; their past-month targets remain in the plan for historical reporting. Use More → Show Historical Rows to view them.", [frm._historical_delete_count]), indicator: "blue"}, 8);
                    frm._historical_delete_count = 0;
                    frm._historical_delete_timer = null;
                    editor.refresh(frm);
                }, 100);
            }
            if (historicalKeys.size && restoredKeys.size > retainedKeys.size) frappe.show_alert({message: __("Some rows were restored because this distribution method cannot remove protected past targets. Use an amendment effective from month 1 to remove those rows for the full year."), indicator: "orange"});
            if (historicalKeys.size && !restoredKeys.size) frappe.show_alert({message: __("This row has protected targets before the effective month. Start an amendment effective from month 1 to remove its targets for the full year."), indicator: "orange"});
            refreshHistoricalRows(frm);
        },
        proposal_details_add(frm, cdt, cdn) {
            const row = locals[cdt][cdn];
            for (const f of ["sales_person", "territory", "customer_group"]) row[f] = frm.doc[f] || "";
            frm.refresh_field("proposal_details");
        },
    });
    function refreshTotals(frm) {
        const rows = frm.doc.proposal_details || [];
        frm.doc.rows_count = rows.length;
        frm.doc.sales_persons_count = new Set(rows.map(r => r.sales_person).filter(Boolean)).size;
        frm.doc.item_groups_count = new Set(rows.map(r => r.item_group).filter(Boolean)).size;
        frm.doc.total_approved_qty = rows.reduce((sum, r) => sum + flt(r.approved_target_qty), 0);
        frm.doc.total_approved_amount = rows.reduce((sum, r) => sum + flt(r.approved_target_amount), 0);
        for (const field of ["rows_count", "sales_persons_count", "item_groups_count", "total_approved_qty", "total_approved_amount"]) frm.refresh_field(field);
    }
    function monthlyChange(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (frm.doc.value_basis === "Quantity and Amount") row.target_rate = flt(row.target_qty) ? flt(row.target_amount) / flt(row.target_qty) : 0;
        else row.target_amount = flt(row.target_qty) * flt(row.target_rate);
        frm.refresh_field("monthly_details");
    }
    function proposalValueChanged(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (frm.doc.value_basis === "Quantity and Amount") {
            row.approved_target_rate = flt(row.approved_target_qty) ? flt(row.approved_target_amount) / flt(row.approved_target_qty) : 0;
        } else {
            row.approved_target_amount = flt(row.approved_target_qty) * flt(row.approved_target_rate);
        }
        frm.refresh_field("proposal_details");
        refreshTotals(frm);
    }
})();
