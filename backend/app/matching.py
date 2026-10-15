"""Conservative, explainable early-career matching, without inventing years."""
import re
from html import unescape
from dataclasses import dataclass
from bs4 import BeautifulSoup

SOFTWARE = re.compile(r"\b(software|sde|sdet|full[ -]?stack|front[ -]?end|back[ -]?end|web developer|application developer|java developer|python developer|programmer|development engineer)\b", re.I)
SENIOR = re.compile(r"\b(senior|sr\.?|staff|principal|lead|manager|director|architect|head|vp|iii|iv)\b", re.I)
EARLY = re.compile(r"\b(junior|jr\.?|graduate|new grad|entry[ -]level|early[ -]career|associate|intern|apprentice|trainee|engineer\s+(?:i|1))\b", re.I)
YEARS = re.compile(r"(?P<low>\d+(?:\.\d+)?)\s*(?:(?:-|–|—|to)\s*(?P<high>\d+(?:\.\d+)?)\s*)?(?P<plus>\+)?\s*(?:years?|yrs?)\b(?:\s+(?:of\s+)?(?:relevant\s+|professional\s+|work\s+|industry\s+|hands-on\s+|commercial\s+|software\s+|development\s+|engineering\s+|programming\s+|related\s+){0,4}experience)?", re.I)
SKILLS = ["Python", "JavaScript", "TypeScript", "Java", "React", "Angular", "Node.js", "C++", "C#", "Go", "SQL", "AWS", "Azure", "Docker", "Kubernetes", ".NET", "Spring", "Git", "Linux"]


def plain(html: str) -> str:
    return BeautifulSoup(unescape(html or ""), "html.parser").get_text("\n", strip=True)


def software_title(title: str) -> bool:
    return bool(SOFTWARE.search(title)) and not bool(SENIOR.search(title))


@dataclass
class Match:
    confidence: str
    experience_min: float | None
    experience_max: float | None
    evidence: str


def match_job(title: str, description: str) -> Match | None:
    if not software_title(title):
        return None
    text = plain(description)
    requirements = []
    for hit in YEARS.finditer(text):
        context = text[max(0, hit.start()-65):min(len(text), hit.end()+90)]
        # Ignore company age, study duration, and marketing numbers.
        if not re.search(r"experience|proficiency|develop|programming|working|building", context, re.I):
            continue
        if re.search(r"(?:founded|established|last|past|over the|degree|course|study)\s*$", text[max(0, hit.start()-25):hit.start()], re.I):
            continue
        low = float(hit.group("low"))
        high = float(hit.group("high")) if hit.group("high") else None
        requirements.append((low, high, context.strip()))
    # Conservative: any explicit requirement beyond two years excludes a posting.
    if any(low > 2 or (high is not None and high > 2) for low, high, _ in requirements):
        return None
    if requirements:
        low, high, evidence = max(requirements, key=lambda x: x[0])
        return Match("confirmed", low, high, evidence)
    if re.search(r"no (?:prior |previous |professional )?experience (?:is )?(?:required|necessary)|0[ -]2 years", text, re.I):
        return Match("confirmed", 0, 2, "The posting explicitly welcomes candidates without previous experience.")
    if EARLY.search(title):
        return Match("possible", None, None, "Early-career wording in the title; years of experience are not stated. Check the original requirements.")
    return None


def skills_from(text: str) -> list[str]:
    return [s for s in SKILLS if re.search(r"(?<!\w)" + re.escape(s) + r"(?!\w)", text, re.I)][:7]


def work_mode(title: str, location: str, description: str) -> str:
    text = f"{title} {location} {description[:600]}"
    if re.search(r"\bhybrid\b", text, re.I):
        return "Hybrid"
    if re.search(r"\bremote\b|work from home", text, re.I):
        return "Remote"
    return "Not specified"
