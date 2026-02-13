# app.py (complete — corrected & ready to run)
import streamlit as st
import pandas as pd
from db import get_user_records_df_by_userid, return_book_db, get_books_df
import os
import time
from datetime import datetime
from sqlalchemy import create_engine, text
import hashlib
import warnings

# suppress some openpyxl warnings that may appear when writing Excel
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

# -----------------------------
# CONFIG / PATHS
# -----------------------------
st.set_page_config(page_title="📚 Smart Library Management System", layout="wide")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = os.path.join(BASE_DIR, "data")
DB_FILE = os.path.join(BASE_DIR, "library.db")
DB_URL = f"sqlite:///{DB_FILE}"

if not os.path.exists(DATA_FOLDER):
    os.makedirs(DATA_FOLDER)

# -----------------------------
# DATABASE (SQLAlchemy)
# -----------------------------
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})


def hash_password(raw: str, salt: str = "smartlib_salt"):
    return hashlib.sha256((salt + raw).encode("utf-8")).hexdigest()


def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT UNIQUE,
                password TEXT,
                role TEXT DEFAULT 'user',
                registered_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS borrowed_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                title TEXT,
                borrow_date DATETIME,
                return_date DATETIME,
                due DATETIME,
                fine REAL DEFAULT 0
            )
        """))


def fix_borrowed_records_table():
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(borrowed_records)")).fetchall()
        col_names = [c[1] for c in cols]

        if "due" not in col_names:
            conn.execute(text("ALTER TABLE borrowed_records ADD COLUMN due DATETIME"))

        if "fine" not in col_names:
            conn.execute(text("ALTER TABLE borrowed_records ADD COLUMN fine REAL DEFAULT 0"))



def create_admin(email: str = "admin@library.local", password: str = "admin123", name: str = "Admin"):
    hashed = hash_password(password)
    with engine.begin() as conn:
        existing = conn.execute(text("SELECT user_id FROM users WHERE email=:email"), {"email": email}).fetchone()
        if not existing:
            conn.execute(text("""
                INSERT INTO users (name, email, password, role)
                VALUES (:name, :email, :password, 'admin')
            """), {"name": name, "email": email, "password": hashed})
        else:
            conn.execute(text("""
                UPDATE users SET password=:password, name=:name, role='admin'
                WHERE email=:email
            """), {"password": hashed, "name": name, "email": email})


def verify_user_credentials(email, password):
    if not email or not password:
        return None
    hashed = hash_password(password)
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT user_id, name, email, role FROM users WHERE email = :e AND password = :p"
        ), {"e": email.strip(), "p": hashed}).fetchone()
        if row:
            return {"user_id": row[0], "name": row[1], "email": row[2], "role": row[3]}
    return None


def create_user(name, email, password):
    if not (name and email and password):
        return False, "All fields required."
    hashed = hash_password(password)
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO users (name, email, password, role)
                VALUES (:name, :email, :password, 'user')
            """), {"name": name, "email": email, "password": hashed})
        return True, None
    except Exception as e:
        msg = str(e)
        if "UNIQUE constraint failed" in msg or "UNIQUE constraint" in msg:
            return False, "Email already registered."
        return False, "Registration failed."


def get_user_by_email(email):
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT user_id, name, email, role FROM users WHERE email = :e"
        ), {"e": email}).fetchone()
        if row:
            return {"user_id": row[0], "name": row[1], "email": row[2], "role": row[3]}
    return None


