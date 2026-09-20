import re
import sys
import json
import time
import shutil
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://utsc.calendar.utoronto.ca"
HERE = Path(__file__).parent
DATA = HERE / "data"
RAW = DATA / "raw"
POLICIES = DATA / "policies"

POLICY_PAGES = [
    "/grades-and-academic-records",
    "/program-regulations",
    "/course-regulations",
    "/academic-integrity",
    "/final-exams-and-assessments",
    "/petitions-and-appeals",
]
DELAY = 1.0  # seconds between real network requests
HEADERS = {"User-Agent": "vision-course-advisor (student project, personal and educational use)"}

CODE = r"[A-Z]{3}[A-D]\d{2}[HY]\d"
COURSE_HEAD = re.compile(rf"^({CODE})\s+[-–—]\s+(.+)$")
LABELS = r"(Prerequisites?|Corequisites?|Exclusions?|Recommended Preparation|Breadth Requirements?|Course Experience|Note)"
LABEL_INLINE = re.compile(rf"^{LABELS}\s*:\s*(.+)$", re.I)
LABEL_ONLY = re.compile(rf"^{LABELS}\s*:?\s*$", re.I)
PROGRAM_CODE = re.compile(r"^(.+?)\s+-\s+([A-Z]{5}\d{4}[A-Z]?)\s*$")
PROGRAM_WORDS = re.compile(r"^(DOUBLE DEGREE|COMBINED|JOINT|CERTIFICATE)\b")
INLINE = ["a", "strong", "b", "em", "i", "span", "u", "sup", "sub", "font", "abbr"]


def fetch(path):
    RAW.mkdir(parents=True, exist_ok=True)
    cache = RAW / (re.sub(r"[^A-Za-z0-9]+", "_", path.strip("/")).lower() + ".html")
    if cache.exists():
        return cache.read_text(encoding="utf-8")
    time.sleep(DELAY)
    try:
        r = requests.get(BASE + path, headers=HEADERS, timeout=60)
    except requests.RequestException as e:
        print("skip", path, e)
        return None
    if r.status_code != 200:
        print("skip", path, r.status_code)
        return None
    cache.write_text(r.text, encoding="utf-8")
    return r.text


KEEP = re.compile(rf"{CODE}|[A-Z]{{5}}\d{{4}}")
CHROME = ["script", "style", "title", "select", "#header", "#main-navigation-h",
          "#footer-menu", ".off-canvas-wrapper", ".first-sidebar", "#highlighted"]

def debug(html, lines):
    print(f"   page has {len(html):,} characters of HTML and {len(lines)} text lines after cleanup")
    print("   lines mentioning a course code:", [l for l in lines if re.search(CODE, l)][:5])
    m = re.search(CODE, html)
    if m:
        print("   raw HTML around the first course code:", repr(html[max(0, m.start() - 200): m.start() + 200]))


def page_lines(html):
    """Return (page name, list of visible text lines) with site menus removed."""
    soup = BeautifulSoup(html, "html.parser")
    name = soup.title.get_text().split("|")[0].strip() if soup.title else "Unknown"
    for sel in CHROME:
        for t in soup.select(sel):
            t.decompose()
    for t in soup.select("header, nav, footer, form"):
        if getattr(t, "decomposed", False):
            continue
        if not KEEP.search(t.get_text()):
            t.decompose()
    for t in soup(INLINE):
        t.unwrap()
    soup.smooth()
    lines = [re.sub(r"\s+", " ", l).strip() for l in soup.get_text("\n").splitlines()]
    return name, [l for l in lines if l]


def section_links(html):
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for a in soup.find_all("a", href=True):
        path = urlparse(a["href"]).path
        if path.startswith("/section/") and path not in found:
            found.append(path)
    return found


def parse_prereqs(text):
    """Best-effort AND-of-ORs of course codes. Flags text it cannot represent exactly."""
    if not text:
        return [], False
    clean = re.sub(rf"\(\s*{CODE}\s*\)", "", text)  # (CODE) = course no longer offered
    groups = []
    for part in re.split(r"\band\b|[,;]", clean):
        alts = re.findall(CODE, part)
        if alts:
            groups.append(alts)
    messy = bool(
        re.search(r"[\[\](){}]|permission|grade|GPA|credit|program|POSt|\bmin|instructor", text, re.I)
        or (re.search(r"\bor\b|/", text) and re.search(r"\band\b", text))
    )
    return groups, messy


def split_label(line):
    m = LABEL_INLINE.match(line)
    if m:
        return m.group(1), m.group(2)
    m = LABEL_ONLY.match(line)
    if m:
        return m.group(1), ""
    return None


