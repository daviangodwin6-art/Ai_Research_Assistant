from dataclasses import dataclass
from typing import List


@dataclass
class Student:
    name: str
    year: int
    department: str
    skills: List[str]
    interests: List[str]
    academic_background: str
    projects: List[str]
    research_interests: List[str]
    availability_hours: int


@dataclass
class Project:
    id: str
    title: str
    domain: str
    faculty: str
    # Skills are split into two tiers (see matcher.py):
    #   must_have_skills   -- strict, core prerequisites (e.g. the language
    #                         or foundational discipline the lab is built on)
    #   nice_to_have_skills -- bonus toolkits/frameworks that boost a match
    #                         but whose absence shouldn't sink it
    must_have_skills: List[str]
    nice_to_have_skills: List[str]
    interests_tags: List[str]
    min_year: int
    min_availability: int


@dataclass
class Faculty:
    name: str
    department: str
    domains: List[str]
    lab: str