# -----------------------------
# BOOK / FILE HANDLING
# -----------------------------
def load_all_books():
    all_files = [
    f for f in os.listdir(DATA_FOLDER)
    if f.lower().endswith((".xlsx", ".xls"))
]

    if not all_files:
        return pd.DataFrame(columns=[
            "book_id", "title", "author", "genre", "isbn", "publisher",
            "year", "price", "copies_available", "shelf_number", "level", "source_file"
        ])

    df_list = []

    for file in all_files:
        if file.startswith("~$"):
            continue

        path = os.path.join(DATA_FOLDER, file)
        try:
            df = pd.read_excel(path)
        except Exception:
            continue

        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns.astype(str)]

        mapping = {
            "bookid": "book_id", "book_code": "book_id",
            "book_title": "title", "bookname": "title", "book": "title",
            "writer": "author", "author_name": "author",
            "genre_category": "genre", "category": "genre", "type": "genre",
            "isbn_number": "isbn",
            "publishing_company": "publisher", "pub": "publisher",
            "publish_year": "year",
            "cost": "price", "amount": "price", "book_price": "price",
            "no_of_copies": "copies_available", "quantity": "copies_available",
            "stock": "copies_available",
            "shelf_no": "shelf_number", "rack_no": "shelf_number",
        }
        df.rename(columns=mapping, inplace=True)

        for col in [
            "book_id", "title", "author", "genre", "isbn", "publisher",
            "year", "price", "copies_available", "shelf_number", "level"
        ]:
            if col not in df.columns:
                df[col] = None

        df["title"] = df["title"].astype(str).str.strip()
        df = df[df["title"] != ""]

        df["copies_available"] = (
            pd.to_numeric(df["copies_available"], errors="coerce")
            .fillna(1).astype(int).clip(lower=0)
        )

        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        df["price"] = pd.to_numeric(df["price"], errors="coerce")

        df["source_file"] = file

        df_list.append(df[[
            "book_id", "title", "author", "genre", "isbn", "publisher",
            "year", "price", "copies_available", "shelf_number", "level", "source_file"
        ]])

    if not df_list:
        return pd.DataFrame(columns=[
            "book_id", "title", "author", "genre", "isbn", "publisher",
            "year", "price", "copies_available", "shelf_number", "level", "source_file"
        ])

    return pd.concat(df_list, ignore_index=True)


def save_new_book_file(df, filename=None):
    if filename is None:
        filename = f"books_{int(time.time())}.xlsx"
    path = os.path.join(DATA_FOLDER, filename)
    df.to_excel(path, index=False, engine="openpyxl")
    st.success(f"✅ Saved as {filename}")



def _normalize_dt_for_db(dt):
    if dt is None:
        return None
    if isinstance(dt, pd.Timestamp):
        dt_py = dt.to_pydatetime()
        return dt_py.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(dt, str):
        return dt
    try:
        coerced = pd.to_datetime(dt)
        return coerced.to_pydatetime().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def load_records_from_db():
    with engine.begin() as conn:
        try:
            rec_df = pd.read_sql("SELECT * FROM borrowed_records", conn)

            # ✅ Normalize datetime columns
            for col in ["borrow_date", "return_date", "due"]:
                if col not in rec_df.columns:
                    rec_df[col] = pd.NaT
                else:
                    rec_df[col] = rec_df[col].replace("", pd.NaT)
                    rec_df[col] = pd.to_datetime(rec_df[col], errors="coerce")

            # ✅ Ensure fine column
            if "fine" not in rec_df.columns:
                rec_df["fine"] = 0

            return rec_df

        except Exception:
            return pd.DataFrame(
                columns=["id", "user", "title", "borrow_date", "return_date", "due", "fine"]
            )



