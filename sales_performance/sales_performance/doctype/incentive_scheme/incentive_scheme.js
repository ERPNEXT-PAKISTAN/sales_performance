frappe.ui.form.on("Incentive Scheme", {
	refresh(frm) {
		frm.set_intro(
			__(
				"Slabs: Min Achievement 90, Min Incentive 0.90, Max Achievement 100, Max Incentive 1.75 pays a rate of 0.90% from 90% to below 100%, and 1.75% at 100% and above. For more levels, add rows with higher Min Achievement thresholds; the highest qualifying minimum takes precedence. Achievement Based On picks the slab (min/max rate). Pay Incentive On: Amount = surplus amount × %; Qty = surplus qty × % (not converted by selling price)."
			)
		);
	},
});
