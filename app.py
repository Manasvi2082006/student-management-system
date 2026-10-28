import streamlit as st
import pandas as pd
import sqlite3
import os
import shutil
import io
from datetime import datetime

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Student Management System",
    page_icon="🎓",
    layout="wide"
)

# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Original database is in project root
DEFAULT_DATABASE = os.path.join(
    BASE_DIR,
    "student_database.db"
)

# Other databases
DATABASE_DIR = os.path.join(
    BASE_DIR,
    "databases"
)

BACKUP_DIR = os.path.join(
    BASE_DIR,
    "backups"
)

os.makedirs(DATABASE_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# ============================================================
# DATABASE FUNCTIONS
# ============================================================

REQUIRED_COLUMNS = [
    "id",
    "name",
    "age",
    "gender",
    "city",
    "course",
    "email"
]


def get_connection(db_path):
    return sqlite3.connect(db_path)


def get_databases():

    databases = []

    # Original database
    if os.path.exists(DEFAULT_DATABASE):
        databases.append(DEFAULT_DATABASE)

    # Databases folder
    if os.path.exists(DATABASE_DIR):

        for file in os.listdir(DATABASE_DIR):

            if file.lower().endswith(".db"):

                path = os.path.join(
                    DATABASE_DIR,
                    file
                )

                if path not in databases:
                    databases.append(path)

    return databases


def get_table_columns(db_path):

    conn = get_connection(db_path)

    try:
        cursor = conn.cursor()

        cursor.execute(
            "PRAGMA table_info(students)"
        )

        columns = [
            row[1]
            for row in cursor.fetchall()
        ]

        return columns

    finally:
        conn.close()


def students_table_exists(db_path):

    if not os.path.exists(db_path):
        return False

    conn = get_connection(db_path)

    try:

        cursor = conn.cursor()

        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            AND name='students'
        """)

        return cursor.fetchone() is not None

    finally:
        conn.close()


def prepare_database(db_path):

    """
    Makes older databases compatible with
    Gender and Email columns.
    """

    if not students_table_exists(db_path):
        return False

    conn = get_connection(db_path)

    try:

        cursor = conn.cursor()

        columns = get_table_columns(db_path)

        # Add gender if missing
        if "gender" not in columns:

            cursor.execute("""
                ALTER TABLE students
                ADD COLUMN gender TEXT
            """)

        # Add email if missing
        if "email" not in columns:

            cursor.execute("""
                ALTER TABLE students
                ADD COLUMN email TEXT
            """)

        conn.commit()

        return True

    except Exception as e:

        st.error(f"Database preparation error: {e}")

        return False

    finally:
        conn.close()


def get_students(db_path):

    prepare_database(db_path)

    conn = get_connection(db_path)

    try:

        query = """
            SELECT
                id,
                name,
                age,
                gender,
                city,
                course,
                email
            FROM students
            ORDER BY id
        """

        df = pd.read_sql_query(
            query,
            conn
        )

        # ----------------------------------------------------
        # CLEAN INVALID STUDENT IDs
        # SQLite records with a NULL ID can appear as NaN in
        # pandas. Remove them from the app so they never appear
        # in Update/Delete dropdowns or break row selection.
        # ----------------------------------------------------
        if "id" in df.columns:
            df["id"] = pd.to_numeric(df["id"], errors="coerce")
            df = df.dropna(subset=["id"]).copy()
            df = df[df["id"] > 0].copy()

            # Display/use whole-number IDs as integers, not 1.0.
            df = df[df["id"] % 1 == 0].copy()
            df["id"] = df["id"].astype("int64")

        # Replace missing text values so forms do not show the
        # literal text 'nan' for name, city, course, etc.
        for column in ["name", "gender", "city", "course", "email"]:
            if column in df.columns:
                df[column] = df[column].where(df[column].notna(), "")

        # Keep missing ages safe for the update form.
        if "age" in df.columns:
            df["age"] = pd.to_numeric(df["age"], errors="coerce")

        return df.reset_index(drop=True)

    except Exception as e:

        st.error(
            f"Unable to read database: {e}"
        )

        return pd.DataFrame(
            columns=REQUIRED_COLUMNS
        )

    finally:
        conn.close()


def add_student(
    db_path,
    name,
    age,
    gender,
    city,
    course,
    email
):

    conn = get_connection(db_path)

    try:

        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO students
            (
                name,
                age,
                gender,
                city,
                course,
                email
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            name,
            age,
            gender,
            city,
            course,
            email
        ))

        conn.commit()

    finally:
        conn.close()


def update_student(
    db_path,
    student_id,
    name,
    age,
    gender,
    city,
    course,
    email
):

    conn = get_connection(db_path)

    try:

        cursor = conn.cursor()

        cursor.execute("""
            UPDATE students
            SET
                name=?,
                age=?,
                gender=?,
                city=?,
                course=?,
                email=?
            WHERE id=?
        """, (
            name,
            age,
            gender,
            city,
            course,
            email,
            student_id
        ))

        conn.commit()

    finally:
        conn.close()


def delete_student(db_path, student_id):

    conn = get_connection(db_path)

    try:

        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                name,
                age,
                gender,
                city,
                course,
                email
            FROM students
            WHERE id=?
        """, (student_id,))

        student = cursor.fetchone()

        if student:

            cursor.execute(
                "DELETE FROM students WHERE id=?",
                (student_id,)
            )

            conn.commit()

        return student

    finally:
        conn.close()


