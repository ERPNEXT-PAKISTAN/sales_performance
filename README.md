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
        → Incentive calculation → posted payout → payment tracking
```

**Do not** compute target amount as previous-year amount × growth. Quantity and selling rate are planned independently.

## Installation

From the bench:

```bash
cd /home/frappe/frappe-bench
bench get-app /path/to/sales_performance   # if installing from git
bench --site site1.local install-app sales_performance
bench --site site1.local migrate
bench --site site1.local clear-cache
```

On this computer the app lives at `apps/sales_performance`.

Required: ERPNext. Optional: `item_sales_target` (adds Item on Target Detail so official targets can be item-wise).

## Update an existing installation

Run these commands on the server from the bench directory. Replace `site1.local` with your site name. Repeat the `migrate` and `clear-cache` commands for each site where `sales_performance` is installed.

```bash
cd /home/frappe/frappe-bench
git -C apps/sales_performance pull --ff-only
bench --site site1.local migrate
bench build --app sales_performance
bench --site site1.local clear-cache
bench restart
```

The Git pull uses the configured tracking branch. Install the app only on a new site; an existing installation needs the migration above.

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

- Same Month Previous Year + Growth (preserves seasonality)
- Equal Monthly (current default) / Quarterly / Half-Yearly (monthly slots always sum to the annual target)
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
bench --site site1.local run-tests --app sales_performance
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

## Personal and manager views

- **My Sales** (`/app/my-sales`) provides month-by-month personal targets, attributed invoice sales, incentive estimates, payout status, target acknowledgements and questions to managers.
- **Sales Performance Overview** (`/app/sales-performance-overview`) provides a scoped team heatmap, target/actual cards, payout totals, approval queue and unanswered questions. Existing detailed reports remain available.
- Customer Group starts at **Market** and can be cleared. Numbers display with zero decimals; thresholds use unrounded comparisons.
- My Sales uses **approved plans only**. Managers can inspect provisional targets, which are labelled. Approving a plan remains an explicit manager action.

### Access setup

Assign the appropriate existing Sales User/manager role. For personal mapping, link User → active Employee → enabled Sales Person. Alternatively, create **Sales Performance Assignment** with User, Company and Sales Person. Enable **Include Sales Person Subtree** to grant an explicitly assigned team. Administrator, System Manager and Sales Performance Admin can view all people; other accounts require a mapping. Unmapped users receive no sales data.

All dashboard/report data requests enforce this scope on the server. Direct planning/payout document access also checks the entire document's sales-person scope; mixed-person documents may be visible only to a manager with the complete assigned team. The personal page exposes only the person's share. Broad All/Desk User permissions on app business records are removed during setup/migration.

### Payout controls

Qty incentive calculations produce incentive units. A new Qty payout needs **Currency per Incentive Unit** before submission; monetary payable is units × that rate. Existing submitted payouts are not converted or rewritten. Reload legacy drafts with **Get Incentives** before submitting so approved source rows and the scheme are recorded.

Submission saves a calculation snapshot and rejects overlapping submitted entitlements (including overlapping monthly/quarterly/annual scopes). Cancel or reconcile a previous payout before posting the same entitlement again. The overlap check serializes submissions per company. Payout totals include all matching detail rows; only the displayed document history is limited to 100 records.

### Daily use

Sales persons can acknowledge approved targets and ask questions from My Sales. Managers answer questions or create person-specific announcements through **Sales Performance Update**. Approved-plan/revision and payout events appear in the personal Updates tab. Visible pages refresh every minute; no email or push channel is configured by this feature.

The manager approval queue links to plans and compares revisions before approval. Achievement Graphics can prioritize largest gaps, lowest achievement or highest achievement. Dashboard **Save View / Load View** stores filters in the current browser under the signed-in user. Monthly Incentives includes an **Explain Incentives** action.
