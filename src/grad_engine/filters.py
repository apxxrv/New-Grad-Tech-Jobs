"""All the text classification: is it a new grad role? is it tech? which class?

These are deliberately simple, central, and easy to tune. As we see real data
we widen/narrow these patterns here, in one place.

This engine descends from an internship tracker. The one conceptual inversion
worth knowing: there, a graduation year in a title ("Class of 2027") named the
STUDENT and was scrubbed before season detection. Here the graduation year IS
the thing we track — a new grad role's "class year" — so those phrases are the
strongest evidence we have, in titles and in posting text alike.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

# --- new grad detection (whole words, never substrings) -----------------------
# Internship/co-op titles are the largest false-positive class for an
# early-career search ("Software Engineer Intern" matches "graduate" boards).
_INTERN_RE = re.compile(
    r"\b(intern|interns|internship|internships|co[\s-]?op|co[\s-]?ops|"
    r"cooperative\s+education|apprentice|apprenticeship|fellowship|bootcamp|"
    r"scholar|scholarship|mba|externship)\b",
    re.IGNORECASE,
)
_SENIOR_RE = re.compile(
    r"\b(senior|sr\.?|staff|principal|manager|director|lead|vp|head|"
    r"distinguished|fellow|architect|experienced|mid[\s-]?level|"
    r"mid[\s-]?career|chief|executive)\b",
    re.IGNORECASE,
)
_ROLE_WORD = (
    r"(?:engineer|engineering|developer|dev|scientist|analyst|programmer|"
    r"researcher|specialist|consultant|technologist|sde|swe)"
)
_DOMAIN_WORD = (
    r"(?:software|systems?|data|platform|backend|back[\s-]?end|frontend|"
    r"front[\s-]?end|full[\s-]?stack|web|mobile|ios|android|cloud|security|"
    r"ml|machine\s+learning|ai|devops|sre|infrastructure|test|qa|quality|"
    r"research|solutions?|applications?|embedded|firmware|network|analytics|"
    r"product|technical|technology|it|computer|quantitative|quant)"
)
# "Software Engineer II", "Data Scientist 2", "Engineer - III", "SWE L4".
# A level above I is a mid-level role even when the posting says "early career".
# A number that counts days/months is a schedule, not a level: "Junior Software
# Engineer- 4 Days Onsite" and "Specialist (12 month duration)" were rejected
# as level 4 and level 12.
_LEVEL_RE = re.compile(
    r"\b" + _ROLE_WORD + r"\s*(?:[-–—,(:/]\s*)?(?:ii|iii|iv|v|vi|[2-9]|1\d|"
    r"l[2-9]|level\s+(?:ii|iii|iv|v|[2-9]))\b(?![\d.])"
    r"(?![\s-]*(?:days?|weeks?|months?|hours?|hrs?|years?|yrs?)\b)"
    r"|\b(?:ii|iii|iv)\b|\bl[3-9]\b|\blevel\s+(?:[2-9]|ii|iii|iv|v)\b"
    r"|\b(?:1|i)\s*/\s*(?:2|ii)\b",
    re.IGNORECASE,
)
# The title's own words for "we hire people straight out of school".
_NEW_GRAD_RE = re.compile(
    r"\b(?:"
    r"new[\s-]?grad(?:uate)?s?|newgrad|"
    r"recent[\s-]?grad(?:uate)?s?|"
    r"(?:university|college|campus)[\s-]?grad(?:uate)?s?|"
    r"grad(?:uate)?\s+(?:program(?:me)?|scheme|hire|hiring|rotation(?:al)?|"
    + _ROLE_WORD + r"|" + _DOMAIN_WORD + r"|associate|trainee|role|"
    r"opportunit(?:y|ies)|position)|"
    + _ROLE_WORD + r"\s*(?:[-–—,(:/]\s*)?grad(?:uate)?s?\b|"
    r"early[\s-]?(?:in[\s-]?)?career|early[\s-]?careers|early[\s-]?talent|"
    r"emerging[\s-]?talent|"
    r"entry[\s-]?level|"
    r"campus\s+(?:hire|hiring|recruit(?:ing|ment)?|program(?:me)?)|"
    r"class\s+of\s+['’]?\d{2,4}|"
    r"rotation(?:al)?\s+(?:program(?:me)?|" + _ROLE_WORD + r"|analyst|associate)|"
    # Banks and big employers name campus hires as programs: JPMorgan's
    # "Software Engineer Program", BNY's "Analyst Program", M&T's
    # "Technology Development Program". "Program Manager" still fails on
    # "manager", and "Software Program Management" matches none of these.
    # (A class year + "Program" is checked separately, see _YEAR_PROGRAM_RE.)
    r"(?:" + _ROLE_WORD + r"|associate|development|leadership)\s+program(?:me)?\b|"
    r"(?:associate|junior|jr\.?)\s+(?:" + _DOMAIN_WORD + r"\s+)?" + _ROLE_WORD + r"|"
    + _ROLE_WORD + r"\s*(?:[-–—,(:/]\s*)?(?:i|1|one)\b(?![\d.])|"
    r"20\d\d\s+(?:start|starts?|graduates?|grads?|cohort)|"
    r"(?:start(?:ing|s)?|starts)\s+(?:in\s+)?(?:summer|fall|autumn|spring|"
    r"winter|\w+)?\s*20\d\d"
    r")",
    re.IGNORECASE,
)
# "2027 Software Engineer Program", "Infrastructure Engineer [2027 EDGE
# Program]": a class year plus "Program" is a campus hire, but only next to a
# role word. Without one it is a student event: Five Rings' "LINK 2027:
# Software Development Intensive Program" is a workshop for sophomores.
_YEAR_PROGRAM_RE = re.compile(
    r"(?<![\w#-])20\d\d(?![\w-])[^|]{0,80}?\bprogram(?:me)?\b"
    r"|\bprogram(?:me)?\b[^|]{0,80}?(?<![\w#-])20\d\d(?![\w-])",
    re.IGNORECASE,
)
_ROLE_WORD_RE = re.compile(r"\b" + _ROLE_WORD + r"\b", re.IGNORECASE)
# Explicit "school-leaver" wording outranks Junior/Associate/Entry Level when
# a title says several of them ("Associate Software Engineer (New Grad)").
_EXPLICIT_GRAD_RE = re.compile(
    r"\b(?:new[\s-]?grad|newgrad|recent[\s-]?grad|(?:university|college|campus)"
    r"[\s-]?grad|class\s+of\s+['’]?\d{2,4}|graduate|graduates|grad)\b",
    re.IGNORECASE,
)
_ROTATIONAL_RE = re.compile(r"\brotation(?:al)?\b", re.IGNORECASE)
_EARLY_CAREER_RE = re.compile(
    r"\bearly[\s-]?(?:in[\s-]?)?careers?\b|\bearly[\s-]?talent\b|\bemerging[\s-]?talent\b",
    re.IGNORECASE,
)
_ENTRY_LEVEL_RE = re.compile(r"\bentry[\s-]?level\b", re.IGNORECASE)
_JUNIOR_RE = re.compile(
    r"\b(?:junior|jr\.?|associate)\s+(?:" + _DOMAIN_WORD + r"\s+)?" + _ROLE_WORD,
    re.IGNORECASE,
)

# --- tech-role detection -----------------------------------------------------
# We keep ONLY software / data / ML / security roles. A role must match an
# INCLUDE term and must NOT match an EXCLUDE term. The exclude list removes
# non-software engineering (mechanical, aerospace, electrical/hardware, etc.)
# and non-technical roles (recruiting, sales, marketing, ...). Note we do NOT
# treat a bare "engineer" as tech — that word alone lets in mech/aero/civil.
_INCLUDE_RE = re.compile(
    r"\b("
    r"software|developer|swe|sde|full[\s-]?stack|"
    r"web developer|web engineer|ios|android|devops|devsecops|sre|site reliability|"
    r"infrastructure|platform engineer|platform engineering|distributed systems|"
    r"operating system|compiler|embedded|firmware|cloud engineer|cloud engineering|"
    r"database engineer|database engineering|database developer|"
    r"cyber|cybersecurity|appsec|application security|information security|infosec|"
    r"security engineer|"
    r"data science|data scientist|data engineer|data analyst|analytics engineer|"
    r"machine learning|ml|deep learning|ai|artificial intelligence|nlp|computer vision|"
    r"research scientist|applied scientist|research engineer|ml engineer|ai engineer|"
    r"quantitative (?:developer|research|researcher|trading|trader|analyst)|"
    r"quant (?:developer|research|researcher|trading|trader|analyst)|"
    r"computer science|programming"
    r")\b",
    re.IGNORECASE,
)
# "Front End" alone is a grocery department (Albertsons posted 170+ "Front End
# Entry Level" cashier roles); it is tech only next to an engineering word.
_CONTEXTUAL_TECH_RE = re.compile(
    r"\b(?:"
    r"(?:front|back)[\s-]?end(?:\s*/\s*(?:front|back)[\s-]?end)?\s+(?:web\s+)?"
    r"(?:engineer(?:ing)?|developer|development|dev|software|swe)|"
    r"mobile\s+(?:app(?:lication)?|software|developer|engineer|engineering)|"
    r"(?:app(?:lication)?|software|developer|ios|android)\s+mobile|"
    r"(?:computer|software|systems?)\s+programming|"
    r"programming\s+(?:language|software|engineer|engineering)"
    r")\b",
    re.IGNORECASE,
)
_ENTERTAINMENT_PROGRAMMING_RE = re.compile(
    r"\b(?:current|television|tv|radio|broadcast|content)\s+programming\b"
    r"|\bprogramming\b[^|/]{0,30}\b(?:television|tv|radio|broadcast|content)\b",
    re.IGNORECASE,
)

# Non-technical intent always wins, including titles that merely mention a
# software product ("Software Sales Associate"). Hardware disciplines are
# separate: an explicit software/embedded/firmware identity is allowed to
# coexist with them ("Embedded Software / Hardware Engineer I").
# PhD is deliberately NOT excluded here: "Research Scientist, New Grad (PhD)"
# is a real new grad tech role, unlike the intern tracker this descends from.
_NON_TECH_EXCLUDE_RE = re.compile(
    r"\b("
    r"recruit|recruiting|recruiter|sales|account executive|account manager|"
    r"account management|marketing|marketer|unpaid|"
    r"legal|counsel|accounting|human resources|people operations|people team|"
    # "talent" alone was here and dropped real roles: an "Emerging Talent
    # Software Engineer" is a named early-career PROGRAM, not HR. Only the
    # recruiting senses of the word exclude.
    r"talent acquisition|talent management|talent partner|talent sourcing|"
    r"talent operations|talent development|"
    r"communications|supply chain|business development|product design|product designer|"
    r"product manager|product management|ux design|graphic design|industrial design|"
    # A "Product Developer" formulates physical products (PPG's aerospace
    # sealants), not software. A "Job Developer" places clients in jobs.
    r"product developer|job developer|vocational"
    r")\b",
    re.IGNORECASE,
)
_HARDWARE_EXCLUDE_RE = re.compile(
    r"\b("
    r"mechanical|aerospace|aeronautical|astrodynamics|aerodynamic|propulsion|avionics|"
    r"guidance|navigation|gnc|naval|civil engineer|chemical|chemistry|chemist|"
    r"biology|biological|materials|structural|thermal|fluid|manufacturing|"
    r"industrial engineer|electrical|fpga|asic|pcb|analog|photonics|optical|"
    r"hardware|physical design|silicon|semiconductor|vlsi|rtl"
    r")\b",
    re.IGNORECASE,
)
_SOFTWARE_FIRST_RE = re.compile(
    r"\b(?:software|developer|swe|sde|devops|devsecops|sre|site reliability|"
    r"embedded|firmware|compiler|operating systems?|cloud engineer|"
    r"database engineer|platform engineer|security engineer)\b",
    re.IGNORECASE,
)


def is_new_grad(title: str) -> bool:
    """Does the title describe a role for someone finishing their degree?

    Positive evidence is the employer's own wording: "New Grad", "University
    Graduate", "Early Career", "Entry Level", "Class of 2027", a rotational
    program, "Associate"/"Junior" + a role word, a level-I title ("Software
    Engineer I"), or a campus program ("2027 Software Engineer Program",
    "Technology Development Program"). Internship, co-op, apprenticeship and
    fellowship titles are rejected outright, as is anything with a seniority
    word or a level above I.
    """
    if not title:
        return False
    if _INTERN_RE.search(title) or _SENIOR_RE.search(title) or _LEVEL_RE.search(title):
        return False
    if _NEW_GRAD_RE.search(title):
        return True
    return bool(_YEAR_PROGRAM_RE.search(title) and _ROLE_WORD_RE.search(title))


def is_tech(title: str) -> bool:
    """Keep software/data/ML/security roles; reject hardware/mech/non-tech."""
    if not title:
        return False
    if _NON_TECH_EXCLUDE_RE.search(title):
        return False
    if _ENTERTAINMENT_PROGRAMMING_RE.search(title):
        return False
    included = bool(_INCLUDE_RE.search(title) or _CONTEXTUAL_TECH_RE.search(title))
    if not included:
        return False
    if _HARDWARE_EXCLUDE_RE.search(title) and not _SOFTWARE_FIRST_RE.search(title):
        return False
    return True


# --- class-year detection ----------------------------------------------------
_CYCLE_RE = re.compile(r"Class of (20\d\d)", re.IGNORECASE)

# "Remote Sensing" is a field of study (satellites), not a work mode — a
# "Remote Sensing Software Engineer I" in Pasadena is an on-site job.
_REMOTE_RE = re.compile(r"\bremote\b(?!\s+sensing)", re.IGNORECASE)

PROGRAM_TYPES = ("New Grad", "Early Career", "Entry Level", "Rotational", "Junior / Associate")


def program_type(title: str) -> str:
    """Which early-career label the title itself uses.

    One of `PROGRAM_TYPES`. Explicit graduate wording wins ("Associate Software
    Engineer (New Grad)" is New Grad), then Rotational, Early Career, Entry
    Level, Junior / Associate. A level-I title with none of those words
    ("Software Engineer I") reads as New Grad, the level's conventional meaning.
    """
    t = title or ""
    if _EXPLICIT_GRAD_RE.search(t):
        return "New Grad"
    if _ROTATIONAL_RE.search(t):
        return "Rotational"
    if _EARLY_CAREER_RE.search(t):
        return "Early Career"
    if _ENTRY_LEVEL_RE.search(t):
        return "Entry Level"
    if _JUNIOR_RE.search(t):
        return "Junior / Associate"
    return "New Grad"


def is_remote(location: str, title: str = "") -> bool:
    """True when the posting itself says remote — in the location OR the title.

    Employers put it in either place: a "Software Engineer I (Remote)" title
    often carries a city in the location field, so reading only the location
    marked genuinely remote roles as on-site. Still no inference beyond the
    employer's own words.
    """
    return bool(_REMOTE_RE.search(location or "")) or bool(_REMOTE_RE.search(title or ""))


def is_cycle_label(value) -> bool:
    """True for a well-formed "Class of <Year>" label (tracked or not)."""
    return bool(value) and bool(_CYCLE_RE.fullmatch(str(value).strip()))


def cycle_label(year: int | str) -> str:
    return f"Class of {int(year)}"


def cycle_year(label: str) -> int | None:
    """2027 for "Class of 2027"; None for anything else (including NOT_STATED)."""
    m = _CYCLE_RE.fullmatch((label or "").strip())
    return int(m.group(1)) if m else None


# A four-digit year, but not one buried in a requisition id ("JR-2026-0042",
# "#2026123") or immediately followed by more digits. Ranges and short years
# are collected separately so their halves are not lost to these guards.
_YEAR_RE = re.compile(r"(?<![\w#-])(20\d\d)(?![\w-]|\s*[-–—/]\s*\d)")
_YEAR_RANGE_RE = re.compile(
    r"(?<![\w#-])(20\d\d)\s*(?:-|–|—|/|to|or|and|&|,)\s*(?:(20\d\d)|(\d\d))(?![\w-])"
)
# "Summer '27" / "New Grad '27": two-digit years behind an apostrophe.
_SHORT_YEAR_RE = re.compile(r"['’](\d{2})\b")
# Years that describe something other than the cohort.
_TITLE_NON_COHORT_RE = re.compile(
    r"\b(?:founded|since|est\.?|established|copyright|©)\s*(?:in\s+)?20\d\d"
    r"|\b(?:covid|sars-cov)[\s-]?(?:20)?19\b"
    r"|\bq[1-4]\s*[-/]?\s*(?:fy)?\s*20\d\d\b"
    r"|\bfy\s*'?(?:20)?\d\d\b",
    re.IGNORECASE,
)


def _title_years(title: str) -> list[int]:
    """Every cohort year a title states, ascending, de-duplicated."""
    if not title:
        return []
    scannable = _TITLE_NON_COHORT_RE.sub(" ", title)
    years: set[int] = set()
    for m in _YEAR_RANGE_RE.finditer(scannable):
        years.add(int(m.group(1)))
        years.add(int(m.group(2)) if m.group(2) else 2000 + int(m.group(3)))
    for m in _YEAR_RE.finditer(scannable):
        years.add(int(m.group(1)))
    for m in _SHORT_YEAR_RE.finditer(scannable):
        years.add(2000 + int(m.group(1)))
    return sorted(years)


def detect_seasons(title: str, cycles=("Class of 2027", "Class of 2026")) -> list[str]:
    """EVERY tracked class year the title states, in `cycles` order.

    "Software Engineer, New Grad (2026/2027)" is one requisition genuinely open
    to two graduating classes. A single-value season field can only keep one,
    so the other silently vanished from its own section. This collects the
    full set; `detect_season` still picks the primary. Evidence-only: a year
    must be present in the title, nothing is inferred from a posting date.
    """
    stated = {cycle_label(y) for y in _title_years(title)}
    return [label for label in cycles if label.strip() in stated]


def states_explicit_year(title: str) -> bool:
    """True when the title names a year at all.

    Used as a hard stop: when detect_season refused a year-stating title, that
    year is an untracked class — the role must not be rescued by a sticky
    stored season or a recency pass ("2025 New Grad" stays out, period).
    """
    return bool(_title_years(title))


def detect_season(title: str, cycles=("Class of 2027", "Class of 2026"), *_ignored) -> str | None:
    """Bucket a title into a class year ONLY if the year is explicit in the title.

    Strict on purpose: a role must actually state its year. Titles with no
    year fall through to `cycle_unstated_ok`, which keeps recent roles under
    `NOT_STATED` instead of guessing.

    Examples (cycles = Class of 2027, Class of 2026):
      "Software Engineer, New Grad (2027)"     -> "Class of 2027"
      "2026 University Graduate - SWE"         -> "Class of 2026"
      "Software Engineer I - Class of '27"     -> "Class of 2027"
      "New Grad Software Engineer (2026/2027)" -> "Class of 2027"  (primary; both kept)
      "Software Engineer I"                    -> None  (no year -> Not stated lane)
      "2025 New Grad Software Engineer"        -> None  (class not tracked -> drop)
    """
    stated = detect_seasons(title, cycles)
    return stated[0] if stated else None


NOT_STATED = "Not stated"
"""Bucket for a real, recent role whose class year nobody has actually stated.

Not a class year and never rendered as one. It exists so these roles can stay
on the list — "Software Engineer I" postings rarely name a graduating class —
without the list claiming to know something it doesn't.
"""


def cycle_unstated_ok(title: str, posted_at: str | None,
                      max_age_days: int = 45,
                      now: datetime | None = None) -> bool:
    """May a role with NO stated class year stay on the list?

    The internship engine this descends from once GUESSED a cycle from the
    posting month; measured against real postings the guess was never right
    when it could be checked, so it was removed. What survives is the useful
    half: the RECENCY test. A recently posted new grad tech role is worth
    showing even when nobody named its class — it is shown as `NOT_STATED`
    instead of wearing a fabricated label. Stale evergreen listings fall off.
    """
    if states_explicit_year(title):
        # The title names a year and detect_season refused it — an explicit
        # untracked class ("2025 New Grad"). It doesn't belong here.
        return False
    if not posted_at:
        return False  # no date -> can't establish recency
    try:
        posted = datetime.strptime(posted_at[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return False
    now = now or datetime.now(UTC)
    age_days = (now - posted).days
    return -1 <= age_days <= max_age_days  # -1 tolerates feed timezone skew


# --- class year stated in posting TEXT (verifies unstated roles) --------------
# Three tiers of evidence, strongest first. Each returns "Class of <Year>"
# labels; when a tier yields anything, weaker tiers are not consulted.
#   1. "Class of 2027" / "class of 2026 or 2027" / "Class of '27"
#   2. a graduation sentence: "graduating between December 2026 and June 2027",
#      "expected graduation date: May 2027", "2027 graduates", "degree
#      conferred by June 2027"
#   3. a start sentence: "start date in summer 2027", "starting in 2027",
#      "join us in August 2027"
_SENTENCE_BREAK = ".!?;\n"
_TEXT_YEAR_RE = re.compile(r"(?<![\w#-])(20\d\d)(?![\w-])")
_TEXT_SHORT_YEAR_RE = re.compile(r"['’](\d{2})\b")
_TEXT_CLASS_OF_RE = re.compile(
    r"\bclass(?:es)?\s+of\s+((?:['’]?\d{2,4})(?:\s*(?:,|/|-|–|—|or|and|&|to)\s*['’]?\d{2,4})*)",
    re.IGNORECASE,
)
_TEXT_GRAD_RE = re.compile(
    r"\b(?:graduat\w*|commencement|degree\s+(?:completion|conferr\w*|awarded)|"
    r"(?:complete|completing|completed|finish|finishing|finished|obtain\w*|"
    r"receiv\w*|earn\w*)\s+(?:a|an|your|their|the|his|her)?\s*"
    r"(?:bachelor|master|ba|bs|ms|meng|mba|phd|ph\.d|degree|undergraduate|graduate)\w*)\b",
    re.IGNORECASE,
)
_TEXT_START_RE = re.compile(
    r"\b(?:start(?:ing|s)?\s+dates?|start(?:ing|s)?|begin(?:ning|s)?|"
    r"join(?:ing)?\s+(?:us|the\s+team)|onboard\w*|cohorts?)\b",
    re.IGNORECASE,
)
# A date in this context describes the company, not the candidate.
_TEXT_COMPANY_RE = re.compile(r"\b(?:founded|established|since|incorporated)\b", re.IGNORECASE)
_TEXT_PAST_RE = re.compile(r"\b(?:graduated|completed|earned|received|obtained)\b", re.IGNORECASE)


def _sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    start = max(text.rfind(ch, 0, pos) for ch in _SENTENCE_BREAK) + 1
    ends = [p for ch in _SENTENCE_BREAK if (p := text.find(ch, pos)) >= 0]
    return start, (min(ends) if ends else len(text))


def _years_in(fragment: str) -> list[int]:
    years = [int(m.group(1)) for m in _TEXT_YEAR_RE.finditer(fragment)]
    years += [2000 + int(m.group(1)) for m in _TEXT_SHORT_YEAR_RE.finditer(fragment)]
    return years


def seasons_from_text(
    text: str, near: int = 160, now: datetime | None = None,
    include_start: bool = True,
) -> list[str]:
    """Every class year established by the strongest posting-text evidence tier.

    Returns "Class of <Year>" labels, latest class first. A posting that says
    "graduating between December 2026 and June 2027" states two classes and
    both are returned; the caller keeps the full set. Years outside the
    plausible window for a live new grad posting (last year through two years
    out) are ignored, as are years describing the company's history.
    `include_start=False` stops after the graduation tier: a start date says
    when a job begins, not who it is for.
    """
    if not text:
        return []
    now = now or datetime.now(UTC)
    year_lo, year_hi = now.year - 1, now.year + 2

    def plausible(years: list[int]) -> list[int]:
        return [y for y in years if year_lo <= y <= year_hi]

    def labels(years: list[int]) -> list[str]:
        return [cycle_label(y) for y in sorted(set(years), reverse=True)]

    # Tier 1: the employer names the class outright.
    found: list[int] = []
    for m in _TEXT_CLASS_OF_RE.finditer(text):
        raw = m.group(1)
        for piece in re.findall(r"['’]?\d{2,4}", raw):
            digits = piece.lstrip("'’")
            if len(digits) == 2:
                found.append(2000 + int(digits))
            elif len(digits) == 4:
                found.append(int(digits))
    if plausible(found):
        return labels(plausible(found))
    found = []  # an implausible "Class of 2031" must not leak into weaker tiers

    # Tier 2: a graduation sentence. Take the years that sit in the same
    # sentence, within `near` characters after the keyword (or shortly before
    # it: "2027 graduates").
    for m in _TEXT_GRAD_RE.finditer(text):
        s_start, s_end = _sentence_bounds(text, m.start())
        sentence = text[s_start:s_end]
        if _TEXT_COMPANY_RE.search(sentence):
            continue
        window = text[max(s_start, m.start() - 40):min(s_end, m.end() + near)]
        years = plausible(_years_in(window))
        if years and not (_TEXT_PAST_RE.fullmatch(m.group(0)) and max(years) < now.year):
            found.extend(years)
    if found or not include_start:
        return labels(found)

    # Tier 3: a start sentence.
    for m in _TEXT_START_RE.finditer(text):
        s_start, s_end = _sentence_bounds(text, m.start())
        sentence = text[s_start:s_end]
        if _TEXT_COMPANY_RE.search(sentence):
            continue
        window = text[m.start():min(s_end, m.end() + near)]
        found.extend(plausible(_years_in(window)))
    return labels(found)


def season_from_text(
    text: str, near: int = 160, now: datetime | None = None
) -> str | None:
    """The sole class year a posting's text establishes, otherwise ``None``."""
    labels = seasons_from_text(text, near=near, now=now)
    return labels[0] if len(labels) == 1 else None


# --- entry level stated in the posting TEXT ----------------------------------
# Most new grad roles are titled plainly ("Software Engineer") and say who they
# are for only in the description. This check is deliberately STRICT: it
# accepts a description only when it plainly targets new grads, asks for at
# most 0-2 years, or names a 2026/2027 graduation window, and it rejects any
# description that also asks for 2+ years or senior/lead duties. It never
# overrides a title that is senior, staff, II+, manager or intern
# (`title_allows_description_check`).
_DESC_AUDIENCE_RE = re.compile(
    r"\b(?:new|recent)\s+(?:college\s+|university\s+)?grad(?:uate)?s?\b"
    r"|\bnew[\s-]?grad\b"
    r"|\b(?:university|college)\s+grad(?:uate)?s?\b"
    r"|\bentry[\s-]level\b"
    r"|\bearly[\s-]in[\s-]career\b|\bearly[\s-]career\b",
    re.IGNORECASE,
)
# Words just BEFORE the phrase that turn it around: "not an entry-level role",
# "mentor new grads", "lead a team of early-career engineers".
_DESC_AUDIENCE_BEFORE_VETO_RE = re.compile(
    r"\b(?:not|no|isn't|non|beyond|past|above|mentor\w*|coach\w*|train\w*|"
    r"supervis\w*|manag\w*|lead\w*|guid\w*)\b",
    re.IGNORECASE,
)
# Words NEAR the phrase that make it a range or a pay band, not the audience:
# "from entry level to senior", "all levels", "the entry-level salary".
_DESC_AUDIENCE_NEAR_VETO_RE = re.compile(
    r"\b(?:senior|mid[\s-]?level|experienced|staff|principal|all\s+levels|"
    r"any\s+level|every\s+level|levels|ranging|salary|pay|compensation|wage)\b"
    r"|\bmore\s+experience\b",
    re.IGNORECASE,
)
_NUM_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15,
}
_NUM = r"(\d{1,2}|" + "|".join(_NUM_WORDS) + r")"
# "3-year degree" is an adjective, not an experience ask, so the number must
# be followed by a space or "+" before "year".
_YEARS = r"(?:\s*\+\s*|\s+(?:or\s+more\s+|plus\s+)?)(?:years?|yrs?)\b"
# What makes a "N years" phrase an experience ask: the word "experience"
# within six words ("1+ years of professional experience", "2 years' relevant
# experience"), or a job-history word right after it ("3+ years in an AI
# engineering role", "1-2 years building software").
_EXPERIENCE_AFTER = (
    r"(?:['’]s?)?\s+(?:of\s+)?(?:(?:[\w/&,+.#’'-]+\s+){0,6}?experience\b"
    r"|(?:in|as|working|building|developing|designing|programming|writing|"
    r"professional|industry|relevant|related|hands[\s-]on|post[\s-]?grad\w*)\b)"
)
_EXP_RANGE_RE = re.compile(
    r"\b" + _NUM + r"\s*(?:-|–|—|to)\s*" + _NUM + _YEARS + _EXPERIENCE_AFTER,
    re.IGNORECASE,
)
_EXP_UPTO_RE = re.compile(
    r"\b(?:up\s+to|less\s+than|under|no\s+more\s+than|fewer\s+than)\s+" + _NUM
    + _YEARS + _EXPERIENCE_AFTER,
    re.IGNORECASE,
)
_EXP_MIN_RE = re.compile(
    r"\b(?:(?:a\s+)?minimum\s+(?:of\s+)?|at\s+least\s+|min\.?\s+)?" + _NUM + r"(\s*\+)?"
    + _YEARS + _EXPERIENCE_AFTER,
    re.IGNORECASE,
)
_EXP_NONE_RE = re.compile(
    r"\bno\s+(?:prior\s+|previous\s+|professional\s+|work\s+|industry\s+)?"
    r"(?:work\s+)?experience\s+(?:is\s+)?(?:required|necessary|needed)\b",
    re.IGNORECASE,
)
# Senior duties stated as part of the job: these veto any positive signal.
_DESC_SENIOR_DUTY_RE = re.compile(
    r"\b(?:senior|staff|principal|lead)[\s-]level\b"
    r"|\bmentor(?:ing|s)?\s+(?:junior|other|less[\s-]experienced|new)\b"
    r"|\b(?:lead|leading|manage|managing|supervise|supervising)\s+(?:a\s+|the\s+)?"
    r"(?:team|teams|engineers|developers|group|staff)\b"
    r"|\bpeople\s+management\b|(?<!\bno\s)\bdirect\s+reports\b"
    r"|\btech(?:nical)?\s+lead(?:ership)?\s+(?:experience|role|responsibilit\w*)\b"
    r"|\bextensive\s+(?:professional\s+|industry\s+|hands[\s-]on\s+)?experience\b"
    r"|\bseasoned\b",
    re.IGNORECASE,
)


