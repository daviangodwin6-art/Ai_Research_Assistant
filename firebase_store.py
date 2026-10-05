import json
import os
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

from models import Faculty, Project, Student

load_dotenv()

ROOT = Path(__file__).resolve().parent
USERS = "users"
PROJECTS = "projects"
FACULTY = "faculty"
ENROLLMENTS = "enrollments"
META = "meta"

_db = None


def _service_account_path() -> Path:
    raw = (os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH") or "firebase-service-account.json").strip()
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def firebase_ready() -> tuple[bool, str]:
    if not (os.getenv("FIREBASE_API_KEY") or "").strip():
        return False, "Add FIREBASE_API_KEY to your .env file (Firebase project Web API key)."
    path = _service_account_path()
    if not path.exists():
        return (
            False,
            f"Firebase service account file not found at {path}. "
            "Download it from Firebase Console → Project settings → Service accounts.",
        )
    return True, ""


def get_db():
    global _db
    if _db is not None:
        return _db
    ready, message = firebase_ready()
    if not ready:
        raise RuntimeError(message)
    if not firebase_admin._apps:
        cred = credentials.Certificate(str(_service_account_path()))
        firebase_admin.initialize_app(cred)
    _db = firestore.client()
    return _db


def seed_if_needed():
    db = get_db()
    seeded = db.collection(META).document("seed").get()
    if seeded.exists and seeded.to_dict().get("done"):
        return
    projects_path = ROOT / "data" / "projects.json"
    faculty_path = ROOT / "data" / "faculty.json"
    if projects_path.exists():
        for item in json.loads(projects_path.read_text(encoding="utf-8")):
            db.collection(PROJECTS).document(item["id"]).set(item, merge=True)
    if faculty_path.exists():
        for item in json.loads(faculty_path.read_text(encoding="utf-8")):
            db.collection(FACULTY).document(item["name"]).set(item, merge=True)
    db.collection(META).document("seed").set(
        {"done": True, "seeded_at": firestore.SERVER_TIMESTAMP},
        merge=True,
    )


def _project_from_doc(doc) -> Project:
    data = doc.to_dict() or {}
    return Project(
        id=data.get("id") or doc.id,
        title=data.get("title", ""),
        domain=data.get("domain", ""),
        faculty=data.get("faculty", ""),
        must_have_skills=list(data.get("must_have_skills") or []),
        nice_to_have_skills=list(data.get("nice_to_have_skills") or []),
        interests_tags=list(data.get("interests_tags") or []),
        min_year=int(data.get("min_year") or 1),
        min_availability=int(data.get("min_availability") or 0),
    )


def list_projects() -> list[Project]:
    docs = get_db().collection(PROJECTS).stream()
    projects = [_project_from_doc(doc) for doc in docs]
    projects.sort(key=lambda p: p.id)
    return projects


def get_project(project_id: str) -> Project | None:
    doc = get_db().collection(PROJECTS).document(project_id).get()
    if not doc.exists:
        return None
    return _project_from_doc(doc)


def next_project_id() -> str:
    ids = [p.id for p in list_projects()]
    numbers = []
    for item in ids:
        if item.upper().startswith("P"):
            suffix = item[1:]
            if suffix.isdigit():
                numbers.append(int(suffix))
    return f"P{(max(numbers) + 1) if numbers else 1}"


def save_project(payload: dict):
    project_id = payload["id"]
    get_db().collection(PROJECTS).document(project_id).set(payload, merge=True)


def delete_project(project_id: str):
    db = get_db()
    db.collection(PROJECTS).document(project_id).delete()
    enrollments = db.collection(ENROLLMENTS).where("project_id", "==", project_id).stream()
    for doc in enrollments:
        doc.reference.delete()


def list_faculty() -> list[Faculty]:
    docs = get_db().collection(FACULTY).stream()
    faculty = []
    for doc in docs:
        data = doc.to_dict() or {}
        faculty.append(
            Faculty(
                name=data.get("name") or doc.id,
                department=data.get("department", ""),
                domains=list(data.get("domains") or []),
                lab=data.get("lab", ""),
            )
        )
    faculty.sort(key=lambda f: f.name)
    return faculty


def username_taken(username: str, exclude_uid: str | None = None) -> bool:
    query = (
        get_db()
        .collection(USERS)
        .where("username_lower", "==", username.strip().lower())
        .limit(2)
        .stream()
    )
    for doc in query:
        if exclude_uid and doc.id == exclude_uid:
            continue
        return True
    return False


def create_user_profile(uid: str, payload: dict):
    data = dict(payload)
    data["uid"] = uid
    data["username_lower"] = data["username"].strip().lower()
    data["created_at"] = firestore.SERVER_TIMESTAMP
    get_db().collection(USERS).document(uid).set(data, merge=True)


def get_user(uid: str) -> dict | None:
    doc = get_db().collection(USERS).document(uid).get()
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    data["uid"] = uid
    return data


def get_user_by_username(username: str) -> dict | None:
    query = (
        get_db()
        .collection(USERS)
        .where("username_lower", "==", username.strip().lower())
        .limit(1)
        .stream()
    )
    for doc in query:
        data = doc.to_dict() or {}
        data["uid"] = doc.id
        return data
    return None


def get_user_by_email(email: str) -> dict | None:
    query = (
        get_db()
        .collection(USERS)
        .where("email", "==", email.strip().lower())
        .limit(1)
        .stream()
    )
    for doc in query:
        data = doc.to_dict() or {}
        data["uid"] = doc.id
        return data
    return None


def update_student_profile(uid: str, student: Student):
    get_db().collection(USERS).document(uid).set(
        {
            "name": student.name,
            "year": student.year,
            "department": student.department,
            "skills": student.skills,
            "interests": student.interests,
            "academic_background": student.academic_background,
            "projects": student.projects,
            "research_interests": student.research_interests,
            "availability_hours": student.availability_hours,
            "updated_at": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def list_students() -> list[Student]:
    docs = get_db().collection(USERS).where("role", "==", "student").stream()
    students = []
    for doc in docs:
        data = doc.to_dict() or {}
        students.append(
            Student(
                name=data.get("name") or data.get("username") or "Student",
                year=int(data.get("year") or 1),
                department=data.get("department") or "CSE",
                skills=list(data.get("skills") or []),
                interests=list(data.get("interests") or []),
                academic_background=data.get("academic_background") or "",
                projects=list(data.get("projects") or []),
                research_interests=list(data.get("research_interests") or []),
                availability_hours=int(data.get("availability_hours") or 8),
            )
        )
    return students


def join_project(user: dict, project: Project):
    enrollment_id = f"{user['uid']}_{project.id}"
    get_db().collection(ENROLLMENTS).document(enrollment_id).set(
        {
            "student_uid": user["uid"],
            "student_username": user.get("username", ""),
            "student_name": user.get("name") or user.get("username", ""),
            "project_id": project.id,
            "project_title": project.title,
            "domain": project.domain,
            "faculty": project.faculty,
            "joined_at": firestore.SERVER_TIMESTAMP,
            "status": "active",
        }
    )


def leave_project(uid: str, project_id: str):
    get_db().collection(ENROLLMENTS).document(f"{uid}_{project_id}").delete()


def list_enrollments_for_student(uid: str) -> list[dict]:
    docs = get_db().collection(ENROLLMENTS).where("student_uid", "==", uid).stream()
    rows = []
    for doc in docs:
        data = doc.to_dict() or {}
        data["id"] = doc.id
        rows.append(data)
    rows.sort(key=lambda r: r.get("project_title") or "")
    return rows


def list_enrollments_for_project(project_id: str) -> list[dict]:
    docs = get_db().collection(ENROLLMENTS).where("project_id", "==", project_id).stream()
    rows = []
    for doc in docs:
        data = doc.to_dict() or {}
        data["id"] = doc.id
        rows.append(data)
    rows.sort(key=lambda r: (r.get("student_name") or "").lower())
    return rows


def student_from_user(user: dict) -> Student:
    return Student(
        name=user.get("name") or user.get("username") or "",
        year=int(user.get("year") or 1),
        department=user.get("department") or "CSE",
        skills=list(user.get("skills") or []),
        interests=list(user.get("interests") or []),
        academic_background=user.get("academic_background") or "",
        projects=list(user.get("projects") or []),
        research_interests=list(user.get("research_interests") or []),
        availability_hours=int(user.get("availability_hours") or 8),
    )


def format_joined_at(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date().isoformat()
    return str(value)[:10]
