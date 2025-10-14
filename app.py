import streamlit as st
import pandas as pd
from datetime import datetime
import os

# -----------------------------
# STREAMLIT CONFIG
# -----------------------------
st.set_page_config(page_title="📚 Smart Library", layout="wide")
st.title("📚 Smart Library Management System (Excel Version)")

# -----------------------------
# FILE PATHS
# -----------------------------
BOOKS_FILE = "books_realistic_dates.xlsx"
RECORDS_FILE = "borrowed_records.xlsx"

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def load_books():
    """Load books from Excel with flexible column handling."""
    if not os.path.exists(BOOKS_FILE):
        st.warning("⚠️ books_realistic_dates.xlsx not found! Please upload one.")
        return pd.DataFrame(columns=["id", "title", "author", "price", "copies"])

    df = pd.read_excel(BOOKS_FILE)
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    mapping = {
        "book_title": "title",
        "bookname": "title",
        "book": "title",
        "writer": "author",
        "author_name": "author",
        "cost": "price",
        "amount": "price",
        "book_price": "price",
        "no_of_copies": "copies",
        "quantity": "copies",
        "stock": "copies"
    }
    df.rename(columns=mapping, inplace=True)

    for col in ["id", "title", "author", "price", "copies"]:
        if col not in df.columns:
            df[col] = None

    df.dropna(subset=["title"], inplace=True)
    df["copies"] = pd.to_numeric(df["copies"], errors="coerce").fillna(0).astype(int)
    df["copies"] = df["copies"].clip(lower=0)

    return df[["id", "title", "author", "price", "copies"]].reset_index(drop=True)


def save_books(df):
    df.to_excel(BOOKS_FILE, index=False)


def load_records():
    if os.path.exists(RECORDS_FILE):
        df = pd.read_excel(RECORDS_FILE)
        if "borrow_date" in df.columns:
            df["borrow_date"] = pd.to_datetime(df["borrow_date"], errors="coerce")
        if "return_date" in df.columns:
            df["return_date"] = pd.to_datetime(df["return_date"], errors="coerce")
        return df
    return pd.DataFrame(columns=["user", "title", "borrow_date", "return_date", "fine"])


def save_records(df):
    df.to_excel(RECORDS_FILE, index=False)


# -----------------------------
# INITIAL LOAD
# -----------------------------
books_df = load_books()
borrowed_records = load_records()

# -----------------------------
# LOGIN SYSTEM
# -----------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "role" not in st.session_state:
    st.session_state.role = None

st.sidebar.header("🔐 Login / Register")
login_mode = st.sidebar.radio("Select", ["Login", "Register"])
email = st.sidebar.text_input("Email")
password = st.sidebar.text_input("Password", type="password")

if login_mode == "Login":
    if st.sidebar.button("Login"):
        if email == "admin@library.com" and password == "admin":
            st.session_state.user = "Admin"
            st.session_state.role = "admin"
        else:
            if not email:
                st.sidebar.warning("Please enter your email to login.")
            else:
                st.session_state.user = email.split("@")[0].title()
                st.session_state.role = "user"
        st.rerun()
else:
    name = st.sidebar.text_input("Full Name")
    if st.sidebar.button("Register"):
        if not name or not email or not password:
            st.sidebar.warning("All fields required.")
        else:
            st.sidebar.success("✅ Registered successfully! You can now login.")

