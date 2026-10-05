import json
from models import Student, Project
from matcher import rank_projects
from ai_layer import explain_match, skill_gap_and_pathway, ask_assistant


def load_students(path="data/students.json"):
    with open(path) as f:
        return [Student(**s) for s in json.load(f)]


def load_projects(path="data/projects.json"):
    with open(path) as f:
        return [Project(**p) for p in json.load(f)]


def main():
    students = load_students()
    projects = load_projects()

    student = students[0]

    ranked = rank_projects(student, projects)

    print(f"\n=== Top matches for {student.name} ===")
    for r in ranked[:3]:
        print(f"{r['title']:35s} {r['score']}%  (eligible: {r['eligible']})")

    top = ranked[0]

    print(f"\n=== AI Explanation for top match: {top['title']} ===")
    print(explain_match(student, top))

    print(f"\n=== Skill Gap & Learning Pathway ===")
    pathway = skill_gap_and_pathway(student, top)
    print(pathway.get("skill_gap", ""))
    for i, step in enumerate(pathway.get("steps", []), start=1):
        print(f"  Step {i}: {step['title']} -- {step['description']}")

    print(f"\n=== AI Research Assistant demo ===")
    question = "I don't have PyTorch experience. Can I still apply?"
    print(f"Student: {question}")
    print("AI:", ask_assistant(student, top, question))


if __name__ == "__main__":
    main()