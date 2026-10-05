import re


def basic_input_check(name, skills, interests, academic_background):
    """
    Fast, free, deterministic sanity checks -- run before the AI check.
    Catches the obvious stuff without spending an API call on it.
    """
    issues = []

    if not name or len(name.strip()) < 2:
        issues.append("Name looks incomplete.")

    if not skills:
        issues.append("No skills entered.")

    if not interests:
        issues.append("No interests entered.")

    if not academic_background or len(academic_background.strip()) < 5:
        issues.append("Academic background looks too short to be useful.")

    # catches things like "aaaa", "xxxxxx", "asdasd" repeated patterns
    for s in skills + interests:
        if re.fullmatch(r"(.)\1{2,}", s.lower().replace(" ", "")):
            issues.append(f"'{s}' looks like a placeholder or typo, not a real entry.")
        elif len(s.strip()) < 2:
            issues.append(f"'{s}' is too short to be a valid entry.")

    return issues