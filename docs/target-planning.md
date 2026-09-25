# Entering and changing sales targets

Sales Target Planning supports historical, manual, and copied targets. Approved plans keep the same plan number when amended.

## Create targets manually

1. Create a Sales Target Planning document and select Company and Fiscal Year.
2. Set **Target Source = Manual**. Previous-year sales are not required.
3. Choose **Target Entry = Annual** or **Monthly**.
4. Choose **Target Values = Quantity and Rate** or **Quantity and Amount**.
5. Add proposal rows with Sales Person (or Territory), Item, and Customer Group. Header assignments default into new rows. Item Group and UOM come from the Item.
6. For annual entry, enter Approved Target Qty and Rate/Amount. Save generates monthly allocations using the selected distribution method.
7. For monthly entry, add the proposal identities, then use **Prepare / Refresh Targets** to create the 12 month rows. Enter monthly quantities and rates/amounts. Save rolls them into annual totals.
8. Save, Submit for Review, then Approve.

**Manual Monthly** preserves the monthly allocation. When using Annual entry, the monthly totals must equal annual totals. **Distribute Annual Targets** explicitly replaces the monthly allocation. Normal saves never silently replace a manual allocation.

**Copy Existing Plan** exposes **Copy Targets from Plan**. The source must belong to the same company. Copying updates the editor; save and approval are separate.

## Import Excel or CSV

Open **Import Excel / CSV**, choose Annual or Monthly, and download the CSV template. Excel can open this template; uploads accept `.xlsx` and UTF-8 `.csv`.

Columns: `sales_person`, `territory`, `item_code`, `customer_group`, `target_qty`, `target_rate`, `target_amount`, `remarks`. Monthly files also require `month` (calendar month number 1–12).

Enter quantity and either rate or amount. If both rate and amount are supplied, they must agree. Blank salesperson, territory and customer group use the header defaults.

- **Append** rejects an existing matching target.
- **Update Matching Rows** updates matching targets and adds missing ones.
- Annual matching uses Sales Person + Territory + Item + Customer Group.
- Monthly matching also includes Month. Use Update Matching Rows to fill existing empty month rows.
- Annual imports allocate imported rows equally across months. Unrelated manual monthly allocations are preserved.
- Validation rejects invalid links, duplicate input rows, invalid months and negative/non-finite numbers. Nothing is saved by the preview; apply it to the editor, then save or approve.

## Change an approved plan

1. Open the approved plan and select **Amend Targets**, or **Continue Editing** to resume saved changes directly.
2. Enter a reason and effective month. Month 1 allows an entire-year correction. Earlier months are protected otherwise.
3. Edit in the same planning form. Company and Fiscal Year stay fixed.
4. Edit or remove rows in the expanded **Target Proposal Details** table. Removing a row immediately removes its displayed monthly allocations and updates the editor totals.
5. An approver clicks the primary **Apply Changes** button, reviews the before/after preview, and selects **Apply Changes to Plan & Reports**. This updates the approved plan and ERPNext targets. Refresh any already open reports afterward.

For approvers, **Apply Changes** saves, previews, and applies the amendment. Confirm with **Apply Changes to Plan & Reports**. For other users it submits the changes for approval; reports update after an approver applies them. The form shows one main action and one target table. Reloading returns to approved targets; **Continue Editing** reopens the saved pending version.

Only one amendment can be pending per plan. Opening Amend Targets resumes it. Conflicting edits are rejected and require a reload. **Exit Amendment** returns to live targets; **Discard Amendment** closes the pending changes. **Amendment History** shows applied and discarded amendments, reasons, authors, approvals and changed inputs.

## Transfer targets when a salesperson leaves

For an approved plan, open an amendment first. Then select **Transfer Targets**:

- Select the original and receiving salesperson.
- Choose the first calendar month to transfer, through December.
- Choose all matching proposal rows or tick selected proposal rows first.
- Enter 100% for a full transfer, or a smaller percentage for a partial transfer.
- Enter a reason and review the quantity/amount preview.

**From Sales Person** lists people present in the current editor. A pending amendment
may already have reassigned or removed a person, even though the live approved plan
still shows them. Resume the amendment and check Proposal Details before transferring
again. The dialog defaults to the salesperson of selected rows; all selected rows must
belong to that person. Unsaved identity changes on a selected row are supported.

A transfer is rejected if the selected rows have no targets in the chosen months.
This prevents accidentally repeating a completed full transfer. The percentage applies
to the current monthly targets, not to the unsold balance after actual sales.

For example, July transfers leave January–June targets with the original salesperson. The receiver's matching target is combined with the transferred quantity and amount. Transfers preserve overall annual totals; quantity rounding follows the app's whole-number precision.

If the receiver also has matching targets in another applicable approved plan, achievement calculations combine the monthly targets and count actual sales once.

Actual invoice sales are never reassigned. Posted/submitted/paid incentive payouts are never rewritten. Historical target corrections can change current achievement calculations and may require a separate payout adjustment.

## Synchronization

Approval replaces only ERPNext target rows owned by this plan (or a legacy plan it supersedes), including rows on a salesperson who no longer has targets. Repeated synchronization does not duplicate these rows. Unrelated targets remain intact.

ERPNext supports one monthly distribution per native target row. When quantity and amount need different distributions, synchronization writes separate quantity and amount rows so both allocations remain correct. Sales Performance continues to use its detailed monthly target rows.