def insert_deleted_student(db_path, student):

    conn = get_connection(db_path)

    try:

        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO students
            (
                id,
                name,
                age,
                gender,
                city,
                course,
                email
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, student)

        conn.commit()

    finally:
        conn.close()


def bulk_delete(db_path, ids):

    conn = get_connection(db_path)

    try:

        cursor = conn.cursor()

        placeholders = ",".join(
            ["?"] * len(ids)
        )

        cursor.execute(
            f"""
            SELECT
                id,
                name,
                age,
                gender,
                city,
                course,
                email
            FROM students
            WHERE id IN ({placeholders})
            """,
            ids
        )

        deleted = cursor.fetchall()

        cursor.execute(
            f"""
            DELETE FROM students
            WHERE id IN ({placeholders})
            """,
            ids
        )

        conn.commit()

        return deleted

    finally:
        conn.close()


# ============================================================
# BACKUP FUNCTIONS
# ============================================================

def create_backup(db_path):

    if not os.path.exists(db_path):
        return None

    filename = os.path.basename(db_path)

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_name = (
        f"{os.path.splitext(filename)[0]}"
        f"_backup_{timestamp}.db"
    )

    backup_path = os.path.join(
        BACKUP_DIR,
        backup_name
    )

    shutil.copy2(
        db_path,
        backup_path
    )

    return backup_path


def restore_database(db_path, backup_path):

    if not os.path.exists(backup_path):
        return False

    shutil.copy2(
        backup_path,
        db_path
    )

    return True


# ============================================================
# ACTIVITY LOG
# ============================================================

def add_activity(message):

    if "activity_log" not in st.session_state:
        st.session_state.activity_log = []

    time = datetime.now().strftime(
        "%d-%m-%Y %H:%M:%S"
    )

    st.session_state.activity_log.insert(
        0,
        f"{time} - {message}"
    )

    # Keep last 100 activities
    st.session_state.activity_log = (
        st.session_state.activity_log[:100]
    )


# ============================================================
# SESSION STATE
# ============================================================

if "selected_database" not in st.session_state:
    st.session_state.selected_database = None

if "operation" not in st.session_state:
    st.session_state.operation = None

if "undo_data" not in st.session_state:
    st.session_state.undo_data = []

if "activity_log" not in st.session_state:
    st.session_state.activity_log = []


# ============================================================
# DATABASE LIST
# ============================================================

databases = get_databases()

if not databases:

    st.error(
        "No SQLite databases were found."
    )

    st.stop()


database_names = [
    os.path.basename(path)
    for path in databases
]


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title("🎓 Student Management")

    st.divider()

    st.subheader("📁 Select Database")

    selected_name = st.selectbox(
        "Choose database",
        database_names
    )

    selected_database = databases[
        database_names.index(selected_name)
    ]

    st.session_state.selected_database = (
        selected_database
    )

    st.caption(
        f"Database: {selected_name}"
    )

    st.divider()

    st.subheader("💾 Database Backup")

    if st.button(
        "📦 Create Backup",
        use_container_width=True
    ):

        backup = create_backup(
            selected_database
        )

        if backup:

            st.success(
                "Backup created successfully!"
            )

            add_activity(
                f"Backup created: "
                f"{os.path.basename(backup)}"
            )

    st.divider()

    st.subheader("📥 Restore Backup")

    backup_files = []

    if os.path.exists(BACKUP_DIR):

        backup_files = [
            f
            for f in os.listdir(BACKUP_DIR)
            if f.endswith(".db")
        ]

    if backup_files:

        selected_backup = st.selectbox(
            "Select backup",
            backup_files
        )

        if st.button(
            "♻️ Restore",
            use_container_width=True
        ):

            backup_path = os.path.join(
                BACKUP_DIR,
                selected_backup
            )

            restore_database(
                selected_database,
                backup_path
            )

            st.success(
                "Database restored!"
            )

            add_activity(
                f"Database restored from "
                f"{selected_backup}"
            )

            st.rerun()

    else:

        st.info(
            "No backups available."
        )

    st.divider()

    st.subheader("📜 Activity Log")

    if st.session_state.activity_log:

        for activity in (
            st.session_state.activity_log[:10]
        ):

            st.caption(activity)

    else:

        st.caption(
            "No activity yet."
        )


