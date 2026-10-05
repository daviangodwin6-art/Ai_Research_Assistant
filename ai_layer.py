import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODEL = "openai/gpt-oss-120b"

# Every free-text response gets rendered inside a custom HTML container in
# app.py, not plain st.write. Markdown syntax (#, **, tables) mixed into a
# hand-written <div> renders unpredictably -- sometimes as literal ### and **
# characters, sometimes as a real heading that breaks out of the container.
# Instructing the model to never use Markdown avoids the problem at the
# source instead of trying to sanitize its output after the fact.
PLAIN_TEXT_RULE = (
    "Respond in plain sentences only. Do not use Markdown formatting of any "
    "kind -- no #, ##, or ### headers, no ** bold, no bullet points with * or -, "
    "and no tables."
)


def explain_match(student, match_result):
    prompt = f"""
Student name: {student.name}
Student skills: {student.skills}
Matched skills: {match_result['matched_skills']}
Missing skills: {match_result['missing_skills']}
Match score: {match_result['score']}%
Project: {match_result['title']} ({match_result['domain']})

Write a short, friendly explanation (3-4 sentences) of why this is a good match,
what skills are missing, and one concrete next step to close the gap.
{PLAIN_TEXT_RULE}
"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def skill_gap_and_pathway(student, match_result):
    """
    Returns structured data (a short analysis string + exactly 3 ordered
    steps) instead of one text blob -- so the steps can be rendered as an
    actual flow chart in the UI, not just printed.
    """
    prompt = f"""
Student skills: {student.skills}
Missing skills for "{match_result['title']}": {match_result['missing_skills']}

Respond with ONLY valid JSON, nothing else, in exactly this format:
{{
  "skill_gap": "a short 2-3 sentence skill-gap analysis",
  "steps": [
    {{"title": "short step title", "description": "1 sentence on what to do"}},
    {{"title": "short step title", "description": "1 sentence on what to do"}},
    {{"title": "short step title", "description": "1 sentence on what to do"}}
  ]
}}

The steps must be ordered most urgent first. Keep it concise and practical
for a first-year CS student. The "skill_gap" and "description" text values
must be plain sentences -- no Markdown formatting of any kind (no #, **, bullet
points, or tables).
"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fail open with a usable fallback shape rather than crashing --
        # the UI can still render something even if the model's JSON broke.
        return {"skill_gap": raw, "steps": []}


def validate_profile(name, skills, interests, academic_background):
    """
    Catches things rule-based checks can't: gibberish that happens to be
    the right length, made-up terms, nonsense that looks superficially
    like a real word, mismatched/contradictory info, etc.
    Rule-based checks (validator.py) should always run first -- this is
    the more expensive, more judgment-based second pass.
    """
    prompt = f"""
You are checking a student's research-matching profile for invalid or nonsensical input.

Name: {name}
Skills: {skills}
Interests: {interests}
Academic background: {academic_background}

Flag anything that looks like:
- gibberish or random keyboard-mash text
- a skill/interest that is not a real technical or academic term
- placeholder text (e.g. "test", "none", "asdf", "idk")
- clearly contradictory or nonsensical combinations

Respond with ONLY valid JSON, nothing else, in exactly this format:
{{"valid": true, "issues": []}}
or
{{"valid": false, "issues": ["short issue description", "short issue description"]}}
"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content.strip()

    # Strip markdown code fences if the model wraps its JSON in them
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Never let a malformed AI response block the whole app --
        # fail open rather than crashing the demo.
        return {"valid": True, "issues": []}


def suggest_starting_point(student, projects):
    """
    Used only when every project scored 0% -- instead of leaving the
    student with an empty results page, this turns their stated
    skills/interests/background into an encouraging next step: what
    basics to start with, and which of the available research domains
    could become realistic targets once they do.
    """
    domains = sorted(set(p.domain for p in projects))
    prompt = f"""
A first-year student has the following profile:
Skills: {student.skills}
Interests: {student.interests}
Academic background: {student.academic_background}

None of the available research projects currently match their profile well.
The available research domains are: {domains}

Write a short, encouraging overview (4-5 sentences) that:
1. Acknowledges where they are starting from
2. Suggests 2-3 concrete foundational skills or topics to begin learning
3. Points to 1-2 of the listed domains that could become realistic targets
   once they build those basics
{PLAIN_TEXT_RULE}
"""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=350,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def ask_assistant(student, match_result, question, history=None):
    if match_result is not None:
        context = f"""
You are a research-opportunity assistant for a university platform.
Student: {student.name}, skills: {student.skills}
Current top match: {match_result['title']} ({match_result['score']}% match)
Matched skills: {match_result['matched_skills']}
Missing skills: {match_result['missing_skills']}

Answer the student's question directly and practically, using this context.
{PLAIN_TEXT_RULE}
"""
    else:
        context = f"""
You are a research-opportunity assistant for a university platform.
Student: {student.name}, skills: {student.skills}, interests: {student.interests}
This student does not currently have a matching research project -- their
profile doesn't yet overlap with any available project's requirements.

Answer the student's question directly and practically, focusing on how
they can build toward eligibility for a future project.
{PLAIN_TEXT_RULE}
"""
    messages = (history or []) + [{"role": "user", "content": f"{context}\n\nQuestion: {question}"}]
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=300,
        messages=messages,
    )
    return response.choices[0].message.content