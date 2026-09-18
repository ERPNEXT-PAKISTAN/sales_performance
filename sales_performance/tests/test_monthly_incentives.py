import unittest

from sales_performance.sales_performance.page.monthly_incentives.monthly_incentives import pivot_rows
from sales_performance.services.achievement_engine import compute_metrics
from sales_performance.services.incentive_engine import allocate_item_incentives, dashboard_totals


class TestMonthlyIncentives(unittest.TestCase):
    def test_monthly_allocation_reconciles_at_every_level(self):
        rows = []
        for person in ('A', 'B'):
            for month, period in ((1, 'January'), (2, 'February')):
                for item, actual in (('One', 200), ('Two', 300)):
                    rows.append(dict(compute_metrics(100, actual, 1000, actual * 10),
                                     sales_person=person, month_number=month, period=period,
                                     item_code=item, territory='North', customer_group='Retail'))
        slabs = [{'min_achievement_percent': 100, 'min_incentive_percent': 2}]
        for level in ('Grouped', 'Item'):
            for pay_on in ('Qty', 'Amount'):
                allocated = allocate_item_incentives(rows, slabs, 'Qty Achievement', pay_on, level)
                result = pivot_rows(allocated)
                expected = dashboard_totals(rows, slabs, 'Qty Achievement', pay_on, level)
                self.assertAlmostEqual(result['total'], expected['incentive_amount'])
                self.assertEqual(len(result['months_total']), 12)
                self.assertEqual(result['months_total'][2:], [0] * 10)
                for group in result['groups']:
                    self.assertEqual(group['total'], sum(item['total'] for item in group['items']))
                    for month in range(12):
                        self.assertEqual(group['months'][month], sum(item['months'][month] for item in group['items']))

    def test_item_dimensions_stay_separate_and_duplicate_months_add(self):
        base = dict(sales_person='A', item_code='One', month_number=12, incentive_amount=3)
        result = pivot_rows([dict(base, territory='North'), dict(base, territory='South'), dict(base, territory='North')])
        group = result['groups'][0]
        self.assertEqual(len(group['items']), 2)
        self.assertEqual(group['months'][11], 9)
        self.assertEqual([item['total'] for item in group['items']], [6, 3])
        self.assertEqual(pivot_rows([])['total'], 0)

    def test_achievement_filter_keeps_whole_items_and_reconciles_totals(self):
        from sales_performance.sales_performance.page.monthly_incentives.monthly_incentives import filter_achievement
        rows = [
            dict(sales_person='A', item_code='Earned', month_number=1, incentive_amount=4),
            dict(sales_person='A', item_code='Earned', month_number=2, incentive_amount=0),
            dict(sales_person='A', item_code='Zero', month_number=1, incentive_amount=0),
            dict(sales_person='B', item_code='Zero', month_number=1, incentive_amount=0),
        ]
        achieved = filter_achievement(pivot_rows(rows), 'Achieved')
        missed = filter_achievement(pivot_rows(rows), 'Not Achieved')
        self.assertEqual(achieved['total'], 4)
        self.assertEqual(len(achieved['groups']), 1)
        self.assertEqual([item['item_code'] for item in achieved['groups'][0]['items']], ['Earned'])
        self.assertEqual(achieved['groups'][0]['items'][0]['months'][1], 0)
        self.assertEqual(missed['total'], 0)
        self.assertEqual(len(missed['groups']), 2)
        self.assertTrue(all(item['item_code'] == 'Zero' for group in missed['groups'] for item in group['items']))