def save_record_to_db(user, title, borrow_date=None, return_date=None, due_date=None, fine=0):
    borrow_date_db = _normalize_dt_for_db(borrow_date or datetime.now())
    return_date_db = _normalize_dt_for_db(return_date)
    due_date_db = _normalize_dt_for_db(due_date)
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO borrowed_records (user, title, borrow_date, return_date, due, fine)
            VALUES (:user, :title, :borrow_date, :return_date, :due, :fine)
        """), {
            "user": user,
            "title": title,
            "borrow_date": borrow_date_db,
            "return_date": return_date_db,
            "due": due_date_db,
            "fine": fine
        })


def update_return_in_db(record_id, return_date, fine):
    return_date_db = _normalize_dt_for_db(return_date)

    with engine.begin() as conn:
        conn.execute(
            text("""
                UPDATE borrowed_records
                SET return_date = :return_date,
                    fine = :fine
                WHERE id = :id
            """),
            {
                "return_date": return_date_db,
                "fine": fine,
                "id": record_id
            }
        )


def find_book_in_data_files(title):
    files = [f for f in os.listdir(DATA_FOLDER) if f.lower().endswith((".xlsx", ".xls"))]
    for file in files:
        path = os.path.join(DATA_FOLDER, file)
        try:
            df = pd.read_excel(path)
        except Exception:
            continue
        cols_low = [c.strip().lower().replace(" ", "_") for c in df.columns.astype(str)]
        df.columns = cols_low
        if "title" not in df.columns:
            continue
        matches = df[df["title"].astype(str).str.lower() == str(title).lower()]
        if not matches.empty:
            idx = matches.index[0]
            return path, df, idx
    return None, None, None

def safe_fmt(dt):
    if pd.isna(dt):
        return "-"
    if isinstance(dt, (pd.Timestamp, datetime)):
        return dt.strftime("%d-%b-%Y")
    try:
        coerced = pd.to_datetime(dt, errors="coerce")
        if pd.isna(coerced):
            return "-"
        else:
            return coerced.strftime("%d-%b-%Y")
    except Exception:
        return "-"


# -----------------------------
# SESSION DEFAULTS
# -----------------------------
if "page" not in st.session_state:
    st.session_state.page = "login"
if "user" not in st.session_state:
    st.session_state.user = None
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# Keep admin sidebar fields persistent keys to avoid collisions
if "admin_email" not in st.session_state:
    st.session_state.admin_email = ""
if "admin_pass" not in st.session_state:
    st.session_state.admin_pass = ""

# -----------------------------
# INIT DB + ADMIN
# -----------------------------
init_db()
fix_borrowed_records_table()   # 🔧 IMPORTANT LINE
create_admin(email="shanker@gmail.com", password="Isha@2004", name="Shanker")


# -----------------------------
# MAIN UI
# -----------------------------
if st.session_state.page == "login":
    st.title("📚 Smart Library Management System")
    st.markdown("Use the sidebar to login/register. Default admin: `admin@library.local` / `admin123`")

    # Sidebar - Admin Login
    st.sidebar.header("👨‍💼 Admin Login")
    admin_email = st.sidebar.text_input("Admin Email", key="admin_email")
    admin_pass = st.sidebar.text_input("Admin Password", type="password", key="admin_pass")

    if st.sidebar.button("Login as Admin"):
        user = verify_user_credentials(admin_email, admin_pass)
        if user and user["role"] == "admin":
            st.session_state.page = "admin"
            st.session_state.user = user["name"]
            st.session_state.user_id = user["user_id"]
            st.sidebar.success(f"✅ Welcome, {user['name']} (Admin)")
            time.sleep(1)
            st.rerun()
        else:
            st.sidebar.error("❌ Invalid admin credentials.")

    # Sidebar - User Login/Register
    st.sidebar.header("🔐 User Login / Register")
    login_mode = st.sidebar.radio("Select", ["Login", "Register"])
    email = st.sidebar.text_input("User Email", key="user_email_input")
    password = st.sidebar.text_input("Password", type="password", key="user_password_input")

    if login_mode == "Login":
        if st.sidebar.button("Login"):
            if not email or not password:
                st.sidebar.warning("Please enter email and password.")
            else:
                user = verify_user_credentials(email, password)
                if user:
                    st.session_state.page = "user"
                    st.session_state.user = user["name"]
                    st.session_state.user_id = user["user_id"]
                    st.rerun()
                else:
                    st.sidebar.error("❌ Invalid email or password.")
        if st.sidebar.button("Forgot Password?"):
            if not email:
                st.sidebar.warning("Enter your registered email first.")
            else:
                u = get_user_by_email(email)
                if u:
                    st.sidebar.success(f"Password reset link sent to {email} (simulated).")
                else:
                    st.sidebar.error("Email not found. Please register.")
        st.sidebar.markdown("[Sign in with Google](https://accounts.google.com/signin)", unsafe_allow_html=True)
    else:
        # Register
        name = st.sidebar.text_input("Full Name", key="reg_name")
        if st.sidebar.button("Register"):
            if not name or not email or not password:
                st.sidebar.warning("All fields required.")
            else:
                ok, err = create_user(name, email, password)
                if ok:
                    st.sidebar.success("✅ Registered successfully! You can now login.")
                else:
                    st.sidebar.error(f"❌ {err}")


# -----------------------------
# ADMIN DASHBOARD
# -----------------------------
elif st.session_state.page == "admin":
    st.title(f"👨‍💼 Admin Dashboard – Welcome {st.session_state.user}")
    if st.sidebar.button("Logout"):
        st.session_state.page = "login"
        st.session_state.user = None
        st.session_state.user_id = None
        time.sleep(1)
        st.rerun()

    tab1, tab2, tab3 = st.tabs(["📊 All User Records", "📚 Manage Books", "👥 Registered Users"])

    # Tab1: All user records
    with tab1:
        st.subheader("📋 Borrow / Return Records of All Users")
        borrowed_records = load_records_from_db()
        if not borrowed_records.empty:
            users = borrowed_records["user"].dropna().unique().tolist()
            selected_user = st.selectbox("Select User (or All)", ["All"] + users)
            if selected_user != "All":
                view_df = borrowed_records[borrowed_records["user"] == selected_user]
            else:
                view_df = borrowed_records
            st.dataframe(view_df.sort_values(by="borrow_date", ascending=False), use_container_width=True)
        else:
            st.info("No borrow/return records found yet.")

    # Tab2: Manage books
    with tab2:
        st.subheader("📚 Current Books in Library (loaded from data/ folder)")
        books_df = load_all_books()
        if not books_df.empty:
            st.dataframe(books_df[["title", "author", "copies_available", "source_file"]], use_container_width=True)
        else:
            st.info("No books found in 'data' folder.")

        st.markdown("---")
        st.subheader("📤 Upload New Book Excel (Admin)")
        uploaded_file = st.file_uploader("Upload Excel with book list", type=["xlsx", "xls"], key="admin_upload")
        if uploaded_file:
            try:
                df = pd.read_excel(uploaded_file)
                save_new_book_file(df)
                # after upload, re-run to show updated list
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Error reading uploaded file: {e}")

    # Tab3: Registered users
    with tab3:
        st.subheader("👥 Registered Users")
        with engine.begin() as conn:
            try:
                users_df = pd.read_sql("SELECT user_id, name, email, role, registered_at FROM users", conn)
            except Exception:
                users_df = pd.DataFrame(columns=["user_id", "name", "email", "role", "registered_at"])

        if not users_df.empty:
            users_df["registered_at"] = pd.to_datetime(users_df["registered_at"], errors="coerce").dt.strftime("%d-%b-%Y %I:%M %p")
            st.metric("🧑‍🤝‍🧑 Total Registered Users", len(users_df))
            st.dataframe(users_df, use_container_width=True)
        else:
            st.info("No registered users found.")


# -----------------------------
# USER DASHBOARD
# -----------------------------
elif st.session_state.page == "user":
    st.title(f"👋 Welcome, {st.session_state.user}")
    if st.sidebar.button("Logout"):
        st.session_state.page = "login"
        st.session_state.user = None
        st.session_state.user_id = None
        st.rerun()

    # Define tabs properly
    tab1, tab2, tab3, tab4 = st.tabs([
        "🔍 Search Books",
        "📘 Borrow / Return",
        "📊 Your Records",
        "🗂️ Book Categories"
    ])

    # TAB 1: Search
    with tab1:
        st.subheader("🔍 Search Books")
        books_df = load_all_books()
        if not books_df.empty:
            search = st.text_input("Search by Title or Author", key="search_input_user")
            if search:
                filtered = books_df[
                    books_df["title"].astype(str).str.contains(search, case=False, na=False)
                    | books_df["author"].astype(str).str.contains(search, case=False, na=False)
                ]
            else:
                filtered = books_df
            st.dataframe(filtered, use_container_width=True)
        else:
            st.info("📂 Upload books in 'data' folder first (admin only).")

    # TAB 2: Borrow / Return
    with tab2:
        st.subheader("📘 Borrow a Book")

        borrowed_records = load_records_from_db()
        books_df = load_all_books()

        if books_df.empty:
            st.info("No books available for borrowing.")
        else:
            available_books = books_df[books_df["copies_available"] > 0]

            if available_books.empty:
                st.info("No copies available right now.")
            else:
                selected_book = st.selectbox(
                    "Select Book to Borrow",
                    available_books["title"].tolist(),
                    key="borrow_select_book"
                )

                if st.button("Borrow Book", key="btn_borrow"):

                    # 🔒 Prevent duplicate borrowing
                    existing = borrowed_records[
                        (borrowed_records["user"].fillna("").str.lower() == st.session_state.user.lower()) &
                        (borrowed_records["title"] == selected_book) &
                        (borrowed_records["return_date"].isna())
                    ]

                    if not existing.empty:
                        st.warning("⚠️ You have already borrowed this book.")
                    else:
                        now = datetime.now()
                        due_date = now + pd.Timedelta(days=7)

                        # ✅ Save to DB
                        save_record_to_db(
                            user=st.session_state.user,
                            title=selected_book,
                            borrow_date=now,
                            due_date=due_date
                        )

                        # 📉 Update Excel stock
                        path, df, idx = find_book_in_data_files(selected_book)
                        if df is not None and path is not None:
                            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns.astype(str)]

                            if "copies_available" not in df.columns:
                                df["copies_available"] = 1

                            current = pd.to_numeric(df.loc[idx, "copies_available"], errors="coerce")
                            current = int(current) if not pd.isna(current) else 1

                            df.loc[idx, "copies_available"] = max(0, current - 1)
                            df.to_excel(path, index=False, engine="openpyxl")

                        st.success(
                            f"✅ Borrowed **'{selected_book}'** successfully!\n\n"
                            f"📅 Borrowed On: {now.strftime('%d-%b-%Y %I:%M %p')}\n"
                            f"📅 Due Date: **{due_date.strftime('%d-%b-%Y')}**"
                        )
        st.markdown("---")
        st.subheader("📕 Return a Book")

        borrowed_records = load_records_from_db()

        # 🔍 Filter current user's unreturned books
        user_borrows = borrowed_records[
            (borrowed_records["user"].fillna("").str.lower() == st.session_state.user.lower()) &
            (borrowed_records["return_date"].isna())
        ] if not borrowed_records.empty else pd.DataFrame()

        if user_borrows.empty:
            st.info("📭 You have no books to return.")
        else:
            return_choice = st.selectbox(
                "Select Book to Return",
                user_borrows["title"].tolist(),
                key="return_select"
            )

            rec = user_borrows[user_borrows["title"] == return_choice].iloc[0]

            # 📅 Dates
            borrow_date = pd.to_datetime(rec["borrow_date"])
            today = datetime.now()

            # 🟢 Grace period logic
            GRACE_DAYS = 7
            total_days = (today - borrow_date).days
            late_days = max(0, total_days - GRACE_DAYS)
            fine = late_days * 1  # ₹1 per day

            # 📌 Preview summary
            st.info(
                f"""
                📘 **Borrowed On:** {borrow_date.strftime('%d-%b-%Y')}
                🕒 **Grace Period:** {GRACE_DAYS} days
                ⌛ **Extra Days:** {late_days}
                💰 **Fine:** ₹{fine}
                """
            )

            # 🔘 Return button
            if st.button("Return Book", key="btn_return"):

                # ✅ Update return info
                update_return_in_db(
                    record_id=rec["id"],
                    return_date=today,
                    fine=fine
                )

                # 📈 Update book stock (Excel)
                path, df, idx = find_book_in_data_files(return_choice)

                if df is not None and path is not None:
                    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns.astype(str)]

                    if "copies_available" not in df.columns:
                        df["copies_available"] = 0

                    current = pd.to_numeric(df.loc[idx, "copies_available"], errors="coerce")
                    current = int(current) if not pd.isna(current) else 0
                    df.loc[idx, "copies_available"] = current + 1

                    df.to_excel(path, index=False, engine="openpyxl")

                # 🎉 Success message
                st.success(
                    f"""
                    ✅ **Book Returned Successfully!**

                    📘 **Title:** {return_choice}
                    📅 **Borrowed On:** {borrow_date.strftime('%d-%b-%Y')}
                    📅 **Returned On:** {today.strftime('%d-%b-%Y')}
                    💰 **Fine Paid:** ₹{fine}
                    """
                )

                st.rerun()


    # TAB 3: Your Records
    with tab3:
        st.subheader("📊 Your Borrow / Return History")
        borrowed_records = load_records_from_db()
        if not borrowed_records.empty:
            # protect against missing columns
            if "user" not in borrowed_records.columns:
                borrowed_records["user"] = ""
            user_records = borrowed_records[borrowed_records["user"].fillna("").str.lower() == str(st.session_state.user).lower()]
        else:
            user_records = pd.DataFrame()

        if not user_records.empty:
            # Format dates for display while avoiding errors
            # Format dates for display while avoiding errors
            def fmt(dt):
                try:
                    return pd.to_datetime(dt, errors="coerce").strftime("%d-%b-%Y")
                except Exception:
                    return ""
            user_records = user_records.copy()
            user_records["borrow_date"] = user_records["borrow_date"].apply(safe_fmt)
            user_records["return_date"] = user_records["return_date"].apply(safe_fmt)
            user_records["due"] = user_records["due"].apply(safe_fmt)
            # Display dates safely using your function
            st.write(f"Borrowed On: {safe_fmt(borrow_date)}")
            st.write(f"Due Date: {safe_fmt(due_date)}")
            st.write(f"Returned On: {safe_fmt(return_date)}")

            st.dataframe(user_records.sort_values(by="borrow_date", ascending=False), use_container_width=True)
        else:
            st.info("No borrow/return records found.")

    # TAB 4: Book Categories
    with tab4:
        st.subheader("🗂️ Explore Book Categories")
        books_df = load_all_books()
        if books_df.empty:
            st.info("📂 No books found in the system.")
        else:
            categories = {
                "Academic Books": ["School", "College / University", "Research & Reference"],
                "Moral Stories": [],
                "Historical Books": [],
                "Fiction": [],
                "Non-Fiction": [],
                "Children's Books": [],
                "Religious / Spiritual Books": [],
                "Comics & Graphic Novels": [],
                "Career & Skill Development": []
            }

            cols = st.columns(3)
            clicked_cat = None
            i = 0
            for cat in categories.keys():
                if cols[i % 3].button(cat, key=f"cat_{cat.replace(' ', '_')}"):
                    clicked_cat = cat
                i += 1

            if clicked_cat:
                st.markdown("---")
                st.markdown(f"### 📚 {clicked_cat}")
                # MORAL STORIES special handling
                if clicked_cat == "Moral Stories":
                    candidates = [f for f in os.listdir(DATA_FOLDER) if "moral" in f.lower() and f.lower().endswith((".xlsx", ".xls"))]
                    if candidates:
                        stories_df = pd.read_excel(os.path.join(DATA_FOLDER, candidates[0]))
                        stories_df.columns = [c.strip().title() for c in stories_df.columns.astype(str)]
                        for idx, row in stories_df.iterrows():
                            with st.expander(f"{row.get('Title', 'Untitled')}"):
                                st.write(row.get('Story', ''))
                                st.markdown(f"**Moral:** {row.get('Moral', '')}")
                    else:
                        st.info("No moral stories found. Please ask admin to upload a file with 'moral' in its name.")

                elif clicked_cat == "Historical Books":
                    candidates = [f for f in os.listdir(DATA_FOLDER) if "histor" in f.lower() and f.lower().endswith((".xlsx", ".xls"))]
                    if candidates:
                        hist_df = pd.read_excel(os.path.join(DATA_FOLDER, candidates[0]))
                        cols_low = [c.strip().lower().replace(" ", "_") for c in hist_df.columns.astype(str)]
                        hist_df.columns = cols_low
                        expected = ["book_id", "title", "author", "publisher", "year", "price", "copies_available", "shelf_number", "level"]
                        for col in expected:
                            if col not in hist_df.columns:
                                hist_df[col] = None
                        hist_df["copies_available"] = pd.to_numeric(hist_df["copies_available"], errors="coerce").fillna(1).astype(int)
                        for _, row in hist_df.iterrows():
                            with st.expander(row["title"] if pd.notna(row["title"]) else "Untitled"):
                                st.markdown(f"**Book ID:** {row['book_id']}")
                                st.markdown(f"**Book Title:** {row['title']}")
                                st.markdown(f"**Author:** {row['author']}")
                                st.markdown(f"**Publisher:** {row['publisher']}")
                                st.markdown(f"**Published Year:** {row['year']}")
                                st.markdown(f"**Cost:** ₹{row['price']}")
                                st.markdown(f"**Copies Available:** {row['copies_available']}")
                                st.markdown(f"**Shelf Number:** {row['shelf_number']}")
                                st.markdown(f"**Level:** {row['level']}")
                    else:
                        st.info("No historical books found or file missing.")

                else:
                    # General category handling using genre / level
                    subcats = categories[clicked_cat]
                    # attempt to find books by genre containing the main category word
                    keyword = clicked_cat.split()[0]  # naive
                    if "genre" in books_df.columns:
                        cat_books = books_df[books_df["genre"].astype(str).str.contains(keyword, case=False, na=False)]
                    else:
                        cat_books = pd.DataFrame()

                    if subcats:
                        for sub in subcats:
                            st.markdown(f"#### 🔹 {sub}")
                            if "level" in cat_books.columns:
                                sub_books = cat_books[cat_books["level"].astype(str).str.contains(sub.split()[0], case=False, na=False)]
                            else:
                                sub_books = pd.DataFrame()
                            if not sub_books.empty:
                                st.write(f"**Total Books:** {len(sub_books)}")
                                st.dataframe(sub_books[["title", "author", "copies_available"]], use_container_width=True)
                            else:
                                st.info(f"No books found in '{sub}' section.")
                    else:
                        if not cat_books.empty:
                            st.write(f"**Total Books:** {len(cat_books)}")
                            st.dataframe(cat_books[["title", "author", "copies_available"]], use_container_width=True)
                        else:
                            st.info("No books found in this category.")

# -----------------------------
# FOOTER
# -----------------------------
st.markdown("---")
st.caption("© 2025 Smart Library Management System | Built by You")