# ============================================================
# PREPARE DATABASE
# ============================================================

prepare_database(
    selected_database
)


# ============================================================
# LOAD DATA
# ============================================================

df = get_students(
    selected_database
)


# ============================================================
# TITLE
# ============================================================

st.title("🎓 Student Management System")

st.write(
    f"Currently selected database: "
    f"**{selected_name}**"
)


# ============================================================
# DASHBOARD
# ============================================================

st.subheader("📊 Dashboard")

total_students = len(df)

if total_students > 0:

    unique_cities = df["city"].nunique()

    unique_courses = df["course"].nunique()

    male_count = (
        df["gender"]
        .fillna("")
        .astype(str)
        .str.lower()
        .eq("male")
        .sum()
    )

    female_count = (
        df["gender"]
        .fillna("")
        .astype(str)
        .str.lower()
        .eq("female")
        .sum()
    )

else:

    unique_cities = 0
    unique_courses = 0
    male_count = 0
    female_count = 0


col1, col2, col3, col4, col5 = st.columns(5)

col1.metric(
    "👨‍🎓 Total Students",
    total_students
)

col2.metric(
    "🏙️ Cities",
    unique_cities
)

col3.metric(
    "📚 Courses",
    unique_courses
)

col4.metric(
    "👨 Male",
    male_count
)

col5.metric(
    "👩 Female",
    female_count
)


# ============================================================
# SEARCH AND FILTER
# ============================================================

st.subheader("🔎 Search & Filter")

filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

with filter_col1:

    search = st.text_input(
        "Search",
        placeholder=(
            "Search ID, name, email, city..."
        )
    )

