"""Realistic-looking values for an attribute, guessed from its name and its relation.

Used only for the example data students see when a question has none of its own
(example_data.py); the grader's test databases keep their placeholders. A guess that
misses is harmless: the values still have the right type, and staff can Regenerate or
copy the data into the INSERT box and edit it.

Each list has 8 values, so a key never runs out for a relation of up to 5 tuples, while
other attributes still repeat now and then (two students in the same major).
"""
import re
from typing import List

PEOPLE = ["Alice", "Bob", "Chen", "Divya", "Ethan", "Farah", "Gopal", "Hana"]
SURNAMES = ["Tan", "Lim", "Kumar", "Wong", "Smith", "Lee", "Garcia", "Ng"]
DEPARTMENTS = ["Computer Science", "Mathematics", "Physics", "Chemistry", "Civil Engineering", "Economics",
               "Biology", "Accounting"]
COURSES = ["Databases", "Algorithms", "Operating Systems", "Networks", "Calculus", "Statistics",
           "Data Mining", "Machine Learning"]
SCHOOLS = ["SCSE", "EEE", "MAE", "NBS", "SPMS", "CEE", "SBS", "ADM"]
CITIES = ["Singapore", "London", "Tokyo", "Sydney", "Boston", "Paris", "Seoul", "Toronto"]
COUNTRIES = ["Singapore", "Japan", "India", "France", "Canada", "Australia", "Brazil", "Kenya"]
COMPANIES = ["Acme", "Globex", "Initech", "Umbrella", "Stark", "Wayne", "Hooli", "Wonka"]
TEAMS = ["Tigers", "Lions", "Eagles", "Sharks", "Wolves", "Bears", "Falcons", "Hawks"]
PIZZERIAS = ["Pizza Hut", "Dominos", "Little Caesars", "Straw Hat", "New York Pizza", "Chicago Pizza",
             "Pizza Express", "Papa Johns"]
PIZZAS = ["cheese", "pepperoni", "mushroom", "supreme", "sausage", "hawaiian", "veggie", "margherita"]
TITLES = ["Database Systems", "The Data Book", "Learning SQL", "Query Design", "Clean Code", "Deep Work",
          "The Pragmatic Programmer", "Refactoring"]