def _num(value: str) -> int:
    value = value.lower()
    return _NUM_WORDS[value] if value in _NUM_WORDS else int(value)


def _experience_asks(text: str) -> list[tuple[int, int | None]]:
    """Every "(min, max) years of experience" the text states."""
    asks: list[tuple[int, int | None]] = []
    spans: list[tuple[int, int]] = []
    for m in _EXP_RANGE_RE.finditer(text):
        asks.append((_num(m.group(1)), _num(m.group(2))))
        spans.append(m.span())
    for m in _EXP_UPTO_RE.finditer(text):
        asks.append((0, _num(m.group(1))))
        spans.append(m.span())
    for m in _EXP_MIN_RE.finditer(text):
        if any(a <= m.start() < b for a, b in spans):
            continue  # the upper half of a range already counted
        asks.append((_num(m.group(1)), None))
    if _EXP_NONE_RE.search(text):
        asks.append((0, 0))
    return asks


# Titles the posting text may never promote, beyond the seniority, intern and
# level words is_new_grad already refuses: Booz Allen's "Data Scientist - Mid"
# (only a separated "Mid", so "Mid-Atlantic Software Engineer" is fine),
# "Intermediate", and a bare trailing level like KLA's "Engr, Software 2".
_MID_TITLE_RE = re.compile(
    r"[-–—(,|/]\s*mid(?:[\s-]level)?\s*(?:$|[),|/]|[-–—]\s)|\bintermediate\b"
    r"|[\s,]+(?:[2-9]|ii|iii|iv|v)\s*$",
    re.IGNORECASE,
)


