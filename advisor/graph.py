import json
from pathlib import Path
import networkx as nx

BASE = Path(__file__).parent


def build_graph(path=BASE / "data" / "courses.json"):
    courses = {c["code"]: c for c in json.load(open(path, encoding="utf-8"))}
    g = nx.DiGraph()
    for code, c in courses.items():
        g.add_node(code, title=c["title"], credits=c["credits"])
    for code, c in courses.items():
        for group in c["prereqs"]:
            for p in group:
                g.add_edge(p, code)  # p unlocks code
    return g, courses


def prereq_text(courses, code):
    groups = courses[code]["prereqs"]
    if not groups:
        return "no prerequisites"
    return " AND ".join("(" + " OR ".join(grp) + ")" for grp in groups)


def unlocks(g, code):
    return sorted(g.successors(code))


def can_take(courses, code, completed):
    done = set(completed)
    return all(any(p in done for p in grp) for grp in courses[code]["prereqs"])