with filter_col2:

    city_options = ["All"] + sorted(
        df["city"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_city = st.selectbox(
        "City",
        city_options
    )

with filter_col3:

    course_options = ["All"] + sorted(
        df["course"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_course = st.selectbox(
        "Course",
        course_options
    )

with filter_col4:

    gender_options = ["All"] + sorted(
        df["gender"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    selected_gender = st.selectbox(
        "Gender",
        gender_options
    )


# ============================================================
# FILTER DATA
# ============================================================

filtered_df = df.copy()


if search:

    search_text = search.lower()

    mask = (
        filtered_df.astype(str)
        .apply(
            lambda row:
            row.str.lower()
            .str.contains(
                search_text,
                na=False
            )
        )
        .any(axis=1)
    )

    filtered_df = filtered_df[mask]


if selected_city != "All":

    filtered_df = filtered_df[
        filtered_df["city"]
        == selected_city
    ]


if selected_course != "All":

    filtered_df = filtered_df[
        filtered_df["course"]
        == selected_course
    ]


if selected_gender != "All":

    filtered_df = filtered_df[
        filtered_df["gender"]
        == selected_gender
    ]


# ============================================================
# STUDENT RECORDS
# ============================================================

st.subheader("📋 Student Records")

st.caption(
    f"Showing {len(filtered_df)} "
    f"of {len(df)} records"
)


# ============================================================
# EXPORT BUTTONS
# ============================================================

export_col1, export_col2, export_col3, export_col4 = st.columns(4)


# CSV
with export_col1:

    csv_data = filtered_df.to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        label="📄 CSV",
        data=csv_data,
        file_name="student_records.csv",
        mime="text/csv",
        use_container_width=True
    )


# TXT
with export_col2:

    txt_data = filtered_df.to_string(
        index=False
    )

    st.download_button(
        label="📝 TXT",
        data=txt_data,
        file_name="student_records.txt",
        mime="text/plain",
        use_container_width=True
    )


# Excel
with export_col3:

    excel_buffer = io.BytesIO()

    with pd.ExcelWriter(
        excel_buffer,
        engine="openpyxl"
    ) as writer:

        filtered_df.to_excel(
            writer,
            index=False,
            sheet_name="Students"
        )

    st.download_button(
        label="📊 Excel",
        data=excel_buffer.getvalue(),
        file_name="student_records.xlsx",
        mime=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True
    )


# PDF
with export_col4:

    try:

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, A4
        from reportlab.platypus import (
            SimpleDocTemplate,
            Table,
            TableStyle
        )

        pdf_buffer = io.BytesIO()

        document = SimpleDocTemplate(
            pdf_buffer,
            pagesize=landscape(A4)
        )

        pdf_data = [
            filtered_df.columns.tolist()
        ]

        for row in filtered_df.itertuples(
            index=False
        ):

            pdf_data.append(
                [str(value) for value in row]
            )

        table = Table(
            pdf_data,
            repeatRows=1
        )

        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.grey
                ),
                (
                    "TEXTCOLOR",
                    (0, 0),
                    (-1, 0),
                    colors.white
                ),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    colors.black
                ),
                (
                    "FONTSIZE",
                    (0, 0),
                    (-1, -1),
                    7
                )
            ])
        )

        document.build([table])

        st.download_button(
            label="📕 PDF",
            data=pdf_buffer.getvalue(),
            file_name="student_records.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    except ImportError:

        st.warning(
            "Install reportlab for PDF export:"
        )

        st.code(
            "python -m pip install reportlab"
        )


# ============================================================
# DISPLAY TABLE
# ============================================================

st.dataframe(
    filtered_df,
    use_container_width=True,
    hide_index=True
)


# ============================================================
# CRUD BUTTONS
# ============================================================

st.divider()

st.subheader("⚙️ Student Operations")

button_col1, button_col2, button_col3, button_col4, button_col5 = st.columns(5)


with button_col1:

    if st.button(
        "➕ ADD",
        use_container_width=True
    ):

        st.session_state.operation = "add"


with button_col2:

    if st.button(
        "✏️ UPDATE",
        use_container_width=True
    ):

        st.session_state.operation = "update"


with button_col3:

    if st.button(
        "🗑️ DELETE",
        use_container_width=True
    ):

        st.session_state.operation = "delete"


with button_col4:

    if st.button(
        "☑️ BULK DELETE",
        use_container_width=True
    ):

        st.session_state.operation = "bulk_delete"


with button_col5:

    if st.button(
        "↩️ UNDO DELETE",
        use_container_width=True
    ):

        st.session_state.operation = "undo"


# ============================================================
# ADD FORM
# ============================================================

if st.session_state.operation == "add":

    st.divider()

    st.subheader("➕ Add Student")

    with st.form("add_student_form"):

        col1, col2, col3 = st.columns(3)

        with col1:

            name = st.text_input(
                "Name *"
            )

            age = st.number_input(
                "Age *",
                min_value=1,
                max_value=100,
                value=20
            )

        with col2:

            gender = st.selectbox(
                "Gender *",
                [
                    "Male",
                    "Female",
                    "Other"
                ]
            )

            city = st.selectbox(
                "City *",
                [
                    "Ahmedabad",
                    "Surat",
                    "Rajkot",
                    "Vadodara",
                    "Bhavnagar"
                ]
            )

        with col3:

            course = st.selectbox(
                "Course *",
                [
                    "Python",
                    "Data Science",
                    "Data Analytics",
                    "Machine Learning",
                    "Web Development"
                ]
            )

            email = st.text_input(
                "Email *"
            )

        submit = st.form_submit_button(
            "➕ Add Student",
            use_container_width=True
        )

        if submit:

            if not name.strip():

                st.error(
                    "Please enter student name."
                )

            elif not email.strip():

                st.error(
                    "Please enter email."
                )

            else:

                add_student(
                    selected_database,
                    name.strip(),
                    age,
                    gender,
                    city,
                    course,
                    email.strip()
                )

                add_activity(
                    f"Added student: {name}"
                )

                st.success(
                    "Student added successfully!"
                )

                st.session_state.operation = None

                st.rerun()


# ============================================================
# UPDATE FORM
# ============================================================

elif st.session_state.operation == "update":

    st.divider()

    st.subheader("✏️ Update Student")

    if len(df) == 0:

        st.warning(
            "No students available."
        )

    else:

        student_ids = df["id"].tolist()

        selected_id = st.selectbox(
            "Select Student ID",
            student_ids
        )

        selected_row = df[
            df["id"] == selected_id
        ].iloc[0]

        with st.form("update_student_form"):

            col1, col2, col3 = st.columns(3)

            with col1:

                new_name = st.text_input(
                    "Name",
                    value=str(
                        selected_row["name"]
                    )
                )

                new_age = st.number_input(
                    "Age",
                    min_value=1,
                    max_value=100,
                    value=(
                        max(1, min(100, int(selected_row["age"])))
                        if pd.notna(selected_row["age"])
                        else 20
                    )
                )

            with col2:

                gender_values = [
                    "Male",
                    "Female",
                    "Other"
                ]

                current_gender = str(
                    selected_row["gender"]
                )

                gender_index = (
                    gender_values.index(
                        current_gender
                    )
                    if current_gender
                    in gender_values
                    else 0
                )

                new_gender = st.selectbox(
                    "Gender",
                    gender_values,
                    index=gender_index
                )

                city_values = [
                    "Ahmedabad",
                    "Surat",
                    "Rajkot",
                    "Vadodara",
                    "Bhavnagar"
                ]

                current_city = str(
                    selected_row["city"]
                )

                city_index = (
                    city_values.index(
                        current_city
                    )
                    if current_city
                    in city_values
                    else 0
                )

                new_city = st.selectbox(
                    "City",
                    city_values,
                    index=city_index
                )

            with col3:

                course_values = [
                    "Python",
                    "Data Science",
                    "Data Analytics",
                    "Machine Learning",
                    "Web Development"
                ]

                current_course = str(
                    selected_row["course"]
                )

                course_index = (
                    course_values.index(
                        current_course
                    )
                    if current_course
                    in course_values
                    else 0
                )

                new_course = st.selectbox(
                    "Course",
                    course_values,
                    index=course_index
                )

                new_email = st.text_input(
                    "Email",
                    value=str(
                        selected_row["email"]
                    )
                )

            update_button = st.form_submit_button(
                "💾 Save Changes",
                use_container_width=True
            )

            if update_button:

                update_student(
                    selected_database,
                    selected_id,
                    new_name.strip(),
                    new_age,
                    new_gender,
                    new_city,
                    new_course,
                    new_email.strip()
                )

                add_activity(
                    f"Updated student ID: "
                    f"{selected_id}"
                )

                st.success(
                    "Student updated successfully!"
                )

                st.session_state.operation = None

                st.rerun()


# ============================================================
# DELETE FORM
# ============================================================

elif st.session_state.operation == "delete":

    st.divider()

    st.subheader("🗑️ Delete Student")

    if len(df) == 0:

        st.warning(
            "No students available."
        )

    else:

        student_ids = df["id"].tolist()

        selected_id = st.selectbox(
            "Select Student ID",
            student_ids
        )

        row = df[
            df["id"] == selected_id
        ].iloc[0]

        st.warning(
            f"You are about to delete: "
            f"**{row['name']}**"
        )

        if st.button(
            "🗑️ Confirm Delete",
            type="primary"
        ):

            deleted = delete_student(
                selected_database,
                selected_id
            )

            if deleted:

                st.session_state.undo_data = [
                    deleted
                ]

                add_activity(
                    f"Deleted student ID: "
                    f"{selected_id}"
                )

                st.success(
                    "Student deleted successfully!"
                )

                st.session_state.operation = None

                st.rerun()


# ============================================================
# BULK DELETE
# ============================================================

elif st.session_state.operation == "bulk_delete":

    st.divider()

    st.subheader("☑️ Bulk Delete")

    if len(filtered_df) == 0:

        st.warning(
            "No records available for deletion."
        )

    else:

        selected_ids = st.multiselect(
            "Select student IDs to delete",
            filtered_df["id"].tolist()
        )

        st.write(
            f"Selected: **{len(selected_ids)}** students"
        )

        if st.button(
            "🗑️ Delete Selected Students",
            type="primary"
        ):

            if not selected_ids:

                st.error(
                    "Please select at least one student."
                )

            else:

                deleted = bulk_delete(
                    selected_database,
                    selected_ids
                )

                st.session_state.undo_data = deleted

                add_activity(
                    f"Bulk deleted "
                    f"{len(deleted)} students"
                )

                st.success(
                    f"{len(deleted)} students deleted!"
                )

                st.session_state.operation = None

                st.rerun()


# ============================================================
# UNDO DELETE
# ============================================================

elif st.session_state.operation == "undo":

    st.divider()

    st.subheader("↩️ Undo Delete")

    if not st.session_state.undo_data:

        st.info(
            "There is nothing to undo."
        )

    else:

        count = len(
            st.session_state.undo_data
        )

        st.warning(
            f"Restore {count} deleted "
            f"student(s)?"
        )

        if st.button(
            "↩️ Restore Deleted Student(s)",
            type="primary"
        ):

            for student in (
                st.session_state.undo_data
            ):

                insert_deleted_student(
                    selected_database,
                    student
                )

            add_activity(
                f"Restored {count} deleted students"
            )

            st.session_state.undo_data = []

            st.success(
                "Deleted students restored!"
            )

            st.session_state.operation = None

            st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "🎓 Student Management System | "
    "SQLite + Streamlit"
)