def title_allows_description_check(title: str) -> bool:
    """May the posting text decide this title? Never for a senior, staff,
    II+, manager or intern title, and only for tech titles that lack
    new-grad wording (those pass on the title alone)."""
    if not title or is_new_grad(title):
        return False
    if _INTERN_RE.search(title) or _SENIOR_RE.search(title) or _LEVEL_RE.search(title):
        return False
    if _MID_TITLE_RE.search(title):
        return False
    return is_tech(title)


def is_entry_level(title: str, entry_signal: str | None = None) -> bool:
    """The title says new grad, or the posting text did and the title allows
    it (a role listed with ``entry_signal="description"``)."""
    if is_new_grad(title):
        return True
    return entry_signal == "description" and title_allows_description_check(title)


def description_entry_reason(text: str, cycles=("Class of 2027", "Class of 2026"),
                             now: datetime | None = None) -> str | None:
    """Why the posting text makes this an entry-level role, or None.

    One of "audience" (the text says it is for new/recent/university grads,
    entry level or early career), "experience" (it asks for at most 0-2 years:
    "0-2 years", "1+ years", "up to 2 years", "no experience required") or
    "graduation" (a graduation window that includes a tracked class: "Class of
    2026", "graduating by June 2027"). Any ask for 2+ years or a range past 2
    ("1-3 years" is not accepted on experience), or senior/lead duties
    ("mentor junior engineers", "lead a team"), returns None.
    """
    if not text:
        return None
    flat = re.sub(r"[–—]", "-", text)
    asks = _experience_asks(flat)
    # Strict: any ask for 2+ years rules the posting out, even next to a
    # "1+ years" line ("2+ years shipping production software").
    if any(low >= 2 for low, _high in asks):
        return None
    if _DESC_SENIOR_DUTY_RE.search(flat):
        return None
    for m in _DESC_AUDIENCE_RE.finditer(flat):
        start, end = _sentence_bounds(flat, m.start())
        before = flat[max(start, m.start() - 40):m.start()]
        near = flat[max(start, m.start() - 120):min(end, m.end() + 120)]
        if not (_DESC_AUDIENCE_BEFORE_VETO_RE.search(before)
                or _DESC_AUDIENCE_NEAR_VETO_RE.search(near)):
            return "audience"
    if asks and all(high is None or high <= 2 for _low, high in asks):
        return "experience"
    tracked = {c.strip() for c in cycles}
    stated = seasons_from_text(flat, now=now, include_start=False)
    if tracked.intersection(stated):
        return "graduation"
    return None


