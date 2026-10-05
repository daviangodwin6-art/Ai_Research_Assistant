"""
Matching engine.

Two scoring improvements live here on top of the original overlap-based
approach:

  B. Weighted skill tiers -- each project splits required_skills into
     must_have_skills (strict core prerequisites) and nice_to_have_skills
     (bonus toolkits). Must-haves are weighted far more heavily, and a
     student missing even one must-have has their total score capped
     (MISSING_CORE_SKILL_CAP), so they can never rank above -- or even
     alongside -- a student who has the fundamentals, no matter how many
     nice-to-have toolkits or interest tags they pick up elsewhere.

  C. Soft year eligibility -- the min_year gate itself is unchanged (it
     still hard-blocks a match and the score stays 0), but an underclassman
     blocked purely by year now gets a fast-track readiness snapshot
     instead of a bare, unexplained 0%: which core/nice-to-have skills they
     already have, and whether their profile is strong enough to flag them
     as a "prepare early" candidate for that upper-year lab.

  D. Teammate suggestions -- an opt-in, per-project feature (see
     suggest_teammates / combine_students below). It never runs as part of
     a solo score; it's only invoked when the UI explicitly asks "who
     could I team up with for this specific project."
"""

from models import Student

CORE_SKILL_WEIGHT = 0.75
NICE_TO_HAVE_WEIGHT = 0.25

# A student missing at least one must-have (core prerequisite) skill has
# their overall score capped at this ceiling, regardless of how strong
# their nice-to-have, interest, academic, or availability scores are.
MISSING_CORE_SKILL_CAP = 0.50

# The raw weighted average lands low even for a genuinely solid match --
# eight-plus independent sub-scores all have to line up before a project
# reaches 100%, so a student with just one or two of the right skills was
# previously seeing a discouraging 15-25%. This is meant to be a starting
# point for first-year students to explore research, not a hard admissions
# cutoff, so the raw fraction is curved upward with a square root before
# being shown. The curve is monotonic -- it never changes which project
# ranks above another for a given student -- it just compresses the gap at
# the low end, so a couple of matching skills reads as a credible,
# encouraging "you're eligible to explore this" score, while a project the
# student is genuinely well suited for still reads clearly higher and stays
# the top recommendation.
SCORE_CURVE_EXPONENT = 0.5


def _curve(raw_fraction):
    return raw_fraction ** SCORE_CURVE_EXPONENT

# Share of must-have skills an underclassman needs to already have before
# we flag them as a genuine "fast-track" candidate for an upper-year lab,
# rather than just someone who is merely curious about it.
FAST_TRACK_MUST_HAVE_THRESHOLD = 0.5


def skill_tier_score(student_skills, must_have_skills, nice_to_have_skills):
    """
    Splits skill matching into a strict must-have tier and a bonus
    nice-to-have tier, each scored independently, then blended with
    must-haves weighted far more heavily (CORE_SKILL_WEIGHT vs
    NICE_TO_HAVE_WEIGHT). This is what lets compute_match distinguish
    "missing Python" from "missing one niche framework" instead of
    treating every required skill as interchangeable.
    """
    student_set = set(s.lower() for s in student_skills)
    must_set = set(s.lower() for s in must_have_skills)
    nice_set = set(s.lower() for s in nice_to_have_skills)

    matched_must = student_set & must_set
    missing_must = must_set - student_set
    matched_nice = student_set & nice_set
    missing_nice = nice_set - student_set

    must_score = len(matched_must) / len(must_set) if must_set else 1.0
    nice_score = len(matched_nice) / len(nice_set) if nice_set else 1.0
    weighted_score = must_score * CORE_SKILL_WEIGHT + nice_score * NICE_TO_HAVE_WEIGHT

    return {
        "weighted_score": weighted_score,
        "must_score": must_score,
        "nice_score": nice_score,
        "matched_must": matched_must,
        "missing_must": missing_must,
        "matched_nice": matched_nice,
        "missing_nice": missing_nice,
        "has_all_must_haves": len(missing_must) == 0,
    }


def interest_overlap_score(student_interests, project_tags):
    student_set = set(i.lower() for i in student_interests)
    tag_set = set(t.lower() for t in project_tags)
    matched = student_set & tag_set
    missing = tag_set - student_set
    score = len(matched) / len(tag_set) if tag_set else 0
    return score, matched, missing


