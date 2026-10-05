import os

import streamlit as st
from dotenv import load_dotenv

import firebase_auth
import firebase_store
from password_gate import signup_issues

load_dotenv()


def _reset_app_state():
    keep = {"user"}
    for key in list(st.session_state.keys()):
        if key not in keep:
            del st.session_state[key]


def render_sidebar(user: dict):
    with st.sidebar:
        st.markdown(f"**Signed in as** `{user.get('username')}`")
        st.caption(user.get("role", "").title())
        if st.button("Log out", use_container_width=True):
            _reset_app_state()
            st.session_state.pop("user", None)
            st.rerun()


def render_login_gate() -> dict | None:
    ready, message = firebase_store.firebase_ready()
    if not ready:
        st.error(message)
        st.markdown(
            """
            **Firebase setup (once):**
            1. Create a Firebase project and enable **Authentication → Email/Password**.
            2. Create a **Firestore** database (start in test mode for the hackathon, then lock rules down).
            3. Copy the Web **API key** into `.env` as `FIREBASE_API_KEY`.
            4. Project settings → Service accounts → **Generate new private key**, save as `firebase-service-account.json`.
            5. Set `ADMIN_INVITE_CODE` in `.env` so only you can create an admin account.
            """
        )
        return None

    try:
        firebase_store.seed_if_needed()
    except Exception as exc:
        st.error(f"Could not connect to Firestore: {exc}")
        return None

    st.title("Research Opportunity Matcher")
    st.caption("Sign in to find labs, join a project, or manage the catalog as admin.")

    login_tab, student_tab, admin_tab = st.tabs(["Log in", "Create student account", "Create admin account"])

    with login_tab:
        _render_login()
    with student_tab:
        _render_student_signup()
    with admin_tab:
        _render_admin_signup()
    return None


def _render_login():
    username_or_email = st.text_input("Username or email", key="login_id")
    password = st.text_input("Password", type="password", key="login_password")
    if st.button("Log in", use_container_width=True, type="primary"):
        ident = username_or_email.strip()
        if not ident or not password:
            st.error("Enter your username/email and password.")
            return
        try:
            if "@" in ident:
                email = ident.lower()
            else:
                profile = firebase_store.get_user_by_username(ident)
                if not profile:
                    st.error("No account found for that username.")
                    return
                email = profile["email"]
            auth = firebase_auth.sign_in(email, password)
            user = firebase_store.get_user(auth["localId"])
            if not user:
                st.error("This login exists in Firebase Auth but has no profile in the database. Create the account again from the signup tab.")
                return
            st.session_state.user = user
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def _render_student_signup():
    st.write("New students: create an account. Your profile is stored in Firestore and used on later logins.")
    username = st.text_input("Username", key="stu_username")
    email = st.text_input("Email", key="stu_email")
    password = st.text_input("Password", type="password", key="stu_password")
    st.caption("Password: at least 8 characters, with a letter and a number.")
    left, right = st.columns(2)
    with left:
        year = st.number_input("Year", min_value=1, max_value=4, value=1, key="stu_year")
    with right:
        department = st.text_input("Department", value="CSE", key="stu_department")
    if st.button("Create student account", use_container_width=True):
        issues = signup_issues(username, email, password, year, department, role="student")
        if issues:
            for issue in issues:
                st.error(issue)
            return
        try:
            if firebase_store.username_taken(username):
                st.error("That username is already taken.")
                return
            auth = firebase_auth.sign_up(email.strip().lower(), password)
            firebase_store.create_user_profile(
                auth["localId"],
                {
                    "username": username.strip(),
                    "email": email.strip().lower(),
                    "role": "student",
                    "name": username.strip(),
                    "year": int(year),
                    "department": department.strip(),
                    "skills": [],
                    "interests": [],
                    "academic_background": "",
                    "projects": [],
                    "research_interests": [],
                    "availability_hours": 8,
                },
            )
            user = firebase_store.get_user(auth["localId"])
            st.session_state.user = user
            st.rerun()
        except Exception as exc:
            st.error(str(exc))


def _render_admin_signup():
    st.write("Admins can add, edit, and remove research projects. An invite code from `.env` is required.")
    username = st.text_input("Admin username", key="adm_username")
    email = st.text_input("Admin email", key="adm_email")
    password = st.text_input("Admin password", type="password", key="adm_password")
    invite = st.text_input("Admin invite code", type="password", key="adm_invite")
    if st.button("Create admin account", use_container_width=True):
        expected = (os.getenv("ADMIN_INVITE_CODE") or "").strip()
        if not expected:
            st.error("ADMIN_INVITE_CODE is not set in .env, so admin signup is disabled.")
            return
        if invite.strip() != expected:
            st.error("Invite code is incorrect.")
            return
        issues = signup_issues(username, email, password, 1, "Admin", role="admin")
        if issues:
            for issue in issues:
                st.error(issue)
            return
        try:
            if firebase_store.username_taken(username):
                st.error("That username is already taken.")
                return
            auth = firebase_auth.sign_up(email.strip().lower(), password)
            firebase_store.create_user_profile(
                auth["localId"],
                {
                    "username": username.strip(),
                    "email": email.strip().lower(),
                    "role": "admin",
                    "name": username.strip(),
                    "year": 0,
                    "department": "Admin",
                    "skills": [],
                    "interests": [],
                    "academic_background": "",
                    "projects": [],
                    "research_interests": [],
                    "availability_hours": 0,
                },
            )
            user = firebase_store.get_user(auth["localId"])
            st.session_state.user = user
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
