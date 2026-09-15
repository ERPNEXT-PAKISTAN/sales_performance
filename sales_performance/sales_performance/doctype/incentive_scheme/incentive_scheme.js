frappe.ui.form.on("Incentive Scheme", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Achievement Based On picks the slab (min/max rate). Pay Incentive On: Amount = surplus amount × %; Qty = surplus qty × % (not converted by selling price)."
			)
		);
	},
});
