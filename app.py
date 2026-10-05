import streamlit as st

from models import Student
from matcher import rank_projects, suggest_teammates
from ai_layer import explain_match, skill_gap_and_pathway, ask_assistant, validate_profile, suggest_starting_point
from validator import basic_input_check
import firebase_store
import auth_ui
import admin_page


def clean_html(raw):
    """
    Strips any whitespace-only line out of a raw multi-line HTML string
    before it reaches st.markdown.

    Several of this file's card templates interpolate an optional
    fragment on its own line -- e.g. the "missing core skill" badge,
    which is "" when it doesn't apply. Streamlit's markdown renderer
    treats a line containing only whitespace as a blank line, and a blank
    line inside a raw HTML block silently ends that block. Everything
    after it then falls back to plain Markdown, and because it's still
    indented (from the source file's own indentation), it gets rendered
    as a literal, escaped code block instead of styled HTML -- which is
    exactly the "<div class=match-meta>...</div>" text that was showing
    up under "Top Matches" instead of the styled meta line.
    """
    return "\n".join(line for line in raw.splitlines() if line.strip())


def circular_progress_html(percent, title, color, size=140, stroke=12):
    """
    A circular (ring) progress gauge built from a plain inline SVG, with
    the project title centered inside the ring instead of off to the side.
    Streamlit has no native circular progress widget, and a CSS
    conic-gradient version needs an opaque center disc to mask the ring
    behind it -- which breaks the moment the page background isn't the
    exact color you guessed. An SVG stroke never needs a background guess:
    it draws the ring itself and leaves everything else transparent, so it
    looks right in any theme.
    """
    percent = max(0, min(100, percent))
    radius = (size - stroke) / 2
    circumference = 2 * 3.141592653589793 * radius
    offset = circumference * (1 - percent / 100)
    center = size / 2

    return clean_html(f"""
    <div class="circular-progress" style="width:{size}px; height:{size}px;">
        <svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
            <circle cx="{center}" cy="{center}" r="{radius}"
                    stroke="rgba(255,255,255,0.10)" stroke-width="{stroke}" fill="none" />
            <circle cx="{center}" cy="{center}" r="{radius}"
                    stroke="{color}" stroke-width="{stroke}" fill="none"
                    stroke-linecap="round"
                    stroke-dasharray="{circumference:.2f}"
                    stroke-dashoffset="{offset:.2f}"
                    transform="rotate(-90 {center} {center})" />
        </svg>
        <div class="circular-progress-label">
            <div class="circle-title">{title}</div>
            <div class="circle-percent" style="color:{color};">{percent:.0f}%</div>
        </div>
    </div>
    """)


def teammate_card_html(suggestion):
    """
    One row in the "Find a teammate" panel: partner name, the score
    before/after teaming up, and specifically which skills they'd add --
    the whole point is to make the increase legible, not just a bigger
    number.
    """
    adds = ", ".join(suggestion["skills_partner_adds"]) or "no new skills -- overlapping interests/availability still helped"
    cap_note = (
        '<div class="match-meta">Still capped: a core prerequisite skill remains uncovered even as a team.</div>'
        if suggestion.get("capped_by_missing_core_skill") else ""
    )
    return clean_html(f"""
    <div class="teammate-card">
        <span class="teammate-name">{suggestion['partner_name']}</span>
        <span class="teammate-score">{suggestion['solo_score']}% &#8594; {suggestion['team_score']}% (+{suggestion['score_increase']})</span>
        <div class="match-meta">Skills they'd add: {adds}</div>
        {cap_note}
    </div>
    """)


def build_action_plan_text(student, top, explanation, skill_gap, steps):
    lines = [
        "RESEARCH MATCH ACTION PLAN",
        "=" * 40,
        f"Student: {student.name}",
        f"Target Project: {top['title']} ({top['domain']})",
        f"Faculty: {top['faculty']}",
        f"Match Score: {top['score']}%",
        f"Eligible: {'Yes' if top['eligible'] else 'No'}",
        "",
        f"Matched Skills: {', '.join(top['matched_skills']) or 'None'}",
        f"Missing Skills: {', '.join(top['missing_skills']) or 'None'}",
        f"Missing Interests: {', '.join(top['missing_interests']) or 'None'}",
    ]
    if top.get("capped_by_missing_core_skill"):
        lines.append("Note: score is capped because a core prerequisite skill is missing.")
    if top.get("potential_score") is not None:
        lines.append(f"Potential Score (if fully matched): {top['potential_score']}%")
    lines += [
        "",
        "WHY THIS MATCH",
        explanation,
        "",
        "SKILL GAP ANALYSIS",
        skill_gap,
        "",
        "LEARNING PATHWAY",
    ]
    for i, step in enumerate(steps, start=1):
        lines.append(f"  Step {i}: {step['title']} -- {step['description']}")
    return "\n".join(lines)


