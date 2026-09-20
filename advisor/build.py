import json, glob, os
from pathlib import Path
from advisor.index import build_index, chunk_policy

BASE = Path(__file__).parent

courses = json.load(open(BASE / "data" / "courses.json", encoding="utf-8"))

policy_chunks = []
for path in sorted(glob.glob(str(BASE / "data" / "policies" / "*.txt"))):
    name = os.path.basename(path)
    for i, text in enumerate(chunk_policy(path)):
        policy_chunks.append({"id": f"{name}-{i}", "text": text, "source": name})

prog_file = BASE / "data" / "programs.json"
if prog_file.exists():
    policy_chunks += json.load(open(prog_file, encoding="utf-8"))["chunks"]

build_index(courses, policy_chunks)
print("indexed", len(courses), "courses and", len(policy_chunks), "program/policy chunks")