# -----------------------------
# MAIN APP
# -----------------------------
if st.session_state.user:
    st.sidebar.success(f"👋 Logged in as {st.session_state.user} ({st.session_state.role})")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.session_state.role = None
        st.rerun()

    # ------------------------------------------
    # ADMIN DASHBOARD
    # ------------------------------------------
    if st.session_state.role == "admin":
        tab1, tab2 = st.tabs(["📚 Manage Books", "📤 Upload / Replace Excel"])

        with tab1:
            st.subheader("📚 Library Book Records")
            if not books_df.empty:
                st.dataframe(books_df, use_container_width=True)
            else:
                st.info("No books found. Upload a valid Excel file.")

        with tab2:
            st.subheader("📤 Upload Excel to Replace Books")
            uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])
            if uploaded_file:
                df = pd.read_excel(uploaded_file)
                df.to_excel(BOOKS_FILE, index=False)
                st.success("✅ Book data replaced successfully!")
                st.rerun()

    # ------------------------------------------
    # USER DASHBOARD
    # ------------------------------------------
    else:
        tab1, tab2, tab3 = st.tabs(["🔍 Search Books", "📘 Borrow / Return", "📊 Your Records"])

        # 🔍 SEARCH BOOKS
        with tab1:
            st.subheader("🔍 Search Books from Library")
            if not books_df.empty:
                search = st.text_input("Search by Title or Author")
                if search:
                    filtered = books_df[
                        books_df["title"].str.contains(search, case=False, na=False) |
                        books_df["author"].str.contains(search, case=False, na=False)
                    ]
                    st.dataframe(filtered, use_container_width=True)
                else:
                    st.dataframe(books_df, use_container_width=True)
            else:
                st.info("📂 Upload 'books_realistic_dates.xlsx' first.")

        # 📘 BORROW / RETURN
        with tab2:
            st.subheader("📘 Borrow or Return Books")

            if books_df.empty:
                st.warning("📂 No books found. Please upload first.")
            else:
                books_df["copies"] = pd.to_numeric(books_df["copies"], errors="coerce").fillna(0).astype(int)

                # Borrow book section
                st.markdown("### 📗 Borrow a Book")
                available_books = books_df[books_df["copies"] > 0]
                if not available_books.empty:
                    selected_book = st.selectbox("Select Book to Borrow", available_books["title"].dropna().tolist())
                    if st.button("Borrow Book"):
                        books_df.loc[books_df["title"] == selected_book, "copies"] -= 1
                        save_books(books_df)

                        new_record = pd.DataFrame([{
                            "user": st.session_state.user,
                            "title": selected_book,
                            "borrow_date": pd.Timestamp.now(),
                            "return_date": pd.NaT,
                            "fine": 0
                        }])
                        borrowed_records = pd.concat([borrowed_records, new_record], ignore_index=True)
                        save_records(borrowed_records)

                        st.success(f"✅ '{selected_book}' borrowed successfully by {st.session_state.user}!")
                        st.rerun()
                else:
                    st.warning("⚠️ No books available to borrow right now.")

                st.divider()

                # Return book section
                st.markdown("### 📘 Return a Book")
                user_borrows = borrowed_records[
                    (borrowed_records["user"].str.lower() == st.session_state.user.lower()) &
                    (borrowed_records["return_date"].isna())
                ]

                if not user_borrows.empty:
                    return_choice = st.selectbox("Select Book to Return", user_borrows["title"].tolist())
                    if st.button("Return Book"):
                        borrowed_records.loc[
                            (borrowed_records["user"].str.lower() == st.session_state.user.lower()) &
                            (borrowed_records["title"] == return_choice) &
                            (borrowed_records["return_date"].isna()),
                            "return_date"
                        ] = pd.Timestamp.now()

                        books_df.loc[books_df["title"] == return_choice, "copies"] += 1
                        save_books(books_df)

                        borrow_date = user_borrows[user_borrows["title"] == return_choice]["borrow_date"].values[0]
                        borrow_date = pd.to_datetime(borrow_date)
                        days = (pd.Timestamp.now() - borrow_date).days
                        fine = max(0, (days - 7) * 5)
                        borrowed_records.loc[
                            (borrowed_records["user"].str.lower() == st.session_state.user.lower()) &
                            (borrowed_records["title"] == return_choice),
                            "fine"
                        ] = fine
                        save_records(borrowed_records)

                        st.info(f"📗 '{return_choice}' returned successfully by {st.session_state.user}! Fine: ₹{fine}")
                        st.rerun()
                else:
                    st.info("📘 You currently have no borrowed books.")

        # 📊 YOUR RECORDS
        with tab3:
            st.subheader("📊 Your Borrowing History")
            user_history = borrowed_records[
                borrowed_records["user"].str.lower() == st.session_state.user.lower()
            ]
            if not user_history.empty:
                st.dataframe(user_history, use_container_width=True)
            else:
                st.info("You haven’t borrowed any books yet.")
