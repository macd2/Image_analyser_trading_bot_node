---
type: "always_apply"
description: "Example description"
---

# Deployment
- For Railway deployments, use Railpack instead of Nixpacks (which is deprecated).

# Git
- Never push to git without explicitly asking for permission first, even if user says "commit and push" - confirm before pushing.

# Database
- Every database connection must use the centralized connector.
- Every database connection must respect the switch from env for local or Supabase PostgreSQL DB.
- This project must have ONE centralized database layer/connector that handles all database operations for both Supabase (PostgreSQL) and SQLite - a single source of truth for all DB operations.
- All database access in the project MUST use the centralized database connectors (lib/db/trading-db.ts for Node.js, python/trading_bot/db/client.py for Python) that handle SQLite/PostgreSQL switching via DB_TYPE - never use direct sqlite3/psycopg2 connections.
- i ALWAYS use the centralized databse layer for handling of difference between SQLite and PostgreSQL

# Rules
- I NEVER assume anything, everything I do MUST be based on code.
- I ALWAYS check the code, database schema via DATABASE_URL from env.local or docs via Jina.
- Never assume anything about database schema or codebase - always verify by checking the actual code/database first, and don't make changes without asking for permission.

# General
- I ALWAYS try to rely on only ONE single source of truth for each concern and rather create a centralized solution than having different code for the same concern in different files for example (trading-db.ts).