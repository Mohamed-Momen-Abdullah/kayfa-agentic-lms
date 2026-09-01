import sqlite3

DB_PATH = "app/data/university.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Show tables
cursor.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type='table'
    ORDER BY name;
""")

tables = cursor.fetchall()

print("Tables:")
for table in tables:
    print("-", table[0])

# Show first 5 rows from each table
for (table_name,) in tables:
    print(f"\n===== {table_name} =====")

    cursor.execute(f'PRAGMA table_info("{table_name}")')
    columns = cursor.fetchall()

    column_names = [col[1] for col in columns]
    print("Columns:", column_names)

    cursor.execute(f'SELECT * FROM "{table_name}" LIMIT 5')
    rows = cursor.fetchall()

    for row in rows:
        print(row)

conn.close()