"""Target edits conserve allocations and enforce amendment boundaries."""
import unittest
import io
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import frappe

from sales_performance.services.target_editor import normalize, transfer, apply_snapshot
from sales_performance.services.target_sync import _percentages
from sales_performance.api.target_editing import (
    validate_effective_month, import_rows, read_import, approver, target_amender,
    _apply_annual_amendments_to_months,
    _scale_months_to_total,
)


class Row(frappe._dict):
    def as_dict(self):
        return dict(self)


class Plan(Row):
    def set(self, key, value):
        self[key] = [Row(r) for r in value] if isinstance(value, list) else value

    def append(self, key, value):
        row = Row(value)
        self.setdefault(key, []).append(row)
        return row


def fail(message, *args, **kwargs):
    raise ValueError(message)


class TestTargetEditor(unittest.TestCase):
    def setUp(self):
        self.db = MagicMock()
        patch.object(frappe, "db", self.db).start()
        self.db.get_value.side_effect = lambda doctype, *args, **kwargs: Row(item_name="Widget", item_group="Products", stock_uom="Nos") if doctype == "Item" else 1
        patch.object(frappe, "throw", side_effect=fail).start()
        self.last_prices = patch("sales_performance.services.pricing_engine.prefetch_last_selling", return_value={}).start()
        self.addCleanup(patch.stopall)
        self.doc = Plan(company="Test", fiscal_year="2026", target_source="Manual", entry_basis="Annual",
            value_basis="Quantity and Rate", distribution_method="Equal Monthly", proposal_details=[], monthly_details=[], custom_percents=[])
        self.doc.append("proposal_details", dict(sales_person="Alice", item_code="Widget", approved_target_qty=120, approved_target_rate=10))

    def test_manual_annual_creates_linked_months(self):
        normalize(self.doc)
        self.assertEqual(len(self.doc.monthly_details), 12)
        self.assertEqual(sum(m.target_qty for m in self.doc.monthly_details), 120)
        self.assertEqual(sum(m.target_amount for m in self.doc.monthly_details), 1200)
        self.assertTrue(all(m.row_key == self.doc.proposal_details[0].row_key for m in self.doc.monthly_details))

    def test_zero_rate_falls_back_to_last_invoice(self):
        self.doc.proposal_details[0].approved_target_rate = 0
        self.last_prices.return_value = {"Widget": {"rate": 7, "price_source": "Last Selling Invoice", "price_reference": "INV-1"}}
        normalize(self.doc)
        self.assertEqual(self.doc.proposal_details[0].approved_target_rate, 7)
        self.assertEqual(self.doc.total_approved_amount, 840)
        self.assertEqual(sum(m.target_amount for m in self.doc.monthly_details), 840)
        self.assertEqual(self.doc.proposal_details[0].price_reference, "INV-1")

    def test_zero_rate_without_sales_remains_zero(self):
        self.doc.proposal_details[0].approved_target_rate = 0
        normalize(self.doc)
        self.assertEqual(self.doc.total_approved_qty, 120)
        self.assertEqual(self.doc.total_approved_amount, 0)

    def test_fallback_preserves_protected_months(self):
        self.doc.proposal_details[0].approved_target_rate = 0
        normalize(self.doc)
        self.doc.entry_basis = "Monthly"
        self.last_prices.return_value = {"Widget": {"rate": 7}}
        normalize(self.doc, pricing_start_month=7)
        self.assertEqual([m.target_amount for m in self.doc.monthly_details[:6]], [0] * 6)
        self.assertEqual([m.target_amount for m in self.doc.monthly_details[6:]], [70] * 6)
        normalize(self.doc)
        self.assertEqual(self.doc.total_approved_amount, 420)

    def test_explicit_positive_rate_and_amount_basis_are_preserved(self):
        normalize(self.doc)
        self.last_prices.assert_not_called()
        self.doc.value_basis = "Quantity and Amount"
        self.doc.proposal_details[0].approved_target_amount = 0
        normalize(self.doc)
        self.last_prices.assert_not_called()
        self.assertEqual(self.doc.total_approved_amount, 0)

    def test_annual_edit_updates_months(self):
        normalize(self.doc)
        self.doc.proposal_details[0].approved_target_qty = 240
        normalize(self.doc)
        self.assertEqual(sum(m.target_qty for m in self.doc.monthly_details), 240)

    def test_annual_rounding_is_stable_across_saves(self):
        row = self.doc.proposal_details[0]
        row.approved_target_qty = 10.4
        normalize(self.doc)
        self.assertEqual(row.approved_target_qty, 10)
        self.assertEqual(row.approved_target_amount, 100)
        normalize(self.doc)
        self.assertEqual(row.approved_target_amount, 100)
        self.assertEqual(sum(m.target_amount for m in self.doc.monthly_details), 100)

    def test_amount_entry_rate_uses_rounded_quantity(self):
        row = self.doc.proposal_details[0]
        self.doc.value_basis = "Quantity and Amount"
        row.approved_target_qty = 10.4
        row.approved_target_amount = 104
        normalize(self.doc)
        self.assertEqual(row.approved_target_rate, 10.4)
        normalize(self.doc)
        self.assertEqual(row.approved_target_rate, 10.4)

    def test_import_rejects_conflicting_amount_with_zero_quantity(self):
        self.doc.proposal_details = []
        data = [dict(sales_person="Alice", item_code="Widget", target_qty=0, target_rate=10, target_amount=100)]
        with patch("sales_performance.api.target_editing.read_import", return_value=data):
            with self.assertRaisesRegex(ValueError, "does not equal Amount"):
                import_rows(self.doc, {"layout": "Annual", "mode": "Append"})

    def test_small_whole_number_targets_never_create_negative_months(self):
        self.doc.proposal_details[0].approved_target_qty = 10
        normalize(self.doc)
        self.assertEqual(sum(m.target_qty for m in self.doc.monthly_details), 10)
        self.assertTrue(all(m.target_qty >= 0 for m in self.doc.monthly_details))

    def test_monthly_entry_rolls_up_and_preserves_varying_rates(self):
        normalize(self.doc)
        self.doc.entry_basis = "Monthly"
        self.doc.monthly_details[0].target_rate = 20
        normalize(self.doc)
        self.assertEqual(self.doc.proposal_details[0].approved_target_amount, 1300)
        self.assertEqual(self.doc.monthly_details[0].target_amount, 200)

    def test_july_transfer_conserves_totals_and_past(self):
        result = transfer(self.doc, "Alice", "Bob", 7)
        self.assertEqual(result["quantity"], 60)
        alice = [m for m in self.doc.monthly_details if m.sales_person == "Alice"]
        bob = [m for m in self.doc.monthly_details if m.sales_person == "Bob"]
        self.assertEqual([m.target_qty for m in alice], [10] * 6 + [0] * 6)
        self.assertEqual([m.target_qty for m in bob], [0] * 6 + [10] * 6)
        self.assertEqual(sum(m.target_amount for m in alice + bob), 1200)

    def test_partial_transfer_merges_existing_target(self):
        self.doc.append("proposal_details", dict(sales_person="Bob", item_code="Widget", approved_target_qty=120, approved_target_rate=20))
        transfer(self.doc, "Alice", "Bob", 7, 50)
        self.assertEqual(len(self.doc.proposal_details), 2)
        bob = next(r for r in self.doc.proposal_details if r.sales_person == "Bob")
        self.assertEqual(bob.approved_target_qty, 150)
        self.assertEqual(bob.approved_target_amount, 2700)
        self.assertEqual(sum(r.approved_target_amount for r in self.doc.proposal_details), 3600)

    def test_selected_transfer_survives_unsaved_identity_edit(self):
        normalize(self.doc)
        row = self.doc.proposal_details[0]
        old_key = row.row_key
        row.territory = "New Territory"
        result = transfer(self.doc, "Alice", "Bob", 7, 50, [old_key])
        self.assertEqual(result, {"quantity": 30, "amount": 300, "rows": 1})
        self.assertEqual(sum(r.approved_target_amount for r in self.doc.proposal_details), 1200)
        self.assertTrue(all(r.territory == "New Territory" for r in self.doc.proposal_details))

    def test_missing_source_explains_pending_editor_state(self):
        with self.assertRaisesRegex(ValueError, "no target rows in the current editor"):
            transfer(self.doc, "Removed Person", "Bob", 7)

    def test_selected_rows_cannot_silently_include_another_person(self):
        self.doc.append("proposal_details", dict(sales_person="Charlie", item_code="Widget", approved_target_qty=120, approved_target_rate=20))
        normalize(self.doc)
        keys = [r.row_key for r in self.doc.proposal_details]
        with self.assertRaisesRegex(ValueError, "must all belong"):
            transfer(self.doc, "Alice", "Bob", 7, 100, keys)
        self.assertEqual(sum(r.approved_target_amount for r in self.doc.proposal_details), 3600)

    def test_selected_transfer_preserves_unselected_rows(self):
        self.doc.append("proposal_details", dict(sales_person="Alice", territory="Other", item_code="Widget", approved_target_qty=240, approved_target_rate=20))
        normalize(self.doc)
        key = self.doc.proposal_details[0].row_key
        result = transfer(self.doc, "Alice", "Bob", 10, 100, [key])
        self.assertEqual(result, {"quantity": 30, "amount": 300, "rows": 1})
        other = next(r for r in self.doc.proposal_details if r.territory == "Other")
        self.assertEqual(other.approved_target_amount, 4800)
        self.assertEqual(sum(r.approved_target_amount for r in self.doc.proposal_details), 6000)

    def test_repeat_full_transfer_rejects_empty_remaining_targets(self):
        transfer(self.doc, "Alice", "Bob", 7)
        with self.assertRaisesRegex(ValueError, "no targets from the effective month"):
            transfer(self.doc, "Alice", "Bob", 7)

    def test_identity_edit_relinks_months(self):
        normalize(self.doc)
        self.doc.entry_basis = "Monthly"
        self.doc.proposal_details[0].sales_person = "Bob"
        normalize(self.doc)
        self.assertTrue(all(m.sales_person == "Bob" for m in self.doc.monthly_details))
        self.assertTrue(all(m.row_key == self.doc.proposal_details[0].row_key for m in self.doc.monthly_details))

    def test_deleting_proposal_removes_its_months_and_totals(self):
        self.doc.append("proposal_details", dict(sales_person="Bob", item_code="Widget", approved_target_qty=240, approved_target_rate=20))
        normalize(self.doc)
        deleted_key = self.doc.proposal_details[0].row_key
        self.doc.proposal_details.pop(0)
        normalize(self.doc)
        self.assertEqual(len(self.doc.monthly_details), 12)
        self.assertFalse(any(m.row_key == deleted_key for m in self.doc.monthly_details))
        self.assertEqual(self.doc.total_approved_qty, 240)
        self.assertEqual(self.doc.total_approved_amount, 4800)

    def test_duplicate_and_negative_rejected(self):
        self.doc.append("proposal_details", dict(self.doc.proposal_details[0]))
        with self.assertRaisesRegex(ValueError, "Duplicate target"):
            normalize(self.doc)
        self.doc.proposal_details.pop()
        self.doc.proposal_details[0].approved_target_qty = -1
        with self.assertRaisesRegex(ValueError, "non-negative"):
            normalize(self.doc)

    def test_manual_distribution_mismatch_is_not_silently_replaced(self):
        normalize(self.doc)
        self.doc.distribution_method = "Manual Monthly"
        self.doc.proposal_details[0].approved_target_qty = 240
        with self.assertRaisesRegex(ValueError, "Monthly totals"):
            normalize(self.doc)

    def test_amendment_blocks_earlier_months(self):
        before = {"monthly_details": [{"sales_person": "Alice", "item_code": "Widget", "month_number": 1, "target_qty": 10}]}
        after = {"monthly_details": [{"sales_person": "Alice", "item_code": "Widget", "month_number": 1, "target_qty": 20}]}
        with self.assertRaisesRegex(ValueError, "before the effective month"):
            validate_effective_month(before, after, 7)
        validate_effective_month(before, after, 1)

    def test_snapshot_cannot_change_approval_or_actuals(self):
        self.doc.status = "Approved"
        apply_snapshot(self.doc, {"status": "Draft", "approved_by": "attacker", "monthly_details": [{"actual_qty": 999, "target_qty": 10}]})
        self.assertEqual(self.doc.status, "Approved")
        self.assertIsNone(self.doc.approved_by)
        self.assertIsNone(self.doc.monthly_details[0].actual_qty)

    def test_distribution_does_not_allocate_to_transferred_out_months(self):
        transfer(self.doc, "Alice", "Bob", 7)
        p = _percentages(self.doc, self.doc.proposal_details[0], "target_qty")
        self.assertAlmostEqual(sum(p), 100)
        self.assertEqual(p[6:], [0] * 6)

    def test_annual_import_amount_and_append_conflict(self):
        self.doc.proposal_details = []
        data = [dict(sales_person="Alice", item_code="Widget", target_qty=120, target_amount=1800)]
        with patch("sales_performance.api.target_editing.read_import", return_value=data):
            import_rows(self.doc, {"layout": "Annual", "mode": "Append"})
            self.assertEqual(self.doc.proposal_details[0].approved_target_rate, 15)
            with self.assertRaisesRegex(ValueError, "already exists"):
                import_rows(self.doc, {"layout": "Annual", "mode": "Append"})

    def test_monthly_import_partial_year(self):
        self.doc.proposal_details = []
        data = [dict(sales_person="Bob", item_code="Widget", month=7, target_qty=30, target_rate=10)]
        with patch("sales_performance.api.target_editing.read_import", return_value=data):
            import_rows(self.doc, {"layout": "Monthly", "mode": "Append"})
        self.assertEqual(self.doc.proposal_details[0].approved_target_qty, 30)
        self.assertEqual(self.doc.monthly_details[6].target_amount, 300)
        self.assertEqual(self.doc.monthly_details[0].target_qty, 0)

    def test_annual_import_preserves_other_manual_allocations(self):
        transfer(self.doc, "Alice", "Bob", 7)
        data = [dict(sales_person="Charlie", item_code="Widget", target_qty=120, target_rate=20)]
        with patch("sales_performance.api.target_editing.read_import", return_value=data):
            import_rows(self.doc, {"layout": "Annual", "mode": "Append"})
        self.assertEqual([m.target_qty for m in self.doc.monthly_details if m.sales_person == "Alice"], [10] * 6 + [0] * 6)
        self.assertEqual([m.target_qty for m in self.doc.monthly_details if m.sales_person == "Bob"], [0] * 6 + [10] * 6)

    def test_xlsx_parser_reads_attached_workbook(self):
        from openpyxl import Workbook
        book = Workbook()
        book.active.append(["sales_person", "item_code", "target_qty", "target_rate"])
        book.active.append(["Alice", "Widget", 120, 10])
        content = io.BytesIO()
        book.save(content)
        file = SimpleNamespace(file_name="targets.xlsx", get_content=lambda: content.getvalue(), check_permission=lambda _: None)
        self.db.get_value.side_effect = None
        self.db.get_value.return_value = "attached-file"
        with patch.object(frappe, "get_doc", return_value=file):
            self.assertEqual(read_import("PLAN", "/private/files/targets.xlsx")[0]["target_qty"], 120)
        self.db.get_value.return_value = None
        with self.assertRaisesRegex(ValueError, "attachment to this plan"):
            read_import("OTHER", "/private/files/targets.xlsx")

    def test_nonapprover_cannot_apply_amendments(self):
        with patch.object(frappe, "session", frappe._dict(user="author@example.com")), patch.object(frappe, "get_roles", return_value=["Sales Target User"]):
            with self.assertRaisesRegex(ValueError, "approver access"):
                approver()

    def test_only_sales_target_managers_can_amend_approved_plans(self):
        with patch.object(frappe, "session", frappe._dict(user="author@example.com")), patch.object(frappe, "get_roles", return_value=["Sales Target User"]):
            with self.assertRaisesRegex(ValueError, "Sales Target Manager access"):
                target_amender()
        with patch.object(frappe, "session", frappe._dict(user="editor@example.com")), patch.object(frappe, "get_roles", return_value=["Sales Target Manager"]):
            target_amender()

    def test_monthly_plan_annual_value_edit_preserves_month_shape(self):
        normalize(self.doc)
        self.doc.entry_basis = "Monthly"
        normalize(self.doc)
        row = self.doc.proposal_details[0]
        baseline = {"proposal_details": [dict(row)]}
        row.approved_target_qty = 240
        with patch("sales_performance.services.precision.get_qty_precision", return_value=0), patch(
            "sales_performance.services.precision.get_currency_precision", return_value=2
        ):
            _apply_annual_amendments_to_months(self.doc, baseline, 1)
        normalize(self.doc)
        self.assertEqual([month.target_qty for month in self.doc.monthly_details], [20] * 12)
        self.assertEqual(sum(month.target_amount for month in self.doc.monthly_details), 2400)

    def test_amendment_scaling_uses_real_child_documents(self):
        from sales_performance.sales_performance.doctype.sales_target_monthly_detail.sales_target_monthly_detail import SalesTargetMonthlyDetail
        # Bypass metadata loading, retaining real Document get/update semantics.
        months = []
        for n in range(1, 13):
            month = SalesTargetMonthlyDetail.__new__(SalesTargetMonthlyDetail)
            month.__dict__.update(month_number=n, target_qty=10, target_amount=100,
                                  _table_fieldnames={})
            months.append(month)
        _scale_months_to_total(months, "target_qty", 10, 1, 0)
        self.assertEqual(sum(m.target_qty for m in months), 10)
        self.assertTrue(all(m.target_qty >= 0 for m in months))
        _scale_months_to_total(months, "target_amount", 600.04, 7, 2)
        self.assertEqual([m.target_amount for m in months[:6]], [100] * 6)
        self.assertAlmostEqual(sum(m.target_amount for m in months), 600.04)
        self.assertTrue(all(m.target_amount >= 0 for m in months))

    def test_annual_amendment_keeps_months_before_effective_month(self):
        normalize(self.doc)
        self.doc.entry_basis = "Monthly"
        normalize(self.doc)
        row = self.doc.proposal_details[0]
        baseline = {"proposal_details": [dict(row)]}
        row.approved_target_qty = 180
        with patch("sales_performance.services.precision.get_qty_precision", return_value=0), patch(
            "sales_performance.services.precision.get_currency_precision", return_value=2
        ):
            _apply_annual_amendments_to_months(self.doc, baseline, 7)
        self.assertEqual([month.target_qty for month in self.doc.monthly_details[:6]], [10] * 6)
        self.assertEqual(sum(month.target_qty for month in self.doc.monthly_details), 180)

    def test_amendment_approval_skips_oversized_version_snapshot(self):
        from sales_performance.api import target_editing
        doc = SimpleNamespace(
            name="PLAN-1",
            flags=frappe._dict(),
            amendment_count=0,
            save=MagicMock(),
            db_set=MagicMock(),
        )
        record = SimpleNamespace(
            name="AMEND-1",
            base_modified="2026-01-01 00:00:00",
            modified="2026-01-02 00:00:00",
            before_values='{"monthly_details":[]}',
            proposed_values='{"monthly_details":[]}',
            effective_month=1,
            status="Under Review",
            amendment_number=0,
            approved_by=None,
            approved_on=None,
            save=MagicMock(),
        )
        with (
            patch.object(frappe, "session", frappe._dict(user="Administrator")),
            patch.object(target_editing, "approver"),
            patch.object(target_editing, "amendment_doc", return_value=(doc, record)),
            patch.object(target_editing, "edited"),
            patch.object(target_editing, "snapshot", return_value={"monthly_details": []}),
            patch.object(target_editing, "validate_effective_month"),
            patch.object(target_editing, "now_datetime", return_value="2026-01-03 00:00:00"),
            patch("sales_performance.services.target_sync.sync_official_targets"),
        ):
            target_editing.approve_amendment("PLAN-1", "AMEND-1", record.modified)
        doc.save.assert_called_once_with(ignore_version=True)
        self.assertEqual(record.status, "Applied")

    def test_client_boolean_flag_cannot_unlock_approved_document(self):
        from sales_performance.sales_performance.doctype.sales_target_planning.sales_target_planning import SalesTargetPlanning
        fake = SimpleNamespace(flags=frappe._dict(authorized_target_action=True), is_new=lambda: False,
            get_doc_before_save=lambda: Row(status="Approved"), status="Draft")
        with patch("sales_performance.sales_performance.doctype.sales_target_planning.sales_target_planning._", side_effect=lambda text: text), self.assertRaisesRegex(ValueError, "Amend Targets"):
            SalesTargetPlanning._guard_locked_edits(fake)

    def test_receiver_targets_combine_across_active_plans(self):
        from sales_performance.services.incentive_engine import combine_plan_months
        rows = [Row(parent="original", row_key="one", sales_person="Bob", item_code="Widget"),
                Row(parent="transfer", row_key="two", sales_person="Bob", item_code="Widget")]
        monthly = {("original", "one"): {7: {"target_qty": 20, "target_amount": 200}},
                   ("transfer", "two"): {7: {"target_qty": 10, "target_amount": 150}}}
        combined = combine_plan_months(rows, monthly)
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined[("Bob", "", "Widget", "")]["months"][7], {"target_qty": 30, "target_amount": 350})


if __name__ == "__main__":
    unittest.main()