PROJECTS = ["Apollo", "Borealis", "Comet", "Delta", "Everest", "Falcon", "Gemini", "Horizon"]
JOBS = ["Engineer", "Manager", "Analyst", "Intern", "Director", "Designer", "Tester", "Consultant"]
COLOURS = ["red", "green", "blue", "black", "white", "yellow", "purple", "orange"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun", "Mon"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]
STATUSES = ["active", "inactive", "pending", "closed", "active", "pending", "closed", "inactive"]
TYPES = ["Standard", "Premium", "Basic", "Deluxe", "Standard", "Premium", "Basic", "Deluxe"]
LETTER_GRADES = ["A", "B", "C", "D", "F", "A", "B", "C"]
GENDERS = ["F", "M"]
SEMESTERS = ["S1", "S2"]

# What a "…name" attribute names, by the letter(s) before "name" (Sname, Dname, Cname, …).
_NAME_PREFIX = {
    "": None, "s": PEOPLE, "p": PEOPLE, "e": PEOPLE, "f": PEOPLE, "first": PEOPLE, "emp": PEOPLE,
    "student": PEOPLE, "prof": PEOPLE, "staff": PEOPLE, "person": PEOPLE, "user": PEOPLE, "author": PEOPLE,
    "player": PEOPLE, "driver": PEOPLE, "pilot": PEOPLE, "m": PEOPLE, "manager": PEOPLE, "customer": PEOPLE,
    "cust": PEOPLE, "l": SURNAMES, "last": SURNAMES, "sur": SURNAMES,
    "d": DEPARTMENTS, "dept": DEPARTMENTS, "department": DEPARTMENTS,
    "c": None, "course": COURSES, "t": TEAMS, "team": TEAMS, "city": CITIES, "company": COMPANIES,
    "proj": PROJECTS, "project": PROJECTS, "b": TITLES, "book": TITLES,
}

# What a relation is about, from its name: decides what its plain "name" attribute holds.
_RELATION_WORDS = [
    (("dept", "department", "faculty"), DEPARTMENTS), (("course", "module", "subject"), COURSES),
    (("team", "club"), TEAMS), (("city", "town"), CITIES), (("country", "nation"), COUNTRIES),
    (("company", "firm", "supplier", "vendor"), COMPANIES), (("pizzeria", "restaurant", "shop"), PIZZERIAS),
    (("pizza",), PIZZAS), (("project",), PROJECTS), (("book", "movie", "film", "song"), TITLES),
]

# Text attributes by a word they contain: the first rule that matches wins.
_TEXT_WORDS = [
    (("major", "dept", "department", "faculty", "discipline"), DEPARTMENTS),
    (("school",), SCHOOLS), (("course", "module", "subject"), COURSES),
    (("city", "town", "location", "address", "hometown"), CITIES), (("country", "nation", "nationality"), COUNTRIES),
    (("gender", "sex"), GENDERS), (("colour", "color"), COLOURS), (("day", "weekday"), DAYS),
    (("month",), MONTHS), (("status", "state"), STATUSES), (("type", "category", "kind", "class", "tier"), TYPES),
    (("pizzeria", "restaurant"), PIZZERIAS), (("pizza", "topping", "flavour", "flavor"), PIZZAS),
    (("company", "employer", "firm", "supplier", "vendor", "brand"), COMPANIES), (("team", "club"), TEAMS),
    (("title", "book", "movie", "film"), TITLES), (("project",), PROJECTS),
    (("job", "role", "position", "occupation", "rank"), JOBS), (("grade", "letter"), LETTER_GRADES),
    (("semester", "term", "sem"), SEMESTERS),
]

# Numbers by a word they contain.
_NUMBER_WORDS = [
    (("age",), [18, 19, 20, 21, 22, 23, 24, 25]),
    (("year", "yr"), [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]),
    (("gpa", "cgpa"), [2.5, 3.0, 3.2, 3.5, 3.8, 4.0, 4.3, 4.5]),
    (("score", "mark", "marks", "points", "grade", "result", "exam", "quiz"), [45, 52, 60, 68, 74, 81, 88, 95]),
    (("salary", "wage", "income", "pay"), [3200, 4100, 4800, 5500, 6300, 7200, 8000, 9500]),
    (("price", "cost", "fee", "amount", "balance"), [5, 8, 10, 12, 15, 18, 20, 25]),
    (("credit", "credits", "au", "units"), [1, 2, 3, 4, 2, 3, 4, 3]),
    (("rating", "stars"), [1, 2, 3, 4, 5, 3, 4, 5]),
    (("height",), [150, 158, 163, 168, 172, 177, 181, 189]),
    (("weight",), [48, 55, 60, 64, 70, 75, 82, 90]),
    (("hours", "hour", "duration", "minutes"), [1, 2, 3, 4, 5, 6, 8, 10]),
    (("qty", "quantity", "count", "number", "num", "total", "phds", "goals", "wins"),
     [3, 7, 12, 18, 25, 33, 40, 48]),
]

_ID_WORDS = {"id", "no", "nr", "num", "number", "code", "key", "ref"}


def words(name: str) -> List[str]:
    """teamid-one → [teamid, one]; firstName → [first, name]; Sname → [sname]."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [w.lower() for w in re.split(r"[\s_\-\d]+", spaced) if w]


def _is_id(name: str, ws: List[str]) -> bool:
    low = name.lower()
    return any(w in _ID_WORDS for w in ws) or bool(re.fullmatch(r"[a-z]{1,4}(id|no|num|nr)", low))


def _has(ws: List[str], keys) -> bool:
    """A word is one of ``keys``, or starts or ends with one of 4+ letters (Numphds, Majors)."""
    return any(w in keys or any(len(k) > 3 and (w.startswith(k) or w.endswith(k)) for k in keys) for w in ws)


def realistic_values(attribute: str, relation: str, affinity: str) -> List[object]:
    """Candidate values for one attribute of ``relation`` (SQLite affinity ``affinity``)."""
    ws = words(attribute) or [attribute.lower()]
    rel_ws = words(relation)
    if affinity in ("INTEGER", "REAL", "NUMERIC"):
        values: List[object] = list(range(1, 9))                      # ids and anything unknown: 1..8
        if _has(ws, ("year", "yr")) and _has(rel_ws, ("student", "pupil", "learner")):
            values = [1, 2, 3, 4]                                      # a student's year of study
        elif not _is_id(attribute, ws):
            for keys, vals in _NUMBER_WORDS:
                if _has(ws, keys):
                    values = list(vals)
                    break
        if affinity == "REAL":
            return [float(v) for v in values]
        if affinity == "INTEGER":
            return [int(v) if float(v).is_integer() else v for v in values]
        return values

    low = attribute.lower()
    if low.endswith("name"):
        listed = _NAME_PREFIX.get(low[:-4], "missing")
        if isinstance(listed, list):
            return list(listed)
        for keys, vals in _RELATION_WORDS:                           # Cname in COURSE, plain "name" in TEAM
            if _has(rel_ws, keys):
                return list(vals)
        return list(COURSES if low[:-4] == "c" else PEOPLE)
    for keys, vals in _TEXT_WORDS:
        if _has(ws, keys):
            return list(vals)
    if _is_id(attribute, ws):                                        # Cno → C101, C102, …
        letter = attribute[0].upper() if attribute[0].isalpha() else "X"
        return [f"{letter}{100 + i}" for i in range(1, 9)]
    return [f"{attribute} {chr(ord('A') + i)}" for i in range(8)]  # Brand A, Brand B, …
