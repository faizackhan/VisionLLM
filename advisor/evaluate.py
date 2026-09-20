import json
from advisor.rag import answer

qs = json.load(open("eval/questions.json"))
for use_grader in (False, True):
    correct = grounded = 0
    for item in qs:
        r = answer(item["q"], use_grader=use_grader)
        correct += all(code in r["answer"] for code in item["expected_codes"])
        grounded += r["grounded"]
    print(f"grader={use_grader}: correct {correct}/{len(qs)}, grounded {grounded}/{len(qs)}")