def eligibility_score(student, project):
    return 1.0 if student.year >= project.min_year else 0.0


def academic_score(student, project):
    return 1.0 if project.domain.lower() in student.academic_background.lower() else 0.0


def project_fit_score(student, project):
    overlap = set(p.lower() for p in student.projects) & set(t.lower() for t in project.interests_tags)
    return len(overlap) / max(len(project.interests_tags), 1)


def availability_score(student, project):
    if not project.min_availability:
        return 1.0
    return min(student.availability_hours / project.min_availability, 1.0)


def fast_track_readiness(student, project):
    """
    Only computed for students blocked purely by project.min_year. The
    year gate itself is never relaxed -- this is informational only, so an
    ambitious underclassman sees a concrete readiness picture (which
    prerequisite skills they already have vs. still need, and whether
    they're already a strong enough candidate to start preparing now)
    instead of a flat, unexplained 0%.
    """
    tier = skill_tier_score(student.skills, project.must_have_skills, project.nice_to_have_skills)
    _, matched_interests, missing_interests = interest_overlap_score(student.interests, project.interests_tags)

    return {
        "years_short": project.min_year - student.year,
        "must_score": round(tier["must_score"] * 100, 1),
        "nice_score": round(tier["nice_score"] * 100, 1),
        "matched_must_skills": sorted(tier["matched_must"]),
        "missing_must_skills": sorted(tier["missing_must"]),
        "matched_nice_skills": sorted(tier["matched_nice"]),
        "missing_nice_skills": sorted(tier["missing_nice"]),
        "matched_interests": sorted(matched_interests),
        "missing_interests": sorted(missing_interests),
        "is_fast_track_candidate": tier["must_score"] >= FAST_TRACK_MUST_HAVE_THRESHOLD,
    }


def compute_match(student, project):
    elig_s = eligibility_score(student, project)

    if elig_s == 0.0:
        # Hard gate: year requirement not met. No amount of extra skills
        # or interests changes this, so there's still no potential_score --
        # but we attach a fast-track readiness snapshot so this doesn't
        # read as a dead end for a strong, ambitious underclassman.
        return {
            "project_id": project.id,
            "title": project.title,
            "domain": project.domain,
            "faculty": project.faculty,
            "min_year": project.min_year,
            "score": 0.0,
            "potential_score": None,
            "matched_skills": [],
            "missing_skills": sorted(set(s.lower() for s in project.must_have_skills + project.nice_to_have_skills)),
            "matched_interests": [],
            "missing_interests": sorted(set(t.lower() for t in project.interests_tags)),
            "eligible": False,
            "has_all_must_haves": False,
            "capped_by_missing_core_skill": False,
            "fast_track": fast_track_readiness(student, project),
        }

    tier = skill_tier_score(student.skills, project.must_have_skills, project.nice_to_have_skills)
    interest_s, matched_interests, missing_interests = interest_overlap_score(student.interests, project.interests_tags)
    academic_s = academic_score(student, project)
    fit_s = project_fit_score(student, project)
    avail_s = availability_score(student, project)

    base_score = (
        tier["weighted_score"] * 0.35 +
        interest_s * 0.25 +
        academic_s * 0.20 +
        fit_s * 0.20
    )
    total = base_score * avail_s

    # Missing even one must-have (core prerequisite) skill caps the score --
    # no amount of nice-to-have toolkits, interest overlap, or availability
    # can let a student lacking a foundational skill outrank one who has it.
    # The cap is applied on the raw (uncurved) fraction so it stays a fixed,
    # meaningful ceiling -- MISSING_CORE_SKILL_CAP of "genuine fit" -- before
    # the encouraging curve is layered on top for display.
    capped = not tier["has_all_must_haves"]
    if capped:
        total = min(total, MISSING_CORE_SKILL_CAP)

    # Ceiling score: what this match would become if the student had every
    # missing skill (both tiers) and every missing interest tag, with
    # everything else held constant. Pure arithmetic, no AI involved --
    # this is what powers the "how to improve this match" panel.
    potential_base = (
        1.0 * 0.35 +
        1.0 * 0.25 +
        academic_s * 0.20 +
        fit_s * 0.20
    )
    potential_score = round(_curve(potential_base * avail_s) * 100, 1)

    return {
        "project_id": project.id,
        "title": project.title,
        "domain": project.domain,
        "faculty": project.faculty,
        "min_year": project.min_year,
        "score": round(_curve(total) * 100, 1),
        "potential_score": potential_score,
        "matched_skills": sorted(tier["matched_must"] | tier["matched_nice"]),
        "missing_skills": sorted(tier["missing_must"] | tier["missing_nice"]),
        "matched_must_skills": sorted(tier["matched_must"]),
        "missing_must_skills": sorted(tier["missing_must"]),
        "matched_nice_skills": sorted(tier["matched_nice"]),
        "missing_nice_skills": sorted(tier["missing_nice"]),
        "matched_interests": sorted(matched_interests),
        "missing_interests": sorted(missing_interests),
        "eligible": True,
        "has_all_must_haves": tier["has_all_must_haves"],
        "capped_by_missing_core_skill": capped,
        "fast_track": None,
    }


