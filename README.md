# Enterprise Inventory Manager

![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

A desktop stock-control application built with Python and Tkinter. Register products, record sales and restocks, and watch the system automatically replenish any item whose stock falls to its reorder threshold — with every action written to a live audit trail.

Built for the **502IT** coursework as a demonstration of encapsulation, thread-safe state, and classic search/sort algorithms.

## Features

- **Product registration** with SKU, name, stock quantity, unit price, and a per-item reorder threshold.
- **Sales and restocks** applied against the selected row, with stock levels validated so they can never go negative.
- **Automatic reordering** — when a sale drops an item to or below its threshold, the system purchases replenishment stock without user intervention and reports it.
- **Live audit trail** — every registration, edit, sale, restock and auto-reorder is timestamped and shown in a terminal-style log pane.
- **Sortable inventory table** — re-sort by ID, name, stock or price using a hand-written merge sort.
- **Health status column** flagging which items are healthy and which have tripped their reorder rule.
- **Inline editing** of price and threshold for the selected item.
- **Zero dependencies** — Python standard library only.

## Implemented algorithms

| # | Algorithm | Complexity | Where |
|---|---|---|---|
| 1 | Product search — hash map lookup by SKU | O(1) | `AdvancedInventoryManager.get_item` |
| 2 | Stock update with non-negative guard | O(1) | `InventoryItem.adjust_stock` |
| 3 | Reorder threshold check | O(1) | `InventoryItem.requires_reorder` |
| 4 | Automatic reorder / replenishment | O(1) | `AdvancedInventoryManager.auto_reorder` |
| 5 | Merge sort over the inventory | O(n log n) | `AdvancedInventoryManager.merge_sort_inventory` |
| 6 | Linear scan for report generation | O(n) | `AdvancedInventoryManager.generate_scanned_report` |

Merge sort is implemented from scratch — recursive split plus an explicit `_merge` step — rather than delegating to `sorted()`, and takes the sort key as a parameter so one implementation serves all four columns.

## Architecture

The domain layer is fully decoupled from the GUI, so the inventory engine can be imported and tested without Tkinter.

```
InventoryItem              A single product. SKU, stock, price, name and threshold
                           are private attributes exposed through validating
                           properties (a blank SKU or name, and negative prices or
                           thresholds, are rejected at construction or the setter).
                           Each instance carries its own threading.Lock, so
                           concurrent readers and writers of one product are
                           serialised.

AdvancedInventoryManager   Owns the SKU -> InventoryItem hash map behind a global
                           lock, plus the audit log. Provides search, edit, sale,
                           restock, auto-reorder, merge sort and report generation.

InventoryApp (tk.Tk)       Three-panel layout: registration and stock-operation
                           forms on the left, inventory table and audit log on the
                           right.
```

### On thread safety

Locking is built in at both levels — per-item locks for field mutation, a manager-level lock for the hash map itself — so the engine is safe to drive from multiple worker threads. The GUI currently exercises it single-threaded; the locking exists so the model can be reused under concurrency without changes.

## Running it

Requires Python 3.8+ with Tkinter (bundled with the standard Windows and macOS installers; on Debian/Ubuntu install `python3-tk`).

```bash
git clone https://github.com/sebastiansiju/inventory-management-system.git
```

```bash
cd inventory-management-system && python inventory_manager.py
```

## Usage

The app starts with three sample products already loaded — one of which (`CABL-03`, stock 5, threshold 10) is deliberately below its threshold so the reorder logic is visible immediately.

**Register a product** — fill in the *Add / Register Item* form and click **+ Add Item to Inventory**. Registering an SKU that already exists adds to its stock instead of creating a duplicate.

**Record a sale** — select a row in the table, set *Units Quantity*, and click **🛒 Record Sale**. If the sale takes stock to or below the threshold, an auto-reorder fires and a dialog tells you.

**Restock manually** — select a row, set the quantity, and click **📦 Manual Restock**.

**Edit an item** — select a row (the current price and threshold pre-fill), change either field, and click **✏️ Apply Edits**.

**Re-sort the table** — pick a key from the *Merge Sort By* dropdown.

Everything you do appears in the **System Audit Trail Logs** pane with a timestamp.

## Sample data

| SKU | Name | Stock | Price | Reorder threshold |
|---|---|---|---|---|
| SRVC-01 | Enterprise Server | 10 | $2,499.99 | 3 |
| SWCH-02 | Network Switch | 25 | $450.00 | 8 |
| CABL-03 | Cat6 Cable (10m) | 5 | $15.00 | 10 |

## Running the tests

The engine is decoupled from the GUI, so it is tested without a display:

```bash
python -m unittest discover -s tests -t . -v
```

35 tests cover the property validators (including that construction itself
rejects a blank ID or name, or a negative stock, price or threshold), stock
arithmetic and its non-negative guard, `O(1)` lookup, merge sort across all
four keys and its stability on tied keys, the reorder policy, the audit
trail, and the locking — including a concurrency test asserting that 8
threads doing 100 increments each land on exactly 800, a regression test
that a restocked item finishes clear of its threshold, and a pair of tests
guarding against a double reorder when two sales race on the same item.

## Project structure

```
inventory-management-system/
├── inventory_manager.py           # Inventory engine + Tkinter GUI
├── tests/
│   └── test_inventory_engine.py   # unittest coverage for the engine
├── .github/workflows/tests.yml    # CI: runs the suite on every push
├── README.md
└── .gitignore
```

## License

MIT