# --- location: US / Canada detection -----------------------------------------
# Full state/province names are matched case-insensitively; the 2-letter codes
# are matched case-SENSITIVELY (uppercase) so "OR"/"IN" don't match the words
# "or"/"in" inside a city name.
_US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia",
]
_CA_PROVINCES = [
    "ontario", "quebec", "british columbia", "alberta", "manitoba",
    "saskatchewan", "nova scotia", "new brunswick", "newfoundland", "labrador",
    "prince edward island", "yukon", "northwest territories", "nunavut",
]
_US_CODES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
    "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
    "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
    "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
    "WI", "WY", "DC", "US", "USA",
]
_CA_CODES = ["ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE", "YT", "NT", "NU"]

# US country tokens. These MUST be matched as whole tokens, never as substrings:
# "usa" hides inside Lausanne, Jerusalem, Busan, Sausalito and dozens of other
# real ATS locations, and a substring test made every one of them read as the
# US. The lookarounds (rather than \b) are what let "U.S." keep its periods.
_US_COUNTRY_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    r"united\s+states(?:\s+of\s+america)?"
    r"|u\.\s?s\.?\s?a\.?"
    r"|u\.\s?s\.?"
    r"|usa"
    r"|america"
    r")(?![a-z0-9])",
    re.IGNORECASE,
)
# "Latin America" / "South America" must not read as the US ("america" token).
_AMERICA_NOT_US_RE = re.compile(r"\b(?:south|latin|central)\s+america")