st.set_page_config(page_title="Research Opportunity Matcher", layout="wide")

if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    auth_ui.render_login_gate()
    st.stop()

auth_ui.render_sidebar(st.session_state.user)

if st.session_state.user.get("role") == "admin":
    admin_page.render_admin(st.session_state.user)
    st.stop()


def hydrate_student_form(user):
    if st.session_state.get("_profile_hydrated"):
        return
    st.session_state["name"] = user.get("name") or user.get("username") or ""
    st.session_state["year"] = int(user.get("year") or 1)
    st.session_state["department"] = user.get("department") or "CSE"
    skills = list(user.get("skills") or [])
    interests = list(user.get("interests") or [])
    prior = list(user.get("projects") or [])
    research = list(user.get("research_interests") or [])
    academic = user.get("academic_background") or ""
    st.session_state["interests"] = ", ".join(interests)
    st.session_state["add_skills"] = bool(skills)
    st.session_state["skills"] = ", ".join(skills)
    st.session_state["add_projects"] = bool(prior)
    st.session_state["prior_projects"] = ", ".join(prior)
    st.session_state["add_academic"] = bool(academic.strip())
    st.session_state["academic_background"] = academic
    st.session_state["add_research"] = bool(research)
    st.session_state["research_interests"] = ", ".join(research)
    st.session_state["add_availability"] = True
    st.session_state["availability_hours"] = int(user.get("availability_hours") or 8)
    st.session_state["_profile_hydrated"] = True


hydrate_student_form(st.session_state.user)

