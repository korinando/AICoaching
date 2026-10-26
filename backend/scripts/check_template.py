from app.agent.templates import load_templates, new_state

# 1. Both templates load
print("Template ids:", list(load_templates().keys()))

# 2. A new state looks right
state = new_state("junior_backend")
print("New state:", state.model_dump_json())

# 3. A bad id gives a clear error
try:
    new_state("does_not_exist")
except ValueError as e:
    print("Good error:", e)

# 4. Two states do not share the same topics list
a = new_state("junior_backend")
b = new_state("junior_backend")
a.planned_topics.append("Hacking")
print("b topics (must NOT contain Hacking):", b.planned_topics)