# Countries that appear in ATS location strings and must never read as US, even
# when a state-code lookalike sits next to them ("IN - Bangalore, India" is not
# Indiana). An explicit US token still wins for multi-country strings.
# NOTE on omissions: "georgia" is a US state as well as a country, and
# "england" hides inside "New England" — both are handled below rather than
# listed here, so a US location never loses to a name collision.
_NON_US_COUNTRIES = (
    "india", "united kingdom", "great britain", "scotland", "wales",
    "northern ireland", "ireland", "germany", "france", "poland",
    "netherlands", "spain", "italy", "portugal", "romania", "hungary",
    "bulgaria", "croatia", "serbia", "slovenia", "bosnia", "albania",
    "montenegro", "macedonia", "ukraine", "belarus", "russia", "moldova",
    "lithuania", "latvia", "estonia", "luxembourg", "iceland", "cyprus",
    "malta", "czech", "slovakia", "sweden", "switzerland", "belgium",
    "austria", "denmark", "norway", "finland", "greece", "turkey", "israel",
    "united arab emirates", "saudi arabia", "qatar", "kuwait", "bahrain",
    "oman", "jordan", "lebanon", "iraq", "iran", "afghanistan", "egypt",
    "morocco", "tunisia", "algeria", "nigeria", "ghana", "senegal",
    "ethiopia", "kenya", "tanzania", "uganda", "zimbabwe", "botswana",
    "namibia", "south africa", "brazil", "mexico", "argentina", "colombia",
    "chile", "peru", "bolivia", "paraguay", "uruguay", "venezuela",
    "ecuador", "panama", "costa rica", "guatemala", "honduras", "nicaragua",
    "el salvador", "belize", "dominican republic", "jamaica", "trinidad",
    "japan", "china", "singapore", "korea", "taiwan", "hong kong", "macau",
    "philippines", "indonesia", "vietnam", "thailand", "cambodia",
    "myanmar", "malaysia", "pakistan", "bangladesh", "sri lanka", "nepal",
    "mongolia", "kazakhstan", "uzbekistan", "azerbaijan", "armenia",
    "australia", "new zealand", "fiji",
)
_NON_US_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _NON_US_COUNTRIES) + r")\b"
    # "England" is a foreign country only when it isn't "New England".
    r"|(?<!new\s)\bengland\b"
)

