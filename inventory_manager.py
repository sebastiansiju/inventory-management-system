import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import threading
from typing import Dict, List, Optional

# Replenishment policy. An auto-reorder buys at least BULK_REORDER_QUANTITY
# units, but always enough to finish REORDER_BUFFER units clear of the item's
# threshold so a restocked item is not immediately flagged as low again.
BULK_REORDER_QUANTITY = 50
REORDER_BUFFER = 10

# CORE LOGIC (OOP Data Structures & Thread-Safe Engine)


class InventoryItem:
    """Represents an encapsulated product with built-in thread safety."""
    
    def __init__(self, item_id: str, name: str, stock: int, price: float, reorder_threshold: int):
        """Creates a product, applying the same validation the properties
        enforce on later edits: a blank name, or a negative stock, price or
        threshold, is rejected up front rather than only on the next edit."""
        self._lock: threading.Lock = threading.Lock()
        self.item_id: str = item_id
        self.name = name
        if stock < 0:
            raise ValueError(f"Stock cannot be negative. Got: {stock}")
        self._stock: int = stock
        self.price = price
        self.reorder_threshold = reorder_threshold

    @property
    def name(self) -> str:
        """The product name."""
        with self._lock: return self._name

    @name.setter
    def name(self, new_name: str) -> None:
        """Sets the product name; rejects a blank or whitespace-only value."""
        if not new_name.strip(): raise ValueError("Name cannot be empty.")
        with self._lock: self._name = new_name

    @property
    def stock(self) -> int:
        """The current stock count. Use adjust_stock to change it."""
        with self._lock: return self._stock

    @property
    def price(self) -> float:
        """The unit price."""
        with self._lock: return self._price

    @price.setter
    def price(self, new_price: float) -> None:
        """Sets the unit price; rejects a negative value."""
        if new_price < 0: raise ValueError("Price cannot be negative.")
        with self._lock: self._price = new_price

    @property
    def reorder_threshold(self) -> int:
        """The stock level at or below which the item needs reordering."""
        with self._lock: return self._reorder_threshold

    @reorder_threshold.setter
    def reorder_threshold(self, new_threshold: int) -> None:
        """Sets the reorder threshold; rejects a negative value."""
        if new_threshold < 0: raise ValueError("Threshold cannot be negative.")
        with self._lock: self._reorder_threshold = new_threshold

    # --- ALGORITHM 2: Stock Update Algorithm ---
    def adjust_stock(self, amount: int) -> int:
        """Mutates stock safely and returns the updated stock count."""
        with self._lock:
            if self._stock + amount < 0:
                raise ValueError(f"Insufficient stock for '{self._name}'. Requested: {abs(amount)}, Available: {self._stock}")
            self._stock += amount
            return self._stock

    # --- ALGORITHM 3: Reorder Threshold-Checking Algorithm ---
    @property
    def requires_reorder(self) -> bool:
        """Evaluates if the current stock is critically low."""
        with self._lock:
            return self._stock <= self._reorder_threshold


