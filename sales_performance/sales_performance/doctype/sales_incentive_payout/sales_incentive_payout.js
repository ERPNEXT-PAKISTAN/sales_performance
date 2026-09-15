frappe.ui.form.on("Sales Incentive Payout", {
	refresh(frm) {
		frm.dashboard.clear_headline();
		frm.set_df_property("pay_on", "read_only", frm.doc.docstatus !== 0);
		if (frm.doc.docstatus === 0) {
			frm.page.set_indicator(__("Draft"), "gray");
			frm.page.set_primary_action(__("Get Incentives"), () => load_incentives(frm));
			if (frm.doc.items && frm.doc.items.length && frm.doc.total_incentive_amount > 0) {
				frm.add_custom_button(__("Submit — Post Accrual GL (Not Paid)"), () => {
					frm.savesubmit();
				}).addClass("btn-primary");
				frm.dashboard.set_headline_alert(
					__("Submit to post GL: Dr Incentive Expense / Cr Incentive Payable. Status becomes Not Paid."),
					"blue"
				);
			}
		}
		if (frm.doc.docstatus === 1 && frm.doc.payment_status !== "Paid") {
			frm.page.set_indicator(__("Not Paid"), "orange");
			frm.dashboard.set_headline_alert(
				__("Accrual is on the books. Click Pay Now to post bank/cash GL and mark Paid."),
				"orange"
			);
			frm.add_custom_button(__("Pay Now — Post to GL"), () => {
				frm.call({
					method: "mark_as_paid",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Posting payment to GL..."),
					callback: (r) => {
						if (!r.exc) {
							frm.reload_doc();
						}
					},
				});
			}).addClass("btn-primary");
			frm.add_custom_button(__("Create Payment Entry (draft)"), () => {
				frm.call({
					method: "create_payment_entry",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Creating Payment Entry..."),
					callback: (r) => {
						frm.reload_doc();
						if (r.message) {
							frappe.show_alert({
								message: __("Payment Entry created as draft. Submit it to mark Paid."),
								indicator: "green",
							});
							frappe.set_route("Form", "Payment Entry", r.message);
						}
					},
				});
			});
		}
		if (frm.doc.payment_status === "Paid") {
			frm.page.set_indicator(__("Paid"), "green");
			frm.dashboard.set_headline_alert(__("This incentive is Paid. Payment GL has been posted."), "green");
		}
		if (frm.doc.journal_entry) {
			frm.add_custom_button(__("Accrual Journal Entry"), () => {
				frappe.set_route("Form", "Journal Entry", frm.doc.journal_entry);
			}, __("View"));
		}
		if (frm.doc.payment_journal_entry) {
			frm.add_custom_button(__("Payment Journal Entry"), () => {
				frappe.set_route("Form", "Journal Entry", frm.doc.payment_journal_entry);
			}, __("View"));
		}
		if (frm.doc.payment_entry) {
			frm.add_custom_button(__("Payment Entry"), () => {
				frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry);
			}, __("View"));
		}
	},

	onload(frm) {
		frm.set_query("expense_account", () => ({
			filters: { company: frm.doc.company, is_group: 0, root_type: "Expense" },
		}));
		frm.set_query("payable_account", () => ({
			filters: { company: frm.doc.company, is_group: 0, root_type: "Liability" },
		}));
		frm.set_query("paid_from_account", () => ({
			filters: { company: frm.doc.company, is_group: 0, account_type: ["in", ["Bank", "Cash"]] },
		}));
		frm.set_query("cost_center", () => ({
			filters: { company: frm.doc.company, is_group: 0 },
		}));
		if (frm.is_new() && !frm.doc.pay_on) {
			frm.set_value("pay_on", "Amount");
		}
	},

	company(frm) {
		if (!frm.doc.company) return;
		frappe.db.get_value(
			"Sales Performance Settings",
			"Sales Performance Settings",
			["incentive_expense_account", "incentive_payable_account", "incentive_paid_from_account", "incentive_cost_center"],
			(r) => {
				if (!r) return;
				if (!frm.doc.expense_account) frm.set_value("expense_account", r.incentive_expense_account);
				if (!frm.doc.payable_account) frm.set_value("payable_account", r.incentive_payable_account);
				if (!frm.doc.paid_from_account) frm.set_value("paid_from_account", r.incentive_paid_from_account);
				if (!frm.doc.cost_center) frm.set_value("cost_center", r.incentive_cost_center);
			}
		);
		set_pay_on_from_scheme(frm);
	},

	fiscal_year(frm) {
		set_pay_on_from_scheme(frm);
	},

	pay_on(frm) {
		if (frm.doc.docstatus !== 0 || frm.is_new() || !frm.doc.company || !frm.doc.fiscal_year) {
			return;
		}
		load_incentives(frm);
	},

	get_incentives(frm) {
		load_incentives(frm);
	},
});

function set_pay_on_from_scheme(frm) {
	if (!frm.doc.company || frm.doc.docstatus !== 0) return;
	frappe.db.get_list("Incentive Scheme", {
		fields: ["pay_on", "fiscal_year"],
		filters: { disabled: 0, company: frm.doc.company },
		limit: 20,
		order_by: "modified desc",
	}).then((all) => {
		const hit =
			(all || []).find((s) => s.fiscal_year === frm.doc.fiscal_year) ||
			(all || []).find((s) => !s.fiscal_year) ||
			(all || [])[0];
		if (hit && hit.pay_on && frm.is_new()) {
			frm.set_value("pay_on", hit.pay_on);
		}
	});
}

function load_incentives(frm) {
	(frm.doc.items || []).slice().forEach((row) => {
		if (!(row.incentive_amount > 0)) {
			const grid_row = frm.get_field("items").grid.grid_rows_by_docname[row.name];
			if (grid_row) grid_row.remove();
		}
	});
	const run = () => {
		frm.call({
			method: "get_incentives",
			doc: frm.doc,
			freeze: true,
			freeze_message: __("Calculating incentives..."),
			callback: (r) => {
				if (!r.exc) {
					frm.reload_doc();
				}
			},
		});
	};
	if (frm.doc.docstatus !== 0) {
		return;
	}
	frm.save().then(run);
}