_US_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _US_STATES) + r")\b", re.IGNORECASE
)
_CA_NAME_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in _CA_PROVINCES) + r")\b", re.IGNORECASE
)
# case-sensitive; (?!-) avoids matching country-style prefixes like "DE-Berlin"
# (Germany) as the US state code DE (Delaware).
_US_CODE_RE = re.compile(r"\b(" + "|".join(_US_CODES) + r")\b(?!-)")
_CA_CODE_RE = re.compile(r"\b(" + "|".join(_CA_CODES) + r")\b(?!-)")

_LOCATION_PART_RE = re.compile(r"[,;|]+")
_LOCATION_OPTION_RE = re.compile(r"[;|]+")
_GEORGIA_COUNTRY_CITIES = {
    "tbilisi", "batumi", "kutaisi", "rustavi", "gori", "zugdidi",
}


# Workday's list API shows "2 Locations" / "5 Locations" instead of the places
# when a role is open in several. That says nothing about the country, so it
# must not count as foreign: Adobe, NVIDIA and Blue Origin new grad roles were
# dropped for it. The detail page lists the real places (see enrich).
_LOCATION_PLACEHOLDER_RE = re.compile(r"^\s*\d+\s+locations?\s*$", re.IGNORECASE)

# Employers often give a bare city ("Miami", "SAN JOSE", "Seattle (hybrid)").
# These are well-known US cities whose name is not also a city that shows up in
# foreign or Canadian postings. Deliberately left out because the name is
# shared: London, Paris, Cambridge, Oxford, Birmingham, Manchester, Dublin,
# Durham, Richmond, Vancouver, Victoria, Kingston, Windsor, Waterloo, Hamilton,
# Athens, Alexandria, Melbourne, Toledo, Aurora, Georgetown. Those still need
# a state or country to count as US. "San Jose" is kept: a Costa Rica posting
# names the country, which is checked first and wins.
_US_CITIES = frozenset({
    "new york", "new york city", "nyc", "manhattan", "brooklyn",
    "san francisco", "sf", "sf bay", "bay", "silicon valley",
    "los angeles", "san diego", "san jose", "sunnyvale", "mountain view",
    "palo alto", "menlo park", "santa clara", "cupertino", "redwood city",
    "san mateo", "foster city", "south san francisco", "oakland", "berkeley",
    "emeryville", "fremont", "milpitas", "pleasanton", "irvine", "santa monica",
    "culver city", "el segundo", "pasadena", "burbank", "long beach",
    "sacramento", "carlsbad", "seattle", "bellevue", "redmond", "kirkland",
    "tacoma", "spokane", "portland", "beaverton", "hillsboro", "boise",
    "salt lake city", "lehi", "provo", "denver", "boulder", "colorado springs",
    "phoenix", "scottsdale", "tempe", "chandler", "tucson", "las vegas",
    "albuquerque", "austin", "dallas", "houston", "san antonio", "fort worth",
    "plano", "irving", "frisco", "el paso", "oklahoma city", "tulsa",
    "kansas city", "omaha", "minneapolis", "st paul", "saint paul", "chicago",
    "evanston", "milwaukee", "madison", "detroit", "ann arbor", "grand rapids",
    "indianapolis", "columbus", "cleveland", "cincinnati", "pittsburgh",
    "philadelphia", "baltimore", "boston", "somerville", "providence",
    "hartford", "stamford", "new haven", "jersey city", "hoboken", "newark",
    "princeton", "arlington", "reston", "herndon", "mclean",
    "tysons", "chantilly", "fairfax", "annapolis junction", "columbia",
    "bethesda", "rockville", "gaithersburg", "raleigh", "cary",
    "charlotte", "research triangle park", "rtp", "atlanta", "alpharetta",
    "nashville", "memphis", "knoxville", "louisville", "lexington",
    "st louis", "saint louis", "huntsville", "orlando",
    "tampa", "miami", "jacksonville", "fort lauderdale", "boca raton",
    "new orleans", "baton rouge", "honolulu", "anchorage", "des moines",
    "charleston", "greenville", "rochester", "buffalo", "syracuse",
    "palm bay", "dayton", "akron", "norfolk",
    "virginia beach", "san luis obispo", "santa barbara", "goleta",
})
_CITY_NOISE_RE = re.compile(
    r"\([^)]*\)"
    r"|\b(?:remote|hybrid|on[\s-]?site|in[\s-]?office|general\s+offices?|offices?|"
    r"headquarters|hq|campus|metro(?:politan)?|area|greater)\b",
    re.IGNORECASE,
)
# "US-WA-Bellevue", "US-AZ-TUCSON-805 ~ ...": country-state-city codes.
_US_PREFIX_RE = re.compile(
    r"^\s*(?:US|USA)\s*[-–:]\s*(?:" + "|".join(c for c in _US_CODES if len(c) == 2)
    + r")\b"
)


