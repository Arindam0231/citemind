# Database Directory (`db/`)

This directory orchestrates local embedded persistence via SQLite (`checkmate.db`).

## Setup
SQLite acts as the state synchronization layer between user inputs, uploaded file artifacts, and the LLM execution process without needing an external service.

## Modules
- **`connection.py`**: Manages the SQLite context generators establishing safe concurrency locks and robust commit procedures natively mapped to the local filepath.
- **`queries.py`**: A centralized library containing pure SQL statements enforcing schema mapping. All CRUD logic targeting slides, cells, selection events, and citations happen here allowing easy migration tracking.
- **`schema.sql`**: The fundamental schema definitions establishing relationships between Data Tables (ie. mapping isolated Excel constraints with generated Presentation artifacts).
