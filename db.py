import pandas as pd
from sqlalchemy import create_engine, text

# -------------------------------
# DATABASE CONNECTION
# -------------------------------
engine = create_engine("sqlite:///library.db", echo=False, future=True)

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT,
            role TEXT DEFAULT 'user'
        );
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS books (
            book_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            author TEXT,
            price REAL,
            copies_available INTEGER
        );
        """))

        conn.execute(text("""
        CREATE TABLE IF NOT EXISTS borrowed_books (
            borrow_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            book_id INTEGER,
            borrow_date DATE,
            due_date DATE,
            return_date DATE,
            fine_amount REAL DEFAULT 0
        );
        """))

        # Add admin user if not exists
        conn.execute(text("""
        INSERT OR IGNORE INTO users (user_id, name, email, password, role)
        VALUES (1, 'Admin', 'admin@library.com', 'admin123', 'admin');
        """))

def import_books_from_excel(path):
    try:
        df = pd.read_excel(path)
        required_cols = ["title", "author", "price", "copies_available"]
        if not all(col in df.columns for col in required_cols):
            print("❌ Excel missing required columns.")
            return False
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM books"))
            df.to_sql("books", con=conn, if_exists="append", index=False)
        return True
    except Exception as e:
        print(f"Error importing Excel: {e}")
        return False
