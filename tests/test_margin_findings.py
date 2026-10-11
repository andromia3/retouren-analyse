import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import befunde
import retouren_analyse


class MarginFindingTests(unittest.TestCase):
    def finding(self, returned_quantity):
        args = SimpleNamespace(prozesskosten=10.0, rueckgabefenster=60,
                               min_retouren=3, reifepuffer=21)
        sales = [dict(sales_order_number='order-1', order_date='2026-01-01',
                      product_number='sku-1', product_name='Artikel', quantity='10',
                      net_revenue='1000', unit_cost='40')]
        returns = [dict(return_number='return-1', sales_order_number='order-1',
                        return_date='2026-02-01', product_number='sku-1',
                        product_name='Artikel', quantity_returned=str(returned_quantity),
                        refund_amount=str(returned_quantity * 100), return_reason='unwanted')]
        analysis = retouren_analyse.analyze(returns, sales, args)
        return analysis, befunde.sammle(analysis)[0]

    def test_positive_contribution_is_not_reported_as_a_loss(self):
        analysis, finding = self.finding(8)
        self.assertEqual(analysis['kosten_top'][0]['deckungsbeitrag_nach_retouren'], 110)
        self.assertIn('110 EUR', finding['was'])
        self.assertIn('0 davon im Minus', finding['was'])
        self.assertNotIn('bei oder unter null', finding['was'])
        self.assertNotIn('nichts mehr', finding['titel'])
        self.assertNotIn('Jeder verkaufte Artikel', finding['warum'])

    def test_negative_contribution_remains_visible(self):
        analysis, finding = self.finding(10)
        self.assertEqual(analysis['kosten_top'][0]['deckungsbeitrag_nach_retouren'], -10)
        self.assertIn('1 davon im Minus', finding['was'])
        self.assertIn('-10 EUR', finding['was'])

    def test_healthy_contribution_does_not_trigger_margin_trap(self):
        analysis, _ = self.finding(1)
        self.assertFalse(any(f['id'] == 'marge_falle' for f in analysis['blinde_flecken']))


if __name__ == '__main__':
    unittest.main()