class AdvancedInventoryManager:
    """Thread-safe inventory engine using hash map lookup O(1)."""
    
    def __init__(self):
        """Creates an empty manager with no items and no audit history."""
        self._inventory: Dict[str, InventoryItem] = {}
        self._global_lock: threading.Lock = threading.Lock()
        self.audit_logs: List[str] = []
        # The audit log gets its own lock rather than reusing _global_lock:
        # several callers append to it while already holding _global_lock, and
        # threading.Lock is not reentrant, so sharing one would deadlock.
        self._log_lock: threading.Lock = threading.Lock()

    def log_event(self, message: str) -> None:
        """Appends a timestamped entry to the audit trail."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._log_lock:
            self.audit_logs.append(f"[{timestamp}] {message}")

    def add_item(self, item: InventoryItem) -> None:
        """Registers a new item, or adds its stock to an existing SKU."""
        with self._global_lock:
            if item.item_id in self._inventory:
                self._inventory[item.item_id].adjust_stock(item.stock)
                self.log_event(f"RESTOCK: Added {item.stock} units to {item.item_id}.")
            else:
                self._inventory[item.item_id] = item
                self.log_event(f"NEW ITEM: Added {item.name} ({item.item_id}).")

    # --- ALGORITHM 1: Product Searching Algorithm ---
    def get_item(self, item_id: str) -> InventoryItem:
        """O(1) Hash Map Lookup to instantly find an item."""
        with self._global_lock:
            if item_id not in self._inventory:
                raise KeyError(f"Item {item_id} not found.")
            return self._inventory[item_id]

    def edit_item(self, item_id: str, name: Optional[str] = None, price: Optional[float] = None, threshold: Optional[int] = None) -> None:
        """Updates any of the given fields on an item and audits the change.
        Fields left as None are left untouched; if none are given, nothing
        is logged."""
        item = self.get_item(item_id) # Uses Searching Algorithm
        changes = []
        
        if name is not None:
            old_name = item.name
            item.name = name
            changes.append(f"Name: '{old_name}' -> '{name}'")
        if price is not None:
            old_price = item.price
            item.price = price
            changes.append(f"Price: ${old_price:.2f} -> ${price:.2f}")
        if threshold is not None:
            old_t = item.reorder_threshold
            item.reorder_threshold = threshold
            changes.append(f"Threshold: {old_t} -> {threshold}")
            
        if changes:
            self.log_event(f"EDIT [{item_id}]: {', '.join(changes)}")

    # --- ALGORITHM 4: Automatic Reorder Algorithm ---
    def auto_reorder(self, item: InventoryItem) -> None:
        """Automatically purchases stock to replenish depleted inventory.

        Orders whichever is larger: the standard bulk quantity, or however many
        units it takes to clear the item's threshold plus a buffer. A flat
        quantity would leave any item whose threshold exceeds that quantity
        permanently below its reorder point, re-triggering on every sale.
        """
        with self._global_lock:
            shortfall = item.reorder_threshold - item.stock
            reorder_amount = max(BULK_REORDER_QUANTITY, shortfall + REORDER_BUFFER)
            item.adjust_stock(reorder_amount)
            self.log_event(f"AUTO-REORDER: System purchased {reorder_amount} units for {item.item_id}.")

    def record_sale(self, item_id: str, quantity: int) -> bool:
        """Deducts a sale from stock, auto-reordering if it drops to or below
        the threshold. Returns whether an auto-reorder was triggered."""
        item = self.get_item(item_id) # Uses Searching Algorithm
        
        new_stock = item.adjust_stock(-quantity) # Uses Stock Update Algorithm
        self.log_event(f"SALE: Sold {quantity} of {item_id}. Remaining: {new_stock}")
        
        # Uses Reorder Threshold-Checking Algorithm
        if item.requires_reorder:
            self.auto_reorder(item) # Trigger Automatic Reorder Algorithm
            return True
            
        return False

    # --- ALGORITHM 5: Sorting Algorithm — Merge Sort ---
    def merge_sort_inventory(self, items: List[InventoryItem], sort_by: str = "id") -> List[InventoryItem]:
        """O(n log n) recursive merge sort implementation."""
        if len(items) <= 1:
            return items

        mid = len(items) // 2
        left_half = self.merge_sort_inventory(items[:mid], sort_by)
        right_half = self.merge_sort_inventory(items[mid:], sort_by)

        return self._merge(left_half, right_half, sort_by)

    def _merge(self, left: List[InventoryItem], right: List[InventoryItem], sort_by: str) -> List[InventoryItem]:
        sorted_list = []
        i = j = 0

        while i < len(left) and j < len(right):
            # Determine sorting key dynamically
            if sort_by == "stock":
                condition = left[i].stock < right[j].stock
            elif sort_by == "price":
                condition = left[i].price < right[j].price
            elif sort_by == "name":
                condition = left[i].name.lower() < right[j].name.lower()
            else:
                condition = left[i].item_id < right[j].item_id

            if condition:
                sorted_list.append(left[i])
                i += 1
            else:
                sorted_list.append(right[j])
                j += 1

        sorted_list.extend(left[i:])
        sorted_list.extend(right[j:])
        return sorted_list

    # --- ALGORITHM 6: Linear Scan Algorithm for Inventory Reports ---
    def generate_scanned_report(self, sort_by: str = "id") -> List[InventoryItem]:
        """O(n) linear scan to extract data, followed by O(n log n) Merge Sort."""
        with self._global_lock:
            # Linear scan extracting all values from the hash map
            items_list = list(self._inventory.values()) 
        
        return self.merge_sort_inventory(items_list, sort_by)


# GUI APPLICATION (Tkinter Frontend)


class InventoryApp(tk.Tk):
    def __init__(self) -> None:
        """Builds the window, the engine, and loads the sample catalogue."""
        super().__init__()
        self.title("502IT Problem 4: Enterprise Inventory Manager")
        self.geometry("1024x720")
        self.minsize(900, 650)
        self.configure(padx=10, pady=10)

        self.manager = AdvancedInventoryManager()
        self.current_sort = "id"
        self._build_layout()
        self._seed_sample_data()

    def _build_layout(self) -> None:
        left_panel = ttk.Frame(self, width=320)
        left_panel.pack(side="left", fill="y", padx=(0, 15))

        right_panel = ttk.Frame(self)
        right_panel.pack(side="right", fill="both", expand=True)

        self._build_form_panel(left_panel)
        self._build_table_panel(right_panel)

    def _build_form_panel(self, parent: ttk.Frame) -> None:
        # 1. Add Item Box
        form_frame = ttk.LabelFrame(parent, text=" Add / Register Item ", padding=15)
        form_frame.pack(fill="x", pady=(0, 15))

        self.var_id = tk.StringVar()
        self.var_name = tk.StringVar()
        self.var_stock = tk.StringVar(value="10")
        self.var_price = tk.StringVar(value="99.99")
        self.var_threshold = tk.StringVar(value="5")

        self._labeled_entry(form_frame, "Item ID (SKU):", self.var_id, 0)
        self._labeled_entry(form_frame, "Item Name:", self.var_name, 1)
        self._labeled_entry(form_frame, "Stock Quantity:", self.var_stock, 2)
        self._labeled_entry(form_frame, "Price ($):", self.var_price, 3)
        self._labeled_entry(form_frame, "Min Threshold:", self.var_threshold, 4)

        ttk.Button(form_frame, text="+ Add Item to Inventory", command=self._add_item).grid(row=5, column=0, columnspan=2, pady=(12, 0), sticky="ew")

        # 2. Transaction Box
        trans_frame = ttk.LabelFrame(parent, text=" Stock Operations ", padding=15)
        trans_frame.pack(fill="x", pady=(0, 15))

        self.var_op_qty = tk.StringVar(value="1")

        ttk.Label(trans_frame, text="Units Quantity:").grid(row=0, column=0, sticky="w")
        ttk.Entry(trans_frame, textvariable=self.var_op_qty, width=14).grid(row=0, column=1, pady=2, sticky="e")

        btn_row = ttk.Frame(trans_frame)
        btn_row.grid(row=1, column=0, columnspan=2, pady=(10, 0), sticky="ew")
        ttk.Button(btn_row, text="🛒 Record Sale", command=self._record_sale).pack(side="left", expand=True, fill="x", padx=(0, 5))
        ttk.Button(btn_row, text="📦 Manual Restock", command=self._restock_item).pack(side="right", expand=True, fill="x", padx=(5, 0))

        # 3. Edit Selected Item Box
        edit_frame = ttk.LabelFrame(parent, text=" Quick Edit Selected ", padding=15)
        edit_frame.pack(fill="x")

        self.var_edit_price = tk.StringVar()
        self.var_edit_threshold = tk.StringVar()

        self._labeled_entry(edit_frame, "New Price ($):", self.var_edit_price, 0)
        self._labeled_entry(edit_frame, "New Threshold:", self.var_edit_threshold, 1)

        ttk.Button(edit_frame, text="✏️ Apply Edits", command=self._apply_edits).grid(row=2, column=0, columnspan=2, pady=(12, 0), sticky="ew")

    def _labeled_entry(self, parent: ttk.Frame, label_text: str, variable: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable, width=18).grid(row=row, column=1, sticky="e", pady=4)

    def _build_table_panel(self, parent: ttk.Frame) -> None:
        table_frame = ttk.LabelFrame(parent, text=" Current Inventory Records ", padding=10)
        table_frame.pack(fill="both", expand=True)
        
        # Merge Sort Controller
        sort_frame = ttk.Frame(table_frame)
        sort_frame.pack(fill="x", pady=(0, 5))
        ttk.Label(sort_frame, text="Merge Sort By: ").pack(side="left")
        
        self.var_sort = tk.StringVar(value="id")
        sort_cb = ttk.Combobox(sort_frame, textvariable=self.var_sort, values=["id", "name", "stock", "price"], state="readonly", width=10)
        sort_cb.pack(side="left")
        sort_cb.bind("<<ComboboxSelected>>", self._on_sort_change)

        columns = ("id", "name", "stock", "price", "threshold", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=12)

        headers = {"id": "Item ID", "name": "Name", "stock": "Stock", "price": "Price", "threshold": "Reorder Min", "status": "Health Status"}
        widths = {"id": 80, "name": 160, "stock": 60, "price": 70, "threshold": 90, "status": 140}
        
        for col in columns:
            self.tree.heading(col, text=headers[col])
            self.tree.column(col, width=widths[col], anchor="center")

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select_item)

        log_frame = ttk.LabelFrame(parent, text=" System Audit Trail Logs ", padding=10)
        log_frame.pack(fill="x", pady=(15, 0))

        self.txt_logs = tk.Text(log_frame, height=10, font=("Consolas", 10), bg="#1e1e1e", fg="#4af626", padx=5, pady=5)
        self.txt_logs.pack(fill="both", expand=True)

    def _on_sort_change(self, event: "tk.Event[tk.Misc]") -> None:
        self.current_sort = self.var_sort.get()
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Triggers Linear Scan Algorithm, followed by Merge Sort Algorithm
        sorted_items = self.manager.generate_scanned_report(sort_by=self.current_sort)

        for item in sorted_items:
            status = "⚠️ AUTO-REORDERED" if item.requires_reorder else "✅ OK"
            # The SKU doubles as the row's iid, so selection handlers can look the
            # item up in the model instead of parsing formatted display text back.
            self.tree.insert("", "end", iid=item.item_id, values=(
                item.item_id, item.name, item.stock, f"${item.price:.2f}", item.reorder_threshold, status
            ))

        self.txt_logs.delete("1.0", tk.END)
        for log in self.manager.audit_logs:
            self.txt_logs.insert(tk.END, log + "\n")
        self.txt_logs.see(tk.END)

    def _seed_sample_data(self) -> None:
        self.manager.add_item(InventoryItem("SRVC-01", "Enterprise Server", 10, 2499.99, 3))
        self.manager.add_item(InventoryItem("SWCH-02", "Network Switch", 25, 450.00, 8))
        self.manager.add_item(InventoryItem("CABL-03", "Cat6 Cable (10m)", 5, 15.00, 10)) 
        self._refresh_ui()

    def _selected_item_id(self) -> Optional[str]:
        """The SKU of the highlighted row, or None with a warning if nothing is selected."""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selection Error", "Please select an item from the table.")
            return None
        return selected[0]      # the iid is the SKU

    def _on_select_item(self, _event: "tk.Event[tk.Misc]") -> None:
        selected = self.tree.selection()
        if not selected:
            return
        try:
            item = self.manager.get_item(selected[0])
        except KeyError:
            return
        self.var_edit_price.set(f"{item.price:.2f}")
        self.var_edit_threshold.set(str(item.reorder_threshold))

    def _add_item(self) -> None:
        try:
            item_id = self.var_id.get().strip()
            name = self.var_name.get().strip()
            stock = int(self.var_stock.get())
            price = float(self.var_price.get())
            threshold = int(self.var_threshold.get())

            if not item_id or not name:
                raise ValueError("ID and Name fields cannot be blank.")

            self.manager.add_item(InventoryItem(item_id, name, stock, price, threshold))
            self._refresh_ui()
            self.var_id.set("")
            self.var_name.set("")
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))

    def _record_sale(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            return

        try:
            qty = int(self.var_op_qty.get())
            if qty <= 0: raise ValueError("Quantity must be greater than zero.")

            auto_reordered = self.manager.record_sale(item_id, qty)
            self._refresh_ui()

            if auto_reordered:
                messagebox.showinfo("Auto Reorder Triggered", f"Stock for [{item_id}] breached threshold.\nAutomatic replenishment algorithm executed.")
        except (ValueError, KeyError) as e:
            messagebox.showerror("Sale Error", str(e))

    def _restock_item(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            return

        try:
            qty = int(self.var_op_qty.get())
            if qty <= 0: raise ValueError("Quantity must be greater than zero.")

            item = self.manager.get_item(item_id)
            item.adjust_stock(qty)
            self.manager.log_event(f"MANUAL RESTOCK: Added {qty} units to {item_id}.")
            self._refresh_ui()
        except (ValueError, KeyError) as e:
            messagebox.showerror("Restock Error", str(e))

    def _apply_edits(self) -> None:
        item_id = self._selected_item_id()
        if item_id is None:
            return

        try:
            price_val = float(self.var_edit_price.get()) if self.var_edit_price.get() else None
            thresh_val = int(self.var_edit_threshold.get()) if self.var_edit_threshold.get() else None

            self.manager.edit_item(item_id, price=price_val, threshold=thresh_val)
            self._refresh_ui()
        except (ValueError, KeyError) as e:
            messagebox.showerror("Edit Error", str(e))


if __name__ == "__main__":
    app = InventoryApp()
    app.mainloop()

