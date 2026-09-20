import re, json
import ollama
from advisor.index import search
from advisor.graph import build_graph, prereq_text, unlocks

LLM = "llama3.2"
g, courses = build_graph()


CODE_RE = re.compile(r"\b([A-Za-z]{3}\s?[A-Da-d]\d{2})([HhYy]\d)?\b")



SHORT_RE = re.compile(r"\b([A-Da-d]\d{2})\b")

def find_codes(q):
    out = []
    for base, suffix in CODE_RE.findall(q):
        base = base.replace(" ", "").upper()
        if suffix:
            out.append(base + suffix.upper())
        else:
            out += [c for c in courses if c.startswith(base)]
    for short in SHORT_RE.findall(q):
        matches = [c for c in courses if c[3:6] == short.upper()]
        if len(matches) <= 2:          # skip ambiguous ones like "a01"
            out += matches
    return list(dict.fromkeys(out))

def graph_facts(codes):
    facts = []
    for c in codes:
        if c not in courses:
            continue
        course = courses[c]
        if course["needs_review"]:
            facts.append(f"{c} prerequisites (calendar wording): {course['prereq_text'] or 'none listed'}.")
        else:
            facts.append(f"{c} prerequisites: {prereq_text(courses, c)}.")
        facts.append(f"{c} directly unlocks: {', '.join(unlocks(g, c)) or 'nothing in the dataset'}.")
    return facts

def ask_json(prompt):
    r = ollama.chat(
        model=LLM,
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0},
    )
    try:
        return json.loads(r["message"]["content"])
    except json.JSONDecodeError:
        return {}

def is_relevant(question, chunk):
    out = ask_json(
        f"Question: {question}\n\nPassage: {chunk}\n\n"
        'Does the passage contain information needed to answer the question? '
        'Reply as JSON: {"relevant": true or false}'
    )
    return bool(out.get("relevant", True))

def rewrite(question):
    r = ollama.chat(model=LLM, messages=[{
        "role": "user",
        "content": f"Rewrite this as a short search query for a university course catalog. Output only the query.\n\n{question}",
    }])
    return r["message"]["content"].strip()

def answer(question, use_grader=True):
    codes = find_codes(question)
    query = question
    for attempt in range(2):
        hits = search(query, "courses", 5) + search(query, "policies", 3)
        good = [h for h in hits if not use_grader or is_relevant(question, h["text"])]
        if len(good) >= 2 or attempt == 1 or not use_grader:
            break
        query = rewrite(question)

    if not codes:  # no code typed: fall back to the best matching course
        top = next((h for h in good if h["meta"].get("code")), None)
        if top:
            codes = [top["meta"]["code"]]

    facts = graph_facts(codes)
    typed = question.upper().replace(" ", "")
    shorthand = [c for c in codes if c in courses and c not in typed]
    if shorthand:
        named = "; ".join(f"{c} ({courses[c]['title']})" for c in shorthand)
        facts.insert(0, f"(Interpreting the question as: {named})")

    # exact calendar wording, straight from the data (never reworded by the model)
    calendar = [
        {
            "code": c,
            "title": courses[c]["title"],
            "prereq_text": courses[c]["prereq_text"] or "None listed",
            "exclusions": courses[c]["exclusions"],
            "source": courses[c]["source"],
        }
        for c in codes
        if c in courses
    ]

    context = "\n".join(facts + [h["text"] for h in good])
    if not context:
        return {
            "answer": "I couldn't find that in the catalog.",
            "grounded": True,
            "sources": [],
            "facts": [],
            "calendar": [],
            "rewritten_query": None,
        }

    prompt = (
        "Answer using ONLY the context below. Cite course codes. "
        "The question may use shorthand for a course (for example 'b07' or 'cs 2'); "
        "if the context says how the question was interpreted, use that. "
        "In calendar prerequisite wording, items joined by 'or' are alternatives (only one is needed), "
        "and square brackets group them; never present alternatives as a list of separate requirements. "
        "An exact copy of the calendar wording is shown to the student below your answer, "
        "so keep any prerequisite summary short. "
        "If the context doesn't contain the answer, say so.\n\n"
        f"Context:\n{context}\n\nQuestion: {question}"
    )
    ans = ollama.chat(model=LLM, messages=[{"role": "user", "content": prompt}])["message"]["content"]

    check = ask_json(
        f"Context:\n{context}\n\nAnswer:\n{ans}\n\n"
        'Is every claim in the answer supported by the context? Reply as JSON: {"grounded": true or false}'
    )
    return {
        "answer": ans,
        "grounded": bool(check.get("grounded", True)),
        "sources": good,
        "facts": facts,
        "calendar": calendar,
        "rewritten_query": query if query != question else None,
    }