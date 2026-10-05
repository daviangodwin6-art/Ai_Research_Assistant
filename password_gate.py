import re

USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,19}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def password_issues(password: str) -> list[str]:
    issues = []
    if not password or len(password) < 8:
        issues.append("Password must be at least 8 characters.")
    if not re.search(r"[A-Za-z]", password or ""):
        issues.append("Password must include at least one letter.")
    if not re.search(r"\d", password or ""):
        issues.append("Password must include at least one number.")
    return issues


def signup_issues(username, email, password, year, department, role="student") -> list[str]:
    issues = []
    username = (username or "").strip()
    email = (email or "").strip()
    department = (department or "").strip()

    if not USERNAME_RE.match(username):
        issues.append(
            "Username must be 3–20 characters, start with a letter, and use only letters, numbers, or underscore."
        )
    if not EMAIL_RE.match(email):
        issues.append("Enter a valid email address.")
    issues.extend(password_issues(password))
    try:
        year_n = int(year)
        if year_n < 1 or year_n > 4:
            issues.append("Year must be between 1 and 4.")
    except (TypeError, ValueError):
        issues.append("Year must be a number between 1 and 4.")
    if role == "student" and len(department) < 2:
        issues.append("Department is required.")
    return issues
