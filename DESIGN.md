# VIKMO Channel Sync & Order Engine - Design Documentation

This document outlines the architectural decisions, database schema constraints, concurrency locking mechanisms, and sync strategy implemented for the VIKMO take-home assignment.

---

## 1. Relational Database Schema & Field Choice Justifications

### Model Relationships
* **Product**: Acts as the master catalog. The `sku` field is configured with `unique=True` and `db_index=True` because it handles frequent high-volume lookups during external catalog sync operations.
* **Inventory**: Structured with a `OneToOneField(Product)` to guarantee exactly one stock ledger record per product instance. A `MinValueValidator(0)` constraint is added at the model layer to prevent negative values.
* **Order & OrderItem**: An `Order` can have multiple `OrderItem` relations (one-to-many). The `total_amount` is calculated dynamically during line item compilation to prevent stale reporting metrics.

### Critical `on_delete` Strategy
* **`OrderItem.product -> models.PROTECT`**: If an items manager deletes a product from the active catalog, cascading deletions would wipe out historical order ledger records, breaking financial accountability. Using `PROTECT` ensures data consistency for audits.
* **`Order.dealer -> models.PROTECT`**: Protects historical transactional invoices from being deleted if a dealer account is removed.

### Pricing Snapshot Pattern
* **`OrderItem.price_at_order`**: Consumer and B2B pricing fluctuates continuously. If a product price is edited in the catalog tomorrow, historical transactions must remain locked to their point-of-sale values. The price is frozen within the model’s `save()` hook.

---

## 2. Concurrency & Data Integrity Strategy

### Race Condition Avoidance
When multiple dealers simultaneously attempt to confirm orders for limited stock units, simple read-then-write logic creates a race condition (over-allocation/overselling). 

To solve this, the `/api/orders/{id}/confirm/` endpoint implements:
1. **Explicit Database Transactions**: Wrapped in Django's `transaction.atomic()` block to guarantee that the operations (validation, reduction, and state update) succeed entirely or roll back completely.
2. **Row-Level Locking (`select_for_update`)**:
   ```python
   Inventory.objects.select_for_update().filter(product_id__in=product_ids)