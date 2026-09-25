"""Unit tests for the inventory engine in inventory_manager.py.

These cover only the non-GUI classes -- InventoryItem and
AdvancedInventoryManager -- which are deliberately decoupled from Tkinter.
"""

import os
import sys
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inventory_manager import (  # noqa: E402
    BULK_REORDER_QUANTITY,
    REORDER_BUFFER,
    AdvancedInventoryManager,
    InventoryItem,
)


def make_item(item_id="SKU-1", name="Widget", stock=10, price=9.99, threshold=3):
    return InventoryItem(item_id, name, stock, price, threshold)


class InventoryItemTests(unittest.TestCase):
    def test_exposes_initial_values(self):
        item = make_item()
        self.assertEqual(item.item_id, "SKU-1")
        self.assertEqual(item.name, "Widget")
        self.assertEqual(item.stock, 10)
        self.assertAlmostEqual(item.price, 9.99)
        self.assertEqual(item.reorder_threshold, 3)

    def test_rejects_blank_name(self):
        item = make_item()
        with self.assertRaises(ValueError):
            item.name = "   "
        self.assertEqual(item.name, "Widget")

    def test_construction_rejects_blank_name(self):
        with self.assertRaises(ValueError):
            make_item(name="   ")

    def test_construction_rejects_blank_item_id(self):
        with self.assertRaises(ValueError):
            make_item(item_id="   ")

    def test_construction_rejects_negative_stock(self):
        with self.assertRaises(ValueError):
            make_item(stock=-1)

    def test_construction_rejects_negative_price(self):
        with self.assertRaises(ValueError):
            make_item(price=-0.01)

    def test_construction_rejects_negative_threshold(self):
        with self.assertRaises(ValueError):
            make_item(threshold=-1)

    def test_rejects_negative_price(self):
        item = make_item()
        with self.assertRaises(ValueError):
            item.price = -1.0
        self.assertAlmostEqual(item.price, 9.99)

    def test_rejects_negative_threshold(self):
        item = make_item()
        with self.assertRaises(ValueError):
            item.reorder_threshold = -5
        self.assertEqual(item.reorder_threshold, 3)

    def test_adjust_stock_applies_delta_and_returns_new_total(self):
        item = make_item(stock=10)
        self.assertEqual(item.adjust_stock(5), 15)
        self.assertEqual(item.adjust_stock(-3), 12)
        self.assertEqual(item.stock, 12)

    def test_adjust_stock_refuses_to_go_negative(self):
        item = make_item(stock=2)
        with self.assertRaises(ValueError):
            item.adjust_stock(-3)
        self.assertEqual(item.stock, 2, "stock must be unchanged after a rejected sale")

    def test_requires_reorder_is_inclusive_of_threshold(self):
        self.assertFalse(make_item(stock=4, threshold=3).requires_reorder)
        self.assertTrue(make_item(stock=3, threshold=3).requires_reorder)
        self.assertTrue(make_item(stock=1, threshold=3).requires_reorder)

    def test_concurrent_adjustments_do_not_lose_updates(self):
        item = make_item(stock=0)

        def add_one_hundred():
            for _ in range(100):
                item.adjust_stock(1)

        threads = [threading.Thread(target=add_one_hundred) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(item.stock, 800)


class SearchAndReportTests(unittest.TestCase):
    def setUp(self):
        self.manager = AdvancedInventoryManager()
        self.manager.add_item(make_item("B-2", "Beta", stock=5, price=30.0))
        self.manager.add_item(make_item("A-1", "Alpha", stock=20, price=10.0))
        self.manager.add_item(make_item("C-3", "Gamma", stock=12, price=20.0))

    def test_get_item_finds_by_sku(self):
        self.assertEqual(self.manager.get_item("A-1").name, "Alpha")

    def test_get_item_raises_for_unknown_sku(self):
        with self.assertRaises(KeyError):
            self.manager.get_item("NOPE")

    def test_adding_existing_sku_restocks_instead_of_duplicating(self):
        self.manager.add_item(make_item("A-1", "Alpha", stock=5))
        self.assertEqual(self.manager.get_item("A-1").stock, 25)
        self.assertEqual(len(self.manager.generate_scanned_report()), 3)

    def test_merge_sort_orders_by_each_key(self):
        by_id = [i.item_id for i in self.manager.generate_scanned_report("id")]
        self.assertEqual(by_id, ["A-1", "B-2", "C-3"])

        by_name = [i.name for i in self.manager.generate_scanned_report("name")]
        self.assertEqual(by_name, ["Alpha", "Beta", "Gamma"])

        by_stock = [i.stock for i in self.manager.generate_scanned_report("stock")]
        self.assertEqual(by_stock, sorted(by_stock))

        by_price = [i.price for i in self.manager.generate_scanned_report("price")]
        self.assertEqual(by_price, sorted(by_price))

    def test_merge_sort_handles_empty_and_single_item(self):
        empty = AdvancedInventoryManager()
        self.assertEqual(empty.generate_scanned_report(), [])

        single = AdvancedInventoryManager()
        single.add_item(make_item("ONLY"))
        self.assertEqual([i.item_id for i in single.generate_scanned_report()], ["ONLY"])

    def test_merge_sort_keeps_every_item(self):
        manager = AdvancedInventoryManager()
        for n in range(25):
            manager.add_item(make_item(f"SKU-{n:02d}", stock=25 - n))
        report = manager.generate_scanned_report("stock")
        self.assertEqual(len(report), 25)
        self.assertEqual(len({i.item_id for i in report}), 25)

    def test_merge_sort_is_stable_for_tied_keys(self):
        """Regression: the merge step used strict '<', so tied keys got
        reordered instead of keeping their original relative order."""
        manager = AdvancedInventoryManager()
        for item_id in ("E-5", "D-4", "C-3", "B-2", "A-1"):
            manager.add_item(make_item(item_id, stock=10, price=5.0))

        original_order = ["E-5", "D-4", "C-3", "B-2", "A-1"]
        by_stock = [i.item_id for i in manager.generate_scanned_report("stock")]
        self.assertEqual(by_stock, original_order)

        by_price = [i.item_id for i in manager.generate_scanned_report("price")]
        self.assertEqual(by_price, original_order)


class SaleAndReorderTests(unittest.TestCase):
    def setUp(self):
        self.manager = AdvancedInventoryManager()

    def test_sale_reduces_stock_without_reorder_when_above_threshold(self):
        self.manager.add_item(make_item("A", stock=20, threshold=5))
        self.assertFalse(self.manager.record_sale("A", 5))
        self.assertEqual(self.manager.get_item("A").stock, 15)

    def test_sale_hitting_threshold_triggers_reorder(self):
        self.manager.add_item(make_item("A", stock=10, threshold=5))
        self.assertTrue(self.manager.record_sale("A", 5))
        self.assertGreater(self.manager.get_item("A").stock, 5)

    def test_oversized_sale_is_rejected_and_leaves_stock_intact(self):
        self.manager.add_item(make_item("A", stock=3, threshold=1))
        with self.assertRaises(ValueError):
            self.manager.record_sale("A", 10)
        self.assertEqual(self.manager.get_item("A").stock, 3)

    def test_reorder_clears_a_threshold_larger_than_the_bulk_quantity(self):
        """The regression this guards: a flat bulk order left high-threshold
        items permanently below their reorder point."""
        high = BULK_REORDER_QUANTITY * 3
        self.manager.add_item(make_item("A", stock=high, threshold=high))
        self.manager.record_sale("A", 1)

        item = self.manager.get_item("A")
        self.assertFalse(item.requires_reorder,
                         "item should be clear of its threshold after reordering")
        self.assertGreaterEqual(item.stock, high + REORDER_BUFFER)

    def test_reorder_uses_bulk_quantity_for_small_thresholds(self):
        self.manager.add_item(make_item("A", stock=5, threshold=5))
        self.manager.record_sale("A", 0)
        self.assertEqual(self.manager.get_item("A").stock, 5 + BULK_REORDER_QUANTITY)

    def test_repeated_sales_never_leave_the_item_flagged(self):
        self.manager.add_item(make_item("A", stock=60, threshold=55))
        for _ in range(20):
            self.manager.record_sale("A", 3)
            self.assertFalse(self.manager.get_item("A").requires_reorder)

    def test_auto_reorder_is_a_noop_once_stock_already_clears_threshold(self):
        """Guards a double-reorder race: two concurrent sales can both see an
        item below threshold and both call auto_reorder; the second call
        must not add another bulk order on top of stock the first already
        replenished."""
        self.manager.add_item(make_item("A", stock=2, threshold=5))
        item = self.manager.get_item("A")

        self.manager.auto_reorder(item)
        stock_after_first_reorder = item.stock
        self.assertFalse(item.requires_reorder)

        self.manager.auto_reorder(item)
        self.assertEqual(item.stock, stock_after_first_reorder,
                          "a second reorder on an already-cleared item must be a no-op")

    def test_concurrent_sales_never_double_reorder(self):
        """Two threads racing record_sale on the same item, each crossing the
        threshold, must not each add a full bulk order -- only enough stock
        to clear the threshold once should be purchased in total."""
        self.manager.add_item(make_item("A", stock=10, threshold=8))

        def sell_one():
            self.manager.record_sale("A", 1)

        threads = [threading.Thread(target=sell_one) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        item = self.manager.get_item("A")
        self.assertFalse(item.requires_reorder)
        self.assertLessEqual(item.stock, 8 + BULK_REORDER_QUANTITY + REORDER_BUFFER,
                              "stock implies more than one bulk reorder was applied")


class EditAndAuditTests(unittest.TestCase):
    def setUp(self):
        self.manager = AdvancedInventoryManager()
        self.manager.add_item(make_item("A", "Alpha", price=10.0, threshold=4))

    def test_edit_applies_only_the_supplied_fields(self):
        self.manager.edit_item("A", price=25.5)
        item = self.manager.get_item("A")
        self.assertAlmostEqual(item.price, 25.5)
        self.assertEqual(item.name, "Alpha")
        self.assertEqual(item.reorder_threshold, 4)

    def test_edit_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            self.manager.edit_item("A", price=-3.0)

    def test_edit_of_unknown_sku_raises(self):
        with self.assertRaises(KeyError):
            self.manager.edit_item("MISSING", price=1.0)

    def test_every_action_is_audited(self):
        start = len(self.manager.audit_logs)
        self.manager.record_sale("A", 1)
        self.manager.edit_item("A", threshold=2)
        self.assertGreater(len(self.manager.audit_logs), start)

    def test_no_op_edit_writes_no_audit_entry(self):
        start = len(self.manager.audit_logs)
        self.manager.edit_item("A")
        self.assertEqual(len(self.manager.audit_logs), start)

    def test_concurrent_logging_keeps_every_entry(self):
        """log_event is called from paths that already hold the global lock, so
        it needs its own lock -- and must not drop entries under contention."""
        manager = AdvancedInventoryManager()

        def log_many():
            for n in range(200):
                manager.log_event(f"event {n}")

        threads = [threading.Thread(target=log_many) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(manager.audit_logs), 1200)

    def test_reorder_does_not_deadlock_while_logging(self):
        """auto_reorder logs while holding the global lock; a shared lock would hang."""
        manager = AdvancedInventoryManager()
        manager.add_item(make_item("A", stock=5, threshold=5))

        done = threading.Event()

        def run_sale():
            manager.record_sale("A", 1)
            done.set()

        thread = threading.Thread(target=run_sale, daemon=True)
        thread.start()
        self.assertTrue(done.wait(timeout=5), "record_sale deadlocked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
