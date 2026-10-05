import streamlit as st

import firebase_store


def _csv(values) -> str:
    return ", ".join(values or [])


def _split_csv(raw: str) -> list[str]:
    return [part.strip() for part in (raw or "").split(",") if part.strip()]


def render_admin(user: dict):
    st.title("Admin — Research catalog")
    st.caption(f"Logged in as {user.get('username')}. Changes are saved to Firestore.")

    try:
        projects = firebase_store.list_projects()
    except Exception as exc:
        st.error(f"Could not load projects: {exc}")
        return

    add_tab, edit_tab = st.tabs(["Add project", "Edit or remove project"])

    with add_tab:
        _project_form(existing=None)

    with edit_tab:
        if not projects:
            st.info("No projects yet. Add one from the other tab.")
            return
        labels = {f"{p.id} — {p.title}": p.id for p in projects}
        choice = st.selectbox("Select a project", list(labels.keys()))
        project_id = labels[choice]
        project = firebase_store.get_project(project_id)
        if project is None:
            st.error("Project no longer exists.")
            return
        _project_form(existing=project)
        enrollments = firebase_store.list_enrollments_for_project(project.id)
        st.subheader("Students on this project")
        if not enrollments:
            st.write("No students have joined yet.")
        else:
            for row in enrollments:
                st.write(f"- {row.get('student_name')} (`{row.get('student_username')}`)")


def _project_form(existing):
    is_new = existing is None
    default_id = firebase_store.next_project_id() if is_new else existing.id
    title = st.text_input("Title", value="" if is_new else existing.title, key=f"title_{default_id}_{is_new}")
    domain = st.text_input("Domain", value="" if is_new else existing.domain, key=f"domain_{default_id}_{is_new}")
    faculty = st.text_input("Faculty", value="" if is_new else existing.faculty, key=f"faculty_{default_id}_{is_new}")
    must_have = st.text_input(
        "Must-have skills (comma separated)",
        value="" if is_new else _csv(existing.must_have_skills),
        key=f"must_{default_id}_{is_new}",
    )
    nice_have = st.text_input(
        "Nice-to-have skills (comma separated)",
        value="" if is_new else _csv(existing.nice_to_have_skills),
        key=f"nice_{default_id}_{is_new}",
    )
    tags = st.text_input(
        "Interest tags (comma separated)",
        value="" if is_new else _csv(existing.interests_tags),
        key=f"tags_{default_id}_{is_new}",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        min_year = st.number_input(
            "Minimum year",
            min_value=1,
            max_value=4,
            value=1 if is_new else int(existing.min_year),
            key=f"year_{default_id}_{is_new}",
        )
    with col_b:
        min_availability = st.number_input(
            "Minimum weekly hours",
            min_value=0,
            max_value=40,
            value=6 if is_new else int(existing.min_availability),
            key=f"avail_{default_id}_{is_new}",
        )

    if is_new:
        if st.button("Add project", type="primary"):
            if not title.strip() or not domain.strip() or not faculty.strip():
                st.error("Title, domain, and faculty are required.")
                return
            if not _split_csv(must_have):
                st.error("Enter at least one must-have skill.")
                return
            project_id = firebase_store.next_project_id()
            firebase_store.save_project(
                {
                    "id": project_id,
                    "title": title.strip(),
                    "domain": domain.strip(),
                    "faculty": faculty.strip(),
                    "must_have_skills": _split_csv(must_have),
                    "nice_to_have_skills": _split_csv(nice_have),
                    "interests_tags": _split_csv(tags),
                    "min_year": int(min_year),
                    "min_availability": int(min_availability),
                }
            )
            st.success(f"Added {project_id}: {title.strip()}")
            st.rerun()
        return

    save_col, delete_col = st.columns(2)
    with save_col:
        if st.button("Save changes", type="primary"):
            if not title.strip() or not domain.strip() or not faculty.strip():
                st.error("Title, domain, and faculty are required.")
                return
            firebase_store.save_project(
                {
                    "id": existing.id,
                    "title": title.strip(),
                    "domain": domain.strip(),
                    "faculty": faculty.strip(),
                    "must_have_skills": _split_csv(must_have),
                    "nice_to_have_skills": _split_csv(nice_have),
                    "interests_tags": _split_csv(tags),
                    "min_year": int(min_year),
                    "min_availability": int(min_availability),
                }
            )
            st.success("Project updated.")
            st.rerun()
    with delete_col:
        confirm = st.checkbox(f"Confirm delete {existing.id}", key=f"del_{existing.id}")
        if st.button("Remove project", type="secondary"):
            if not confirm:
                st.error("Check the confirmation box first.")
                return
            firebase_store.delete_project(existing.id)
            st.success("Project removed.")
            st.rerun()
