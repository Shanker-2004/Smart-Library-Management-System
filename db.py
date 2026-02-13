# db.py
import os
import hashlib
import pandas as pd
from sqlalchemy import create_engine, text

# -----------------------------
# PATHS & DATABASE SETUP
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = os.path.join(BASE_DIR, "data")
DB_FILE = os.path.join(BASE_DIR, "library.db")
DB_URL = f"sqlite:///{DB_FILE}"

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

# Create SQLAlchemy engine
engine = create_engine(DB_URL, echo=False, future=True)


# =============================
# PASSWORD HASH HELPER
# =============================
def _hash_password(password: str) -> str:
    """Return SHA-256 hash of a password."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# =============================
# INITIALIZATION
# =============================
def init_db():
    """Initialize tables for users, books, and borrow_records."""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS books (
                book_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                price REAL DEFAULT 0,
                copies INTEGER DEFAULT 0
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS borrow_records (
                record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                borrow_date TEXT DEFAULT CURRENT_TIMESTAMP,
                return_date TEXT,
                fine REAL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(user_id),
                FOREIGN KEY(book_id) REFERENCES books(book_id)
            );
        """))


def create_admin(email: str = "shanker@gmail.com", password: str = "Isha@2004", name: str = "Shanker"):
    """Create or update the admin account."""
    hashed = _hash_password(password)
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT user_id FROM users WHERE email=:email"),
            {"email": email}
        ).fetchone()

        if not existing:
            conn.execute(
                text("""
                    INSERT INTO users (name, email, password, role)
                    VALUES (:name, :email, :password, 'admin')
                """),
                {"name": name, "email": email, "password": hashed}
            )
        else:
            conn.execute(
                text("""
                    UPDATE users
                    SET password=:password, name=:name, role='admin'
                    WHERE email=:email
                """),
                {"password": hashed, "name": name, "email": email}
            )


# =============================
# USER FUNCTIONS
# =============================
def register_user(name: str, email: str, password: str, role: str = "user"):
    """Register a new user account."""
    hashed = _hash_password(password)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (name, email, password, role)
            VALUES (:name, :email, :password, :role)
        """), {"name": name, "email": email, "password": hashed, "role": role})


def get_user_by_email(email: str):
    with engine.begin() as conn:
        result = conn.execute(
            text("SELECT * FROM users WHERE email=:email"),
            {"email": email}
        )
        return result.mappings().fetchone()


def verify_user_credentials(email: str, password: str):
    """Verify user credentials and return user record if valid."""
    hashed = _hash_password(password)
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT user_id, name, email, role
                FROM users
                WHERE email=:email AND password=:password
            """),
            {"email": email, "password": hashed}
        ).fetchone()

        return dict(result._mapping) if result else None


def list_users_df():
    with engine.begin() as conn:
        df = pd.read_sql(
            text("SELECT user_id, name, email, role, registered_at FROM users"),
            conn
        )
    return df


# =============================
# BOOK FUNCTIONS
# =============================
def add_book(title: str, author: str = None, price: float = 0.0, copies: int = 0):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO books (title, author, price, copies)
            VALUES (:title, :author, :price, :copies)
        """), {"title": title, "author": author, "price": price, "copies": copies})


def update_book_copies(book_id: int, new_copies: int):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE books SET copies=:copies WHERE book_id=:book_id
        """), {"copies": new_copies, "book_id": book_id})


def get_books_df():
    with engine.begin() as conn:
        return pd.read_sql(text("SELECT * FROM books"), conn)


# =============================
# BORROW / RETURN FUNCTIONS
# =============================
def borrow_book_db(user_id: int, book_id: int) -> bool:
    """Create borrow record and decrement copies."""
    with engine.begin() as conn:
        res = conn.execute(
            text("SELECT copies FROM books WHERE book_id=:book_id"),
            {"book_id": book_id}
        ).fetchone()

        if not res or res[0] <= 0:
            return False

        conn.execute(text("""
            INSERT INTO borrow_records (user_id, book_id)
            VALUES (:uid, :bid)
        """), {"uid": user_id, "bid": book_id})

        conn.execute(
            text("UPDATE books SET copies=copies-1 WHERE book_id=:book_id"),
            {"book_id": book_id}
        )
        return True

