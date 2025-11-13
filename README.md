# StockFlow B2B Inventory Management - Case Study Solution

You can read the full case study solution at : https://drive.google.com/file/d/14O7sujB0gBkrEGuWuk7PWuLzDNGYWpgV/view?usp=sharing

This repository contains my solution for the StockFlow take-home assignment. The project is structured as a runnable Flask application and includes the full write-up, code fixes, database design, and API implementation.

* `/app.py`: The main Flask application containing all API endpoints and SQLAlchemy models.
* `/schema.sql`: The SQL DDL for the database design.
* `/requirements.txt`: Project dependencies.

---

## Part 1: Code Review & Debugging

The original code had several critical issues related to database transactions, input validation, and business logic.

### 1. Identified Issues

1.  **Not Atomic:** The code used two separate `db.session.commit()` calls. This creates a race condition. If the first commit (Product) succeeded but the second (Inventory) failed, the database would be left in an inconsistent state with a "ghost" product.
2.  **No Input Validation:** It used `data['key']` directly. If any key was missing from the JSON payload, the app would crash with a `KeyError` (500 Server Error).
3.  **No Error Handling:** A `try...except` block was missing. If the database raised an `IntegrityError` (like a duplicate SKU), the app would crash.
4.  **Incorrect Business Logic:** The `Product` model was tied to a `warehouse_id`. This is wrong, as the prompt states products can exist in *multiple* warehouses. The product itself shouldn't know about a warehouse; the `Inventory` table is what links them.
5.  **No Type Casting:** It didn't validate or cast data types, like converting the `price` to a `Decimal` or `initial_quantity` to an `int`.

### 2. Corrected Code (`/app.py`)

My corrected code is included as the `/api/products` endpoint in `app.py`. Here's what I fixed:

* **Atomic:** All database operations are wrapped in a single `try...except` block with one `db.session.commit()` at the end.
* **Validation:** A `for` loop checks for all `required_fields` first and returns a `400 Bad Request` if any are missing.
* **Type-Casting:** All inputs are explicitly cast (e.g., `Decimal(data['price'])`) inside a `try` block to catch `ValueError` or `InvalidOperation`.
* **Error Handling:** The `try` block now catches `IntegrityError` (for duplicate SKUs, returning a `409 Conflict`) and a general `Exception` to `rollback()` the session and prevent a crash.
* **Correct Logic:** The `Product` is created *without* a `warehouse_id`. The `Inventory` record is then created to link the new `product.id` to the `warehouse_id`.

---

## Part 2: Database Design

My database plan is centered on creating a clean, scalable, and auditable system.

### 1. The Main Problem: Tracking Stock
* We need to track a product in *many* warehouses.
* **The Fix:** I created an `Inventory` table. This table's only job is to connect a `product_id` to a `warehouse_id` and store the `quantity`. This is the standard "many-to-many" pattern and is the core of the whole design.

### 2. The History Problem: Tracking Changes
* We need to "track when inventory levels change."
* **The Fix:** We *never* just update a quantity. Doing that erases history.
* Instead, I proposed an `InventoryLogs` table (schema included in `schema.sql`). This table acts like a bank ledger. Every time stock changes, we add a new row: `+50, "restock"` or `-3, "sale"`. This gives us a perfect, non-destructive audit trail, which is critical for any real inventory system.

### 3. Other Key Decisions
* **`ProductTypes`:** To handle the "low stock threshold" rule, I put this on a `ProductTypes` table, not the `Product` table. This way, a company can update the threshold for 10,000 "T-Shirt" products by changing just *one* row.
* **Bundles & Suppliers:** These are just more many-to-many relationships, so I created join tables (`BundleComponents` and `ProductSuppliers`) to handle them.
* **Gaps Identified:** Before finalizing, I'd ask:
    1.  Is a SKU unique *per company* or *globally* unique? (I assumed globally per the prompt).
    2.  Are bundle stock levels "virtual" (calculated from parts) or "kitted" (pre-assembled)?
    3.  For the API, what's the exact definition of "recent sales"? (I assumed 30 days).

---

## Part 3: API Implementation

The `/api/companies/<int:company_id>/alerts/low-stock` endpoint is implemented in `app.py`.

### My Approach

My main goal was to make this query efficient. The "only alert for products with recent sales" rule is a perfect filter.

1.  **Define "Recent":** I assumed "recent" means the last 30 days.
2.  **Create a Subquery:** First, I create a subquery that *only* gets the list of `product_id`s that have sold in the last 30 days and their total sales. This list is very small.
3.  **Build the Main Query:** I then build the big, complex query that joins `Products`, `Warehouses`, `Inventory`, `ProductTypes` (for the threshold), and `Suppliers`.
4.  **Join for Performance:** I **inner join** the big query with my small subquery. This means the database only has to do the heavy lifting for the few products that actually sold, not the entire 10-million-item catalog. This makes it very fast.
5.  **Handle Edge Cases:**
    * **No Supplier:** I used an `outerjoin` for `Suppliers`, so if a product has no supplier, it still appears (the `supplier` field will just be `null`).
    * **Divide by Zero:** In the final loop, I check if `avg_daily_sale > 0` before calculating `days_until_stockout` to prevent a crash.
    * **Company Not Found:** The code first checks if the company exists and returns a `404` if not.
