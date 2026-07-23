---
name: sql-optimization
description: Database design, query optimization, indexing strategies, and performance tuning for SQLite and async database operations.
---

# SQL & Database Optimization Guidelines (SQLite / aiosqlite)

Use this skill when modifying database schemas, writing complex SQL queries, optimizing slow queries, or designing asynchronous data access layers.

## Core Rules & Best Practices

1. **Indexing & Query Performance**
   - Create indexes on columns frequently used in `WHERE`, `JOIN`, `ORDER BY`, and `GROUP BY` clauses.
   - For queries filtering on multiple columns, use composite indexes with left-most prefix column ordering in mind.
   - Use `EXPLAIN QUERY PLAN` to verify that SQLite is utilizing indexes (`SEARCH TABLE`) instead of full table scans (`SCAN TABLE`).

2. **Async SQLite (`aiosqlite`) Best Practices**
   - Maintain WAL mode (`PRAGMA journal_mode=WAL;`) and reasonable busy timeouts (`PRAGMA busy_timeout = 5000;`) for concurrent read/write throughput.
   - Always manage database connections using context managers (`async with aiosqlite.connect(...)` or connection pool handlers) to prevent resource leaks.
   - Commit transactions explicitly (`await db.commit()`) after write/update operations.

3. **Avoiding Common SQL Anti-Patterns**
   - **N+1 Query Problem:** Avoid executing single SELECT queries inside loops. Fetch data in batch using `WHERE column IN (...)` or proper `JOIN` clauses.
   - **SELECT * Prohibition:** Specify explicit column names in `SELECT` statements (`SELECT id, name, status FROM ...`) to minimize I/O overhead and payload sizes.
   - **Parameterized Queries:** ALWAYS use parameter binding (`?` in SQLite) to prevent SQL injection vulnerabilities. NEVER format raw strings directly into SQL queries.

4. **Schema Migration & Maintenance**
   - Ensure primary keys and foreign key constraints (`PRAGMA foreign_keys = ON;`) are enforced for relational data integrity.
   - Use transactions (`async with db.transaction():`) for atomic multi-step write operations to keep database state consistent.