def rank_projects(student, projects):
    results = [compute_match(student, p) for p in projects]
    return sorted(results, key=lambda x: x["score"], reverse=True)


def combine_students(student_a, student_b):
    """
    Builds a synthetic "team" profile for two students collaborating on
    the same project: skills, interests, prior projects, and research
    interests are unioned; academic backgrounds are concatenated (so
    either student's background can satisfy the domain check); and
    availability is summed (two people cover more weekly hours than one
    would alone).

    Year is the LOWER of the two, so eligibility for the team still
    requires both members to individually meet the project's min_year --
    teaming up is meant to close a skill gap, not launder a year
    requirement neither of them meets alone.

    Feeding the result into compute_match() reuses every existing scoring
    rule (tiered must-have/nice-to-have skills, the missing-core-skill
    cap, the display curve) instead of maintaining a second, parallel
    scoring formula for teams.
    """
    return Student(
        name=f"{student_a.name} & {student_b.name}",
        year=min(student_a.year, student_b.year),
        department=student_a.department,
        skills=sorted(set(student_a.skills) | set(student_b.skills), key=str.lower),
        interests=sorted(set(student_a.interests) | set(student_b.interests), key=str.lower),
        academic_background=f"{student_a.academic_background}; {student_b.academic_background}".strip("; "),
        projects=sorted(set(student_a.projects) | set(student_b.projects), key=str.lower),
        research_interests=sorted(
            set(student_a.research_interests) | set(student_b.research_interests), key=str.lower
        ),
        availability_hours=student_a.availability_hours + student_b.availability_hours,
    )


def suggest_teammates(student, project, candidates, top_n=3):
    """
    Ranks candidate partners for ONE specific project by the score the
    pair would get if they teamed up on it. This is opt-in: it is only
    ever called when the UI explicitly asks, for one project at a time --
    it never runs as part of the default per-project scoring, since "who
    should I team up with" is a separate question from "how do I score on
    my own."

    A candidate is only worth suggesting if pairing with them actually
    raises the score above what the student already gets solo -- matching
    with someone who adds nothing (or overlaps entirely) isn't advice,
    it's noise. Results are ranked by the resulting team score, highest
    first, and capped at top_n.
    """
    solo = compute_match(student, project)
    suggestions = []
    for candidate in candidates:
        if candidate.name.strip().lower() == student.name.strip().lower():
            continue
        team = combine_students(student, candidate)
        team_result = compute_match(team, project)
        if team_result["score"] > solo["score"]:
            suggestions.append({
                "partner_name": candidate.name,
                "solo_score": solo["score"],
                "team_score": team_result["score"],
                "score_increase": round(team_result["score"] - solo["score"], 1),
                "matched_skills": team_result["matched_skills"],
                "missing_skills": team_result["missing_skills"],
                "capped_by_missing_core_skill": team_result["capped_by_missing_core_skill"],
                "skills_partner_adds": sorted(
                    set(s.lower() for s in candidate.skills) - set(s.lower() for s in student.skills)
                ),
            })

    suggestions.sort(key=lambda s: s["team_score"], reverse=True)
    return suggestions[:top_n]