def build_course(code, title, block, section):
    desc, fields, cur = [], {}, None
    for line in block:
        lab = split_label(line)
        if lab:
            cur = lab[0].lower().rstrip("s")
            fields[cur] = [lab[1]] if lab[1] else []
        elif cur:
            fields[cur].append(line)
        else:
            desc.append(line)
    text = lambda k: " ".join(fields.get(k, [])).strip()
    prereq = text("prerequisite")
    groups, messy = parse_prereqs(prereq)
    return {
        "code": code,
        "title": title,
        "section": section,
        "description": " ".join(desc),
        "credits": 0.5 if code[-2] == "H" else 1.0,
        "prereqs": groups,
        "prereq_text": prereq,
        "needs_review": messy,
        "corequisites": re.findall(CODE, text("corequisite")),
        "exclusions": re.findall(r"[A-Z]{3}[A-D]?\d{2,3}[HY]\d?", text("exclusion")),
        "recommended": text("recommended preparation"),
        "breadth": text("breadth requirement"),
        "experience": text("course experience"),
        "note": text("note"),
        "source": f"{BASE}/course/{code}",
    }


def parse_courses(lines, section):
    courses, i = [], 0
    while i < len(lines):
        m = COURSE_HEAD.match(lines[i])
        if not m:
            i += 1
            continue
        code, title = m.group(1), m.group(2).strip()
        j, block = i + 1, []
        while j < len(lines) and not lines[j].startswith("Link to UTSC Timetable") and not COURSE_HEAD.match(lines[j]):
            block.append(lines[j])
            j += 1
        courses.append(build_course(code, title, block, section))
        i = j
    return courses


def parse_programs(lines, section, path):
    """Everything that is not a course block, chunked and prefixed with its nearest program heading."""
    programs, chunks = [], []
    slug = re.sub(r"[^a-z0-9]+", "-", section.lower()).strip("-")
    heading, buf, size, n = f"{section} (overview)", [], 0, 0

    def flush():
        nonlocal buf, size, n
        if buf:
            chunks.append({
                "id": f"prog-{slug}-{n}",
                "source": f"{section}: {heading}",
                "url": BASE + path,
                "text": f"[{section} | {heading}]\n" + "\n".join(buf),
            })
            n += 1
        buf, size = [], 0

    i = 0
    while i < len(lines):
        line = lines[i]
        if COURSE_HEAD.match(line):  # skip the whole course block
            i += 1
            while i < len(lines) and not lines[i].startswith("Link to UTSC Timetable") and not COURSE_HEAD.match(lines[i]):
                i += 1
            if i < len(lines) and lines[i].startswith("Link to UTSC Timetable"):
                i += 1
            continue
        m = PROGRAM_CODE.match(line)
        if len(line) < 300 and (m or PROGRAM_WORDS.match(line)):
            flush()
            heading = line
            programs.append({
                "name": m.group(1) if m else line,
                "code": m.group(2) if m else "",
                "section": section,
                "url": BASE + path,
            })
        else:
            buf.append(line)
            size += len(line)
            if size >= 1100:
                flush()
        i += 1
    flush()
    return programs, chunks


def arg(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else None


def main():
    only = arg("--only")
    suffix = "_test" if only else ""
    if "--fresh" in sys.argv and RAW.exists():
        shutil.rmtree(RAW)
    POLICIES.mkdir(parents=True, exist_ok=True)

    index_html = fetch("/program-sections")
    if not index_html:
        sys.exit("Could not load the Program Sections page.")
    sections = section_links(index_html)
    if only:
        sections = [s for s in sections if only.lower() in s.lower()]
    print(f"{len(sections)} sections to fetch")

    courses, programs, chunks = {}, [], []
    for n, path in enumerate(sections, 1):
        html = fetch(path)
        if not html:
            continue
        section, lines = page_lines(html)
        found = parse_courses(lines, section)
        progs, chs = parse_programs(lines, section, path)
        if not found or not progs:
            debug(html, lines)
        for c in found:
            courses.setdefault(c["code"], c)
        programs += progs
        chunks += chs
        print(f"[{n}/{len(sections)}] {section}: {len(found)} courses, {len(progs)} programs")

    if not only:
        for old in list(POLICIES.glob("policy_*.txt")) + list(POLICIES.glob("program_*.txt")):
            old.unlink()
        for path in POLICY_PAGES:
            html = fetch(path)
            if html:
                name, lines = page_lines(html)
                slug = re.sub(r"[^a-z0-9]+", "_", path.strip("/").lower())
                (POLICIES / f"policy_{slug}.txt").write_text(f"{name}\n" + "\n".join(lines), encoding="utf-8")

    course_list = list(courses.values())
    (DATA / f"courses{suffix}.json").write_text(json.dumps(course_list, indent=2), encoding="utf-8")
    (DATA / f"programs{suffix}.json").write_text(
        json.dumps({"programs": programs, "chunks": chunks}, indent=2), encoding="utf-8"
    )
    flagged = sum(c["needs_review"] for c in course_list)
    print(f"\nSaved {len(course_list)} courses ({flagged} with complicated prerequisites), "
          f"{len(programs)} programs, {len(chunks)} program text chunks.")


if __name__ == "__main__":
    main()