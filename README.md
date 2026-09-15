# Sales Performance & Incentives

Advanced **planning and performance layer** for ERPNext v16. It does **not** replace ERPNext Sales Person / Territory / Sales Partner targets. Official execution remains ERPNext `Target Detail` (and the Item field from the existing `item_sales_target` app).

## Architecture

```
Historical Sales (submitted Sales Invoices, net of returns)
        → Target Planning (this app)
        → Growth Engine (qty × (1 + growth%))
        → Pricing Engine (price list / last sale / PY average / manual)
        → Target Amount = Target Qty × Target Selling Rate
        → Monthly Distribution
        → Manager review & approval
        → ERPNext Target Detail (idempotent sync)
        → Achievement reports
        → Incentive Scheme (configuration only; calculation is future work)
```

**Do not** compute target amount as previous-year amount × growth. Quantity and selling rate are planned independently.

## Installation

From the bench:

```bash
cd /home/frappe/frappe-bench
bench get-app /path/to/sales_performance   # if installing from git
bench --site ss.frappe.my install-app sales_performance
bench --site ss.frappe.my migrate
bench --site ss.frappe.my clear-cache
```

On this computer the app lives at `apps/sales_performance`.

Required: ERPNext. Optional: `item_sales_target` (adds Item on Target Detail so official targets can be item-wise).

## Configuration

Open **Sales Performance Settings**:

- Default pricing method
- Default distribution method
- Default growth %
- Require override reason
- Block approval when a row has qty but no price

Assign roles:

| Role | Access |
| --- | --- |
| Sales Target User | Create drafts, recalculate |
| Sales Target Manager | Review, override approved qty/rate |
| Sales Target Approver | Approve / reject, sync ERPNext targets |
| Sales Performance Manager | Reports and dashboard |
| Sales Performance Admin | Settings, Incentive Scheme, full setup |

## Target Planning

1. Create **Sales Target Planning** for a Company + Fiscal Year (optional Sales Person / Territory).
2. Add **Item Group Growth Rules** (positive or negative %). `Apply to Children` uses the Item Group tree. Higher **Priority** wins.
3. Choose **Pricing Method** and **Distribution Method**.
4. **Recalculate Proposal** (server-side):
   - Aggregates submitted Sales Invoices (`docstatus = 1`) with SQL
   - Nets returns / credit notes via signed `stock_qty` and `base_net_amount`
   - Attributes qty/amount using ERPNext **Sales Team Contribution %**
   - `Target Qty = Previous Year Net Qty × (1 + Growth % / 100)`
   - `Target Amount = Target Qty × Target Selling Rate`
5. Rows with zero previous-year qty are marked **Requires Review** (`No previous-year sales history`).
6. Manager may change **Approved Target Qty / Rate** without changing calculated values. Override reason is required when approving overridden rows.
7. **Approve** locks the document and syncs ERPNext `Target Detail` on Sales Person (or Territory). Re-running sync updates the same grain; it does not duplicate rows.
8. Further changes: **Create Revision** (new version, previous plan kept). When the revision is approved, the previous plan is marked **Superseded**.

## Growth Rules

Example:

| Item Group | Growth % |
| --- | --- |
| GI Coil | 10 |
| CR Coil | 20 |
| HR Coil | 5 |

`100 × 10% = 110`, `100 × -10% = 90`. Rounding uses System Settings float precision and UOM whole-number flag.

## Pricing Methods

| Method | Source stored on the row |
| --- | --- |
| Specific Price List | ERPNext Item Price (`price_source = Item Price`, `price_reference = IP-...`) |
| Last Selling Price | Latest submitted non-return Sales Invoice Item (`Last Selling Invoice` / `SINV-...`) |
| Previous Year Average Selling Price | Net amount ÷ net qty (`historical calculation`) |
| Manual Price | User-entered (`Manual` / `user-entered`) |

Rates are converted to stock UOM and company currency where Item Price UOM/currency differ.

## Distribution Methods

- Same Month Previous Year + Growth (default; preserves seasonality)
- Equal Monthly / Quarterly / Half-Yearly (monthly slots always sum to the annual target)
- Manual Monthly (validated on review/approval)
- Custom Percentage Distribution (must total 100%)

ERPNext **Monthly Distribution** records are created/updated when official targets are synced (`distribution_id` is required on Target Detail).

## ERPNext Target Integration

Inspected ERPNext v16 `Target Detail` fields: `item_group`, `fiscal_year`, `target_qty`, `target_amount`, `distribution_id`. Custom fields added (not core):

- `custom_source_planning`
- `custom_planning_version`
- `custom_planning_key`
- `custom_approved_by`
- `custom_approved_on`

If `item_sales_target` is installed, the existing custom `item` field is populated.

## Achievement

Reports:

- **Sales Target Achievement** — salesperson / territory / item group / item
- **Sales Target Monthly Performance** — Monthly, Quarterly, Half-Yearly, YTD, Annual
- **Target Planning Audit** — versions, overrides, warnings, status

`Achievement % = Actual / Target × 100`. Zero targets return empty (not an error divide).

## Incentives

**Incentive Scheme** + **Incentive Scheme Slab** store min/max achievement bands and separate min/max incentive rates. Payout is calculated on **Sales Target Achievement** (not stored on Sales Target Planning): surplus above target × the matching rate. Below min achievement, incentive is 0.

## Testing

```bash
bench --site ss.frappe.my run-tests --app sales_performance
```

Engine tests cover growth, distribution rounding, returns netting, pricing averages, override/lock rules, and duplicate-key matching. Full invoice integration tests are skipped unless ERPNext test masters exist.

## Upgrade Safety

- Does not modify `apps/erpnext` or `apps/frappe`
- ERPNext access is isolated in `sales_performance/services/`
- Survives ERPNext updates as long as Sales Invoice, Sales Team, Item Price, and Target Detail public fields remain

## Example

Previous year net qty 10,000 KG, growth 15%, price list rate 260:

- Target Qty = 11,500
- Target Amount = 11,500 × 260 = 2,990,000
- Previous year amount 2,400,000 stays as historical reference (not 2,400,000 × 1.15)