def return_book_db(user_id: int, book_id: int):
    with engine.begin() as conn:
        record = conn.execute(text("""
            SELECT record_id, borrow_date
            FROM borrow_records
            WHERE user_id=:uid AND book_id=:bid AND return_date IS NULL
            ORDER BY borrow_date DESC LIMIT 1
        """), {"uid": user_id, "bid": book_id}).fetchone()

        if not record:
            return None

        rid, borrow_date = record
        borrow_ts = pd.to_datetime(borrow_date)
        days = (pd.Timestamp.now() - borrow_ts).days
        fine = max(0, (days - 7))

        conn.execute(text("""
            UPDATE borrow_records
            SET return_date=CURRENT_TIMESTAMP, fine=:fine
            WHERE record_id=:rid
        """), {"fine": fine, "rid": rid})

        conn.execute(
            text("UPDATE books SET copies=copies+1 WHERE book_id=:bid"),
            {"bid": book_id}
        )

        return fine

def get_user_records_df_by_userid(user_id: int):
    with engine.begin() as conn:
        df = pd.read_sql(text("""
            SELECT br.record_id, b.title, b.author,
                br.borrow_date, br.return_date, br.fine
            FROM borrow_records br
            JOIN books b ON br.book_id=b.book_id
            WHERE br.user_id=:uid
            ORDER BY br.borrow_date DESC
        """), conn, params={"uid": user_id})
    return df


def get_all_borrow_records_df():
    with engine.begin() as conn:
        df = pd.read_sql(text("""
            SELECT br.record_id, u.name AS user_name, u.email AS user_email,
                b.title, b.book_id, br.borrow_date, br.return_date, br.fine
            FROM borrow_records br
            LEFT JOIN users u ON br.user_id=u.user_id
            LEFT JOIN books b ON br.book_id=b.book_id
            ORDER BY br.borrow_date DESC
        """), conn)
    return df


# =============================
# ADMIN DASHBOARD
# =============================
def get_admin_stats():
    with engine.begin() as conn:
        users = conn.execute(text("SELECT COUNT(*) FROM users WHERE role='user'")).scalar() or 0
        books = conn.execute(text("SELECT COUNT(*) FROM books")).scalar() or 0
        borrowed = conn.execute(text("SELECT COUNT(*) FROM borrow_records WHERE return_date IS NULL")).scalar() or 0
        fine = conn.execute(text("SELECT SUM(fine) FROM borrow_records")).scalar() or 0

    return {
        "total_users": users,
        "total_books": books,
        "borrowed_books": borrowed,
        "total_fine_collected": fine
    }


def get_top_borrowed_books(limit: int = 5):
    with engine.begin() as conn:
        return pd.read_sql(text(f"""
            SELECT b.title, COUNT(*) AS borrow_count
            FROM borrow_records br
            JOIN books b ON br.book_id=b.book_id
            GROUP BY b.book_id
            ORDER BY borrow_count DESC
            LIMIT {limit}
        """), conn)


def get_recent_borrow_activity(limit: int = 10):
    with engine.begin() as conn:
        return pd.read_sql(text(f"""
            SELECT u.name AS user_name, b.title, br.borrow_date,
                br.return_date, br.fine
            FROM borrow_records br
            JOIN users u ON br.user_id=u.user_id
            JOIN books b ON br.book_id=b.book_id
            ORDER BY br.borrow_date DESC
            LIMIT {limit}
        """), conn)


# =============================
# EXCEL IMPORT / EXPORT
# =============================
def import_books_from_excel(filepath: str):
    if not os.path.exists(filepath):
        raise FileNotFoundError(filepath)

    df = pd.read_excel(filepath)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    for col in ["title", "author", "price", "copies"]:
        if col not in df.columns:
            df[col] = None

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM books"))
        for _, r in df.iterrows():
            conn.execute(text("""
                INSERT INTO books (title, author, price, copies)
                VALUES (:title, :author, :price, :copies)
            """), {
                "title": str(r["title"]),
                "author": str(r["author"]),
                "price": float(r["price"] or 0),
                "copies": int(r["copies"] or 0)
            })


def export_books_to_excel(filepath: str):
    get_books_df().to_excel(filepath, index=False)


def export_borrow_records_to_excel(filepath: str):
    get_all_borrow_records_df().to_excel(filepath, index=False)


# =============================
# MAIN
# =============================
if __name__ == "__main__":
    init_db()
    create_admin()
    print("✅ Database initialized and admin ensured (Shanker / Isha@2004).")