def is_location_placeholder(location: str) -> bool:
    """True for Workday's "N Locations" stand-in for a multi-place role."""
    return bool(_LOCATION_PLACEHOLDER_RE.match(location or ""))


def _is_bare_us_city(option: str) -> bool:
    """"Miami", "SAN JOSE", "Seattle (hybrid)", "Greater Seattle Area"."""
    core = _CITY_NOISE_RE.sub(" ", option.lower()).replace(".", "")
    core = " ".join(re.sub(r"[^a-z' ]+", " ", core).split())
    return core in _US_CITIES


def _location_parts(location: str) -> list[str]:
    return [part.strip() for part in _LOCATION_PART_RE.split(location) if part.strip()]


def _structured_signal(
    parts: list[str], names: list[str], codes: list[str]
) -> tuple[int, str, str] | None:
    """Rightmost state/province component as ``(index, kind, value)``."""
    by_length = sorted(names, key=len, reverse=True)
    for index in range(len(parts) - 1, -1, -1):
        low = parts[index].lower().strip()
        for name in by_length:
            if re.fullmatch(
                rf"{re.escape(name)}(?:\s+(?:[-–—(]).*)?", low, re.IGNORECASE
            ) or re.search(
                rf"(?:^|\s[-–—]\s){re.escape(name)}$", low, re.IGNORECASE
            ):
                return index, "name", name
        for code in codes:
            # A structured component accepts lowercase ("Austin, tx"), but a
            # country-style prefix such as "DE-Berlin" deliberately does not.
            if re.fullmatch(
                rf"{re.escape(code)}(?:\s+(?:[-–—(]).*)?", parts[index], re.IGNORECASE
            ):
                return index, "code", code
    return None


