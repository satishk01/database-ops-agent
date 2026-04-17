"""
Seed script to populate an Aurora PostgreSQL database with realistic data
for demonstrating the DataOps Agent.

Usage:
  python seed_demo_db.py

This creates tables, inserts sample data, and introduces some
intentional performance issues (bloat, missing indexes, etc.)
for the agent to discover and fix.
"""

from app.db import get_connection


def seed():
    conn = get_connection()
    conn.autocommit = True
    cur = conn.cursor()

    # Verify SSL connection
    cur.execute("SELECT ssl_is_used()")
    ssl_used = cur.fetchone()[0]
    print(f"SSL connection: {'Yes' if ssl_used else 'No (WARNING: not encrypted)'}")
    print()

    print("Creating tables...")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id SERIAL PRIMARY KEY,
        first_name VARCHAR(100),
        last_name VARCHAR(100),
        email VARCHAR(255),
        department VARCHAR(100),
        salary NUMERIC(10,2),
        hire_date DATE,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        proj_name VARCHAR(200),
        status VARCHAR(50),
        budget NUMERIC(12,2),
        start_date DATE,
        end_date DATE,
        lead_id INTEGER REFERENCES employees(id)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS timesheets (
        id SERIAL PRIMARY KEY,
        employee_id INTEGER REFERENCES employees(id),
        project_id INTEGER REFERENCES projects(id),
        hours_worked NUMERIC(5,2),
        work_date DATE,
        description TEXT
    );
    """)

    # Check if data already exists
    cur.execute("SELECT count(*) FROM employees")
    if cur.fetchone()[0] > 0:
        print("Data already exists, skipping insert.")
    else:
        print("Inserting sample employees...")
        cur.execute("""
        INSERT INTO employees (first_name, last_name, email, department, salary, hire_date)
        SELECT
            'Employee_' || i,
            'Last_' || i,
            'emp' || i || '@example.com',
            (ARRAY['Engineering','Sales','Marketing','HR','Finance'])[1 + (i % 5)],
            30000 + (random() * 120000)::int,
            '2018-01-01'::date + (random() * 2500)::int
        FROM generate_series(1, 50000) AS i;
        """)

        print("Inserting sample projects...")
        cur.execute("""
        INSERT INTO projects (proj_name, status, budget, start_date, end_date, lead_id)
        SELECT
            'Project_' || i,
            (ARRAY['active','completed','on_hold','cancelled'])[1 + (i % 4)],
            10000 + (random() * 500000)::int,
            '2023-01-01'::date + (random() * 800)::int,
            '2024-06-01'::date + (random() * 400)::int,
            1 + (random() * 49999)::int
        FROM generate_series(1, 500) AS i;
        """)

        print("Inserting sample timesheets...")
        cur.execute("""
        INSERT INTO timesheets (employee_id, project_id, hours_worked, work_date, description)
        SELECT
            1 + (random() * 49999)::int,
            1 + (random() * 499)::int,
            1 + (random() * 12)::numeric(5,2),
            '2024-01-01'::date + (random() * 365)::int,
            'Work item ' || i
        FROM generate_series(1, 200000) AS i;
        """)

    # Create some intentional bloat by updating and not vacuuming
    print("Creating intentional bloat for demo...")
    cur.execute("""
    UPDATE employees SET salary = salary + 1 WHERE id <= 10000;
    """)

    # Create an unused index (waste)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_employees_unused_demo
    ON employees (created_at, first_name, last_name, department);
    """)

    # Enable pg_stat_statements if possible
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements;")
        print("pg_stat_statements enabled.")
    except Exception:
        print("Note: pg_stat_statements not available (needs superuser or shared_preload_libraries).")

    # Run some queries to populate pg_stat_statements
    print("Running sample queries to populate stats...")
    for _ in range(10):
        cur.execute("SELECT * FROM employees WHERE email LIKE '%500%'")
        cur.execute("SELECT * FROM employees WHERE last_name = 'Last_42'")
        cur.execute("""
        SELECT e.first_name, p.proj_name, sum(t.hours_worked)
        FROM timesheets t
        JOIN employees e ON e.id = t.employee_id
        JOIN projects p ON p.id = t.project_id
        GROUP BY e.first_name, p.proj_name
        ORDER BY sum(t.hours_worked) DESC
        LIMIT 10
        """)

    cur.close()
    conn.close()
    print("Demo database seeded successfully!")
    print()
    print("The agent should now be able to find:")
    print("  - Table bloat in 'employees' (from the UPDATE)")
    print("  - Unused index 'idx_employees_unused_demo'")
    print("  - Missing indexes on email and last_name columns")
    print("  - Slow queries from the LIKE and JOIN operations")


if __name__ == "__main__":
    seed()