# ---------- Global styling ----------
st.markdown(
    """
    <style>
    .app-subtitle { color: #9a9a9a; font-size: 15px; margin-top: -8px; margin-bottom: 20px; }
    .match-card {
        border-radius: 12px; padding: 16px 18px; margin-bottom: 8px;
        background: rgba(255,255,255,0.03); border-left: 5px solid #555;
    }
    .match-card.eligible { border-left-color: #4CAF50; }
    .match-card.ineligible { border-left-color: #E05252; }
    .match-card.fasttrack { border-left-color: #4C8BF5; }
    .match-title { font-weight: 700; font-size: 16px; }
    .match-meta { color: #9a9a9a; font-size: 13px; margin-top: 2px; }
    .badge {
        display: inline-block; padding: 2px 10px; border-radius: 999px;
        font-size: 12px; font-weight: 600; margin-left: 8px;
    }
    .badge.eligible { background: rgba(76,175,80,0.18); color: #4CAF50; }
    .badge.ineligible { background: rgba(224,82,82,0.18); color: #E05252; }
    .badge.fasttrack { background: rgba(76,139,245,0.18); color: #4C8BF5; }
    .badge.capped { background: rgba(224,163,48,0.18); color: #E0A030; }
    .section-card {
        border-radius: 12px; padding: 18px 20px; margin-bottom: 16px;
        background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08);
    }
    .improve-panel {
        border-radius: 10px; padding: 14px 16px; margin-bottom: 16px;
        background: rgba(255,255,255,0.03); border: 1px dashed rgba(255,255,255,0.15);
    }
    .step-box {
        border: 2px solid #4CAF50; border-radius: 10px; padding: 12px;
        text-align: center; min-height: 120px; background: rgba(76,175,80,0.06);
    }
    .step-label { font-size: 11px; color: #4CAF50; font-weight: 700; letter-spacing: 0.5px; }
    .step-title { font-weight: 700; margin: 6px 0; }
    .step-desc { font-size: 13px; color: #ccc; }
    .chat-bubble {
        border-radius: 10px; padding: 10px 14px; margin-bottom: 8px; font-size: 14px;
    }
    .chat-user { background: rgba(76,139,245,0.12); }
    .chat-ai { background: rgba(255,255,255,0.04); }
    .required-label { color: #E0A030; font-size: 12px; }
    .circular-progress {
        position: relative; margin: 4px auto 8px auto;
    }
    .circular-progress svg { position: absolute; top: 0; left: 0; }
    .circular-progress-label {
        position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        text-align: center; padding: 0 16px;
    }
    .circle-title { font-size: 12px; font-weight: 600; line-height: 1.25; color: #ddd; }
    .circle-percent { font-size: 20px; font-weight: 800; margin-top: 4px; }
    .teammate-panel {
        border-radius: 10px; padding: 14px 16px; margin-bottom: 16px;
        background: rgba(76,139,245,0.04); border: 1px dashed rgba(76,139,245,0.3);
    }
    .teammate-card {
        border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;
        background: rgba(255,255,255,0.03); border-left: 3px solid #4C8BF5;
    }
    .teammate-name { font-weight: 700; font-size: 14px; }
    .teammate-score { font-size: 13px; color: #4C8BF5; font-weight: 700; margin-left: 10px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("AI-Powered Research Opportunity Discovery")
st.markdown(
    f'<div class="app-subtitle">Welcome back, {st.session_state.user.get("username")}. '
    "Update your profile to find labs, or open a project you already joined.</div>",
    unsafe_allow_html=True,
)

try:
    projects = firebase_store.list_projects()
    faculty_list = firebase_store.list_faculty()
    student_roster = firebase_store.list_students()
    enrollments = firebase_store.list_enrollments_for_student(st.session_state.user["uid"])
except Exception as exc:
    st.error(f"Could not load data from Firestore: {exc}")
    st.stop()

enrolled_ids = {row["project_id"] for row in enrollments}

if enrollments:
    st.subheader("Projects you are part of")
    st.caption("These stay saved on your account, so they show up every time you log in.")
    for row in enrollments:
        leave_col, info_col = st.columns([1, 4])
        with info_col:
            st.markdown(
                clean_html(f"""
                <div class="match-card eligible">
                    <span class="match-title">{row.get('project_title', '')}</span>
                    <span class="badge eligible">Joined</span>
                    <div class="match-meta">{row.get('domain', '')} &middot; {row.get('faculty', '')}</div>
                </div>
                """),
                unsafe_allow_html=True,
            )
        with leave_col:
            if st.button("Leave", key=f"leave_{row.get('project_id')}"):
                firebase_store.leave_project(st.session_state.user["uid"], row["project_id"])
                st.rerun()
else:
    st.info("You have not joined a research project yet. Find a match below and click Join.")

# ---------- Session state setup ----------
# Streamlit reruns the entire script top-to-bottom on every interaction
# (button click, checkbox toggle, text input, etc). Without session_state,
# results and chat history would be wiped every time you touch anything
# else on the page. This block makes them persist.
if "ranked" not in st.session_state:
    st.session_state.ranked = None
    st.session_state.student = None
    st.session_state.top_match = None
    st.session_state.explanation = ""
    st.session_state.skill_gap = ""
    st.session_state.pathway_steps = []
    st.session_state.intro_requested = False
    st.session_state.no_match = False
    st.session_state.encourage_text = ""
    # Underclassmen blocked purely by a project's min_year, but whose
    # skills already look strong enough to be worth preparing early for
    # that lab -- see fast_track_readiness() in matcher.py.
    st.session_state.fast_track_matches = []
    # A specific collaborator entered in the profile form (optional -- see
    # suggest_teammates() in matcher.py). None until the student fills it in.
    st.session_state.manual_collaborator = None

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []  # list of (question, answer) tuples

if "show_improvement" not in st.session_state:
    st.session_state.show_improvement = {}  # project_id -> bool

if "show_teammates" not in st.session_state:
    st.session_state.show_teammates = {}  # project_id -> bool

if "teammate_suggestions" not in st.session_state:
    st.session_state.teammate_suggestions = {}  # project_id -> list of suggestion dicts

# ---------- Student input (plain widgets, not st.form) ----------
# Checkboxes need to reveal their field immediately, before submission.
# st.form batches all its widgets and only reruns on submit, so a
# checkbox inside a form can't dynamically show a new input -- these
# have to be regular top-level widgets instead.
st.subheader("Your Profile")

st.markdown('<span class="required-label">Required</span>', unsafe_allow_html=True)
left, right = st.columns(2)
with left:
    name = st.text_input("Name", key="name")
    year = st.number_input("Year", min_value=1, max_value=4, key="year")
with right:
    department = st.text_input("Department", key="department")
    interests = st.text_input("Interests (comma separated)", placeholder="Computer Vision, Robotics", key="interests")

st.markdown('<span class="required-label">Optional -- check to add</span>', unsafe_allow_html=True)
opt_left, opt_right = st.columns(2)

with opt_left:
    add_skills = st.checkbox("Add skills", key="add_skills")
    skills = st.text_input("Skills (comma separated)", placeholder="Python, Machine Learning, OpenCV", key="skills") if add_skills else st.session_state.get("skills", "")

    add_projects = st.checkbox("Add past projects", key="add_projects")
    prior_projects = st.text_input("Past projects (comma separated)", placeholder="image classifier", key="prior_projects") if add_projects else st.session_state.get("prior_projects", "")

with opt_right:
    add_academic = st.checkbox("Add academic background", key="add_academic")
    academic_background = st.text_input("Academic background", placeholder="CSE core, intro to AI", key="academic_background") if add_academic else st.session_state.get("academic_background", "")

    add_research = st.checkbox("Add research interests", key="add_research")
    research_interests = st.text_input("Research interests (comma separated)", placeholder="Computer Vision", key="research_interests") if add_research else st.session_state.get("research_interests", "")

add_availability = st.checkbox("Specify weekly availability", key="add_availability")
availability_hours = st.number_input("Weekly availability (hours)", min_value=0, max_value=40, key="availability_hours") if add_availability else st.session_state.get("availability_hours", 8)

# Teaming up with a complementary student is opt-in and separate from the
# main profile: it never changes your own solo scores above, it only
# feeds an extra candidate into "Find a teammate for this project" below
# the results. Leave this unchecked and nothing about matching changes.
add_collaborator = st.checkbox("Check a specific collaborator for teammate suggestions (optional)")
if add_collaborator:
    collab_left, collab_right = st.columns(2)
    with collab_left:
        collab_name = st.text_input("Collaborator name", placeholder="e.g. a classmate's name")
        collab_year = st.number_input("Collaborator year", min_value=1, max_value=4, value=1, key="collab_year")
    with collab_right:
        collab_skills = st.text_input("Collaborator skills (comma separated)", placeholder="Python, SQL, Figma", key="collab_skills")
        collab_interests = st.text_input("Collaborator interests (comma separated)", placeholder="HCI", key="collab_interests")
else:
    collab_name = collab_skills = collab_interests = ""
    collab_year = 1

submitted = st.button("Find Matches", use_container_width=True)

# Matching + AI overview only run on submit. Once computed, results are
# saved into session_state, so they stay on screen no matter what you
# click afterward (including using the chatbot or faculty card below).
if submitted:
    missing_required = []
    if not name.strip():
        missing_required.append("Name")
    if not department.strip():
        missing_required.append("Department")
    if not interests.strip():
        missing_required.append("Interests")

    if missing_required:
        st.error("Please fill in: " + ", ".join(missing_required))
    else:
        skills_list = [s.strip() for s in skills.split(",") if s.strip()]
        interests_list = [i.strip() for i in interests.split(",") if i.strip()]

        # Fast rule-based checks first (free, instant), then the AI catches
        # anything more subtle -- gibberish that happens to look word-shaped,
        # placeholder text, contradictory entries, etc.
        rule_issues = basic_input_check(name, skills_list, interests_list, academic_background)
        with st.spinner("Checking input..."):
            ai_check = validate_profile(name, skills_list, interests_list, academic_background)

        all_issues = rule_issues + ai_check.get("issues", [])
        if all_issues:
            st.warning("We noticed a few possible issues with your input:")
            for issue in all_issues:
                st.write(f"- {issue}")
            st.caption("Matching will still run below, but results may be inaccurate until this is fixed.")

        student = Student(
            name=name,
            year=int(year),
            department=department,
            skills=skills_list,
            interests=interests_list,
            academic_background=academic_background,
            projects=[p.strip() for p in prior_projects.split(",") if p.strip()],
            research_interests=[r.strip() for r in research_interests.split(",") if r.strip()],
            availability_hours=int(availability_hours),
        )
        firebase_store.update_student_profile(st.session_state.user["uid"], student)
        refreshed = firebase_store.get_user(st.session_state.user["uid"])
        if refreshed:
            st.session_state.user = refreshed

        # Optional: a specific collaborator to check for teammate
        # suggestions, on top of the built-in student roster. Only built
        # when a name AND at least one skill were actually entered.
        manual_collaborator = None
        if collab_name.strip() and collab_skills.strip():
            manual_collaborator = Student(
                name=collab_name.strip(),
                year=int(collab_year),
                department=department,
                skills=[s.strip() for s in collab_skills.split(",") if s.strip()],
                interests=[i.strip() for i in collab_interests.split(",") if i.strip()],
                academic_background="",
                projects=[],
                research_interests=[],
                availability_hours=5,
            )
        st.session_state.manual_collaborator = manual_collaborator

        ranked = rank_projects(student, projects)
        # Only keep matches with a genuine, nonzero fit -- a 0% "match"
        # isn't useful to show and just adds noise to the results list.
        nonzero_matches = [r for r in ranked if r["score"] > 0][:3]

        # Underclassmen blocked purely by min_year, but who already have
        # most of a project's core (must-have) skills, get surfaced
        # separately as fast-track candidates -- worth preparing for early
        # rather than a dead end. The year gate itself never changes.
        fast_track_matches = [
            r for r in ranked
            if not r["eligible"] and r.get("fast_track") and r["fast_track"]["is_fast_track_candidate"]
        ][:2]

        st.session_state.student = student
        st.session_state.chat_history = []
        st.session_state.intro_requested = False
        st.session_state.show_improvement = {}
        st.session_state.show_teammates = {}
        st.session_state.teammate_suggestions = {}
        st.session_state.fast_track_matches = fast_track_matches

        if nonzero_matches:
            top = nonzero_matches[0]
            st.session_state.ranked = nonzero_matches
            st.session_state.top_match = top
            st.session_state.no_match = False
            st.session_state.encourage_text = ""

            with st.spinner("Generating AI overview..."):
                st.session_state.explanation = explain_match(student, top)
                pathway = skill_gap_and_pathway(student, top)
                st.session_state.skill_gap = pathway.get("skill_gap", "")
                st.session_state.pathway_steps = pathway.get("steps", [])
        else:
            # Nothing scored above 0% -- there's no project to build a
            # flow chart or faculty card around. Give the student
            # something useful anyway: an AI overview aimed at getting
            # them started, instead of a blank results page.
            st.session_state.ranked = []
            st.session_state.top_match = None
            st.session_state.explanation = ""
            st.session_state.skill_gap = ""
            st.session_state.pathway_steps = []
            st.session_state.no_match = True
            with st.spinner("Generating AI overview..."):
                st.session_state.encourage_text = suggest_starting_point(student, projects)

# ---------- Results section (independent block) ----------
# Renders from session_state, not from `submitted` -- so it stays visible
# even after you interact with the chatbot or faculty card below.
if st.session_state.ranked:
    st.divider()
    st.subheader("Top Matches")

    top_three = st.session_state.ranked[:3]
    projects_by_id = {p.id: p for p in projects}
    for r in top_three:
        eligible = r["eligible"]
        css_class = "eligible" if eligible else "ineligible"
        badge_text = "Meets Year Requirement" if eligible else "Below Year Requirement"
        core_badge = (
            '<span class="badge capped">Missing core skill</span>'
            if r.get("capped_by_missing_core_skill") else ""
        )
        # Ring color doubles as a quick visual signal: amber when a core
        # skill is missing (score is capped), green otherwise.
        ring_color = "#E0A030" if r.get("capped_by_missing_core_skill") else "#4CAF50"

        ring_col, info_col = st.columns([1, 3])
        with ring_col:
            st.markdown(
                circular_progress_html(r["score"], r["title"], ring_color),
                unsafe_allow_html=True,
            )
        with info_col:
            st.markdown(
                clean_html(f"""
                <div class="match-card {css_class}">
                    <span class="badge {css_class}">{badge_text}</span>
                    {core_badge}
                    <div class="match-meta">{r['domain']} &middot; {r['faculty']}</div>
                </div>
                """),
                unsafe_allow_html=True,
            )

            pid = r["project_id"]
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                btn_label = "Hide improvement details" if st.session_state.show_improvement.get(pid) else "See how to improve this match"
                if st.button(btn_label, key=f"improve_{pid}"):
                    st.session_state.show_improvement[pid] = not st.session_state.show_improvement.get(pid, False)
            with btn_col2:
                team_btn_label = "Hide teammate suggestions" if st.session_state.show_teammates.get(pid) else "Find a teammate for this project"
                if st.button(team_btn_label, key=f"team_{pid}"):
                    st.session_state.show_teammates[pid] = not st.session_state.show_teammates.get(pid, False)
                    if st.session_state.show_teammates[pid] and pid not in st.session_state.teammate_suggestions:
                        current_name = st.session_state.student.name.strip().lower()
                        candidates = [c for c in student_roster if c.name.strip().lower() != current_name]
                        if st.session_state.manual_collaborator:
                            candidates.append(st.session_state.manual_collaborator)
                        project_obj = projects_by_id.get(pid)
                        st.session_state.teammate_suggestions[pid] = suggest_teammates(
                            st.session_state.student, project_obj, candidates
                        )
            with btn_col3:
                if pid in enrolled_ids:
                    st.success("You already joined this project.")
                elif not eligible:
                    st.caption("Year requirement not met — cannot join yet.")
                else:
                    if st.button("Join this research project", key=f"join_{pid}"):
                        project_obj = projects_by_id.get(pid)
                        if project_obj:
                            join_user = dict(st.session_state.user)
                            if st.session_state.student:
                                join_user["name"] = st.session_state.student.name
                            firebase_store.join_project(join_user, project_obj)
                            st.rerun()

        if st.session_state.show_improvement.get(pid):
            if r["potential_score"] is None:
                st.markdown(
                    '<div class="improve-panel">This project has a year requirement this profile does not '
                    'currently meet. Adding skills or interests will not change eligibility here.</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown('<div class="improve-panel">', unsafe_allow_html=True)
                st.progress(min(int(r["score"]), 100) / 100, text=f"Current: {r['score']}%")
                st.progress(min(int(r["potential_score"]), 100) / 100, text=f"Potential if fully matched: {r['potential_score']}%")
                if r.get("capped_by_missing_core_skill"):
                    st.write(
                        "This score is capped because a core prerequisite skill is missing -- "
                        "closing that gap first raises the ceiling the most."
                    )
                if r.get("missing_must_skills"):
                    st.write("Core skills that would raise this score: " + ", ".join(r["missing_must_skills"]))
                if r.get("missing_nice_skills"):
                    st.write("Nice-to-have skills that would raise this score: " + ", ".join(r["missing_nice_skills"]))
                if r["missing_interests"]:
                    st.write("Interests that would raise this score: " + ", ".join(r["missing_interests"]))
                if not r["missing_skills"] and not r["missing_interests"]:
                    st.write("This profile already covers every listed skill and interest for this project.")
                st.markdown("</div>", unsafe_allow_html=True)

        if st.session_state.show_teammates.get(pid):
            suggestions = st.session_state.teammate_suggestions.get(pid, [])
            st.markdown('<div class="teammate-panel">', unsafe_allow_html=True)
            if suggestions:
                st.write(f"Teaming up on {r['title']} could raise your score:")
                for suggestion in suggestions:
                    st.markdown(teammate_card_html(suggestion), unsafe_allow_html=True)
            else:
                st.write(
                    "No one in the student roster (or the collaborator you entered, if any) raises "
                    "your score for this project beyond what you already get on your own."
                )
                st.caption(
                    "Add a specific collaborator's skills in your profile above and resubmit to check "
                    "someone not in the roster."
                )
            st.markdown("</div>", unsafe_allow_html=True)

    st.divider()
    st.subheader(f"AI Overview: {st.session_state.top_match['title']}")
    st.markdown(f'<div class="section-card">{st.session_state.explanation}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="section-card">{st.session_state.skill_gap}</div>', unsafe_allow_html=True)

    # Flow chart for the 3-step learning pathway, most urgent step first.
    # Built with plain HTML/CSS boxes + arrows so it renders reliably
    # with zero extra dependencies (no Graphviz binary needed).
    steps = st.session_state.pathway_steps
    if steps:
        st.markdown("**Learning Pathway**")
        cols = st.columns(len(steps) * 2 - 1)
        for i, step in enumerate(steps):
            col_index = i * 2
            with cols[col_index]:
                st.markdown(
                    clean_html(f"""
                    <div class="step-box">
                        <div class="step-label">STEP {i + 1}</div>
                        <div class="step-title">{step['title']}</div>
                        <div class="step-desc">{step['description']}</div>
                    </div>
                    """),
                    unsafe_allow_html=True,
                )
            if col_index + 1 < len(cols):
                with cols[col_index + 1]:
                    st.markdown(
                        "<div style='text-align:center; font-size:28px; padding-top:40px; color:#4CAF50;'>&#8594;</div>",
                        unsafe_allow_html=True,
                    )

    # ---------- Faculty Contact Card ----------
    matched_faculty = next(
        (f for f in faculty_list if f.name == st.session_state.top_match["faculty"]),
        None,
    )
    if matched_faculty:
        st.divider()
        st.markdown("**Faculty Contact**")
        st.markdown(
            clean_html(f"""
            <div class="section-card">
                <div class="match-title">{matched_faculty.name}</div>
                <div class="match-meta">{matched_faculty.department} &middot; {matched_faculty.lab}</div>
                <div style="margin-top:8px; font-size:13px;">Research domains: {', '.join(matched_faculty.domains)}</div>
            </div>
            """),
            unsafe_allow_html=True,
        )
        if st.session_state.intro_requested:
            st.success(f"Introduction request sent to {matched_faculty.name} (demo mode -- no email actually sent).")
        else:
            if st.button("Request Introduction"):
                st.session_state.intro_requested = True
                st.rerun()

    # ---------- Downloadable Action Plan ----------
    st.divider()
    plan_text = build_action_plan_text(
        st.session_state.student,
        st.session_state.top_match,
        st.session_state.explanation,
        st.session_state.skill_gap,
        st.session_state.pathway_steps,
    )
    st.download_button(
        label="Download Action Plan (.txt)",
        data=plan_text,
        file_name=f"{st.session_state.student.name.replace(' ', '_')}_action_plan.txt",
        mime="text/plain",
        use_container_width=True,
    )

elif st.session_state.no_match:
    st.divider()
    st.subheader("Top Matches")
    st.write("There are no current matches for this profile.")
    st.markdown(f'<div class="section-card">{st.session_state.encourage_text}</div>', unsafe_allow_html=True)

# ---------- Fast-Track Consideration (independent block) ----------
# Only ever populated for students blocked purely by a project's min_year
# whose core-skill readiness already clears FAST_TRACK_MUST_HAVE_THRESHOLD
# in matcher.py. Renders alongside either results state above, or on its
# own if there were no eligible matches at all.
if st.session_state.fast_track_matches:
    st.divider()
    st.subheader("Fast-Track Consideration")
    st.caption(
        "These labs require a higher year than you're currently in, but your profile "
        "already shows strong readiness -- here's what to focus on to be ready early."
    )
    for r in st.session_state.fast_track_matches:
        ft = r["fast_track"]
        st.markdown(
            clean_html(f"""
            <div class="match-card fasttrack">
                <span class="match-title">{r['title']}</span>
                <span class="badge fasttrack">{ft['years_short']} year(s) early &middot; requires Year {r['min_year']}</span>
                <div class="match-meta">{r['domain']} &middot; {r['faculty']}</div>
            </div>
            """),
            unsafe_allow_html=True,
        )
        st.progress(min(int(ft["must_score"]), 100) / 100, text=f"Core skill readiness: {ft['must_score']}%")
        if ft["missing_must_skills"]:
            st.write("Core skills to build before applying: " + ", ".join(ft["missing_must_skills"]))
        else:
            st.write("You already have every core skill this lab requires.")
        if ft["missing_nice_skills"]:
            st.write("Helpful extras to explore early: " + ", ".join(ft["missing_nice_skills"]))

# ---------- AI Assistant chat (independent block) ----------
# Only needs a student + top match to exist -- never re-triggers matching
# or the overview generation above.
if st.session_state.student:
    st.divider()
    st.subheader("Ask the AI Research Assistant")

    for q, a in st.session_state.chat_history:
        with st.chat_message("user"):
            st.write(q)
        with st.chat_message("assistant"):
            st.write(a)

    with st.form("chat_form", clear_on_submit=True):
        question = st.text_input("Your question")
        ask_clicked = st.form_submit_button("Ask")

    if ask_clicked and question:
        with st.spinner("Thinking..."):
            answer = ask_assistant(
                st.session_state.student,
                st.session_state.top_match,
                question,
            )
        st.session_state.chat_history.append((question, answer))
        st.rerun()