def _matching_part_indexes(parts: list[str], pattern: re.Pattern) -> list[int]:
    return [index for index, part in enumerate(parts) if pattern.search(part.lower())]


def is_united_states(location: str) -> bool:
    if not location:
        return False
    # Several connectors preserve every advertised location by joining
    # alternatives with semicolons.  Evaluate each option independently:
    # otherwise a foreign country in the last option can veto a valid US
    # option (and reversing the employer's list changes the answer).
    options = [part.strip() for part in _LOCATION_OPTION_RE.split(location)
               if part.strip()]
    if len(options) > 1:
        return any(is_united_states(option) for option in options)
    low = location.lower()
    stripped = _AMERICA_NOT_US_RE.sub(" ", low)
    if _US_COUNTRY_RE.search(stripped) or _US_PREFIX_RE.match(location):
        return True
    parts = _location_parts(location)
    us_signal = _structured_signal(parts, _US_STATES, _US_CODES)
    ca_signal = _structured_signal(parts, _CA_PROVINCES, _CA_CODES)
    foreign_indexes = _matching_part_indexes(parts, _NON_US_RE)
    canada_indexes = [
        index for index, part in enumerate(parts)
        if re.search(r"\bcanada\b", part, re.IGNORECASE)
    ]

    if us_signal:
        index, kind, value = us_signal
        # A named country to the right is an actual country qualifier:
        # "IN - Bangalore, India" and "CA - Sydney, Australia" are foreign.
        if any(country_index > index for country_index in foreign_indexes):
            return False
        if any(country_index > index for country_index in canada_indexes):
            return False
        if value == "georgia" and any(
            city in parts[0].lower() for city in _GEORGIA_COUNTRY_CITIES
        ):
            return False
        if kind == "code" and (ca_signal or canada_indexes):
            # "Milton, Ontario, CA" is Canada; a province outranks the
            # California-looking suffix. A full state name remains decisive,
            # so "Ontario, California" stays correctly American.
            # Ontario, California is commonly abbreviated "Ontario, CA".
            # It is a two-component US city/state location; the Canadian form
            # carries another city/province component ("Milton, Ontario, CA")
            # or an explicit Canada qualifier.
            if (
                value == "CA" and len(parts) == 2
                and parts[0].strip().casefold() == "ontario"
                and not canada_indexes
            ):
                return True
            return False
        return True

    if foreign_indexes:
        return False
    if _US_NAME_RE.search(low):
        return True
    if re.search(r"\b(?:canada|canadian)\b", low) or _CA_NAME_RE.search(low):
        return False
    if _US_CODE_RE.search(location):
        return True
    return _is_bare_us_city(location)


def is_canada(location: str) -> bool:
    if not location:
        return False
    options = [part.strip() for part in _LOCATION_OPTION_RE.split(location)
               if part.strip()]
    if len(options) > 1:
        return any(is_canada(option) for option in options)
    if is_united_states(location):
        return False
    low = location.lower()
    if re.search(r"\b(?:canada|canadian)\b", low):
        return True
    if _CA_NAME_RE.search(low):
        return True
    if _CA_CODE_RE.search(location):
        return True
    return False


def is_us_or_canada(location: str) -> bool:
    return is_united_states(location) or is_canada(location)


def region_ok(location: str, want_us: bool, want_canada: bool) -> bool:
    """True if the location matches one of the wanted regions.

    Conservative: a bare "Remote" with no country mentioned matches nothing.
    The one exception is Workday's "N Locations" placeholder, which names no
    place at all: it is unknown, not foreign, so it is not rejected here. The
    pipeline swaps in the real places from the detail page when it can.
    """
    if (want_us or want_canada) and is_location_placeholder(location):
        return True
    if want_us and is_united_states(location):
        return True
    if want_canada and is_canada(location):
        return True
    return False


# --- category tagging (first match wins; order = specific before generic) -----
_CATEGORY_PATTERNS = [
    ("Quant", re.compile(r"\b(quant|quantitative|trading|trader)\b", re.IGNORECASE)),
    (
        "Data & ML/AI",
        re.compile(
            r"\b(data|machine learning|\bml\b|\bai\b|artificial intelligence|"
            r"deep learning|nlp|computer vision|research scientist|"
            r"applied scientist|analytics)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Hardware",
        re.compile(
            r"\b(hardware|electrical|firmware|asic|fpga|robotics|mechanical|"
            r"chip|silicon|manufacturing|industrial|analog|photonics|optical)\b",
            re.IGNORECASE,
        ),
    ),
    ("Security", re.compile(r"\b(cyber|infosec|appsec|security)", re.IGNORECASE)),
    (
        "Software",
        re.compile(
            r"\b(software|developer|swe|backend|frontend|full[\s-]?stack|"
            r"mobile|ios|android|devops|sre|infrastructure|platform|systems|"
            r"cloud|web|compiler|embedded|firmware|engineer|engineering|"
            r"programming|computer science)\b",
            re.IGNORECASE,
        ),
    ),
]


def categorize(title: str) -> str:
    if not title:
        return "Other"
    for name, pattern in _CATEGORY_PATTERNS:
        if pattern.search(title):
            return name
    return "Other"
