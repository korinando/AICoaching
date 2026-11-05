"""The scoring rubric, as data: changing what a score means doesn't touch the prompt, and Week 6 can
compare versions. Written for me at my request, so I must be able to defend every line."""

# Change this whenever a meaning changes, so Week 6's results say which rubric they measured.
RUBRIC_VERSION = "v1"

# Every level is described: with only 1, 3 and 5, the judge has to guess what a 2 or a 4 means.
# The keys must match CriterionScores in schemas.py.
RUBRIC: dict[str, dict[str, str]] = {
    "technical_accuracy": {
        "1": "Wrong, or no attempt at the concept. No correct claim to give credit for.",
        "2": "A related idea, but a key part is wrong or missing, so it wouldn't work in practice.",
        "3": "Mostly correct: the main idea is right, with minor gaps or a small mistake.",
        "4": "Correct and complete for this level, with no meaningful mistake.",
        "5": "Correct and precise, and also says when or why, such as a trade-off or a limit.",
    },
    "clarity": {
        "1": "The point can't be worked out, even after allowing for transcription errors.",
        "2": "The point can be guessed, but it's mostly lost in repetition or wandering.",
        "3": "Understandable, but unfocused in places or longer than it needs to be.",
        "4": "Easy to follow, with the point coming through quickly.",
        "5": "Clear and concise: every part helps, and it answers what was actually asked.",
    },
    "structure": {
        "1": "No order at all, or it doesn't address the question.",
        "2": "Some relevant pieces, in an order that makes the listener do the work.",
        "3": "A partial structure, such as a definition but no example, or a story with no result.",
        "4": "A clear order, such as definition, then how it works, then an example.",
        "5": (
            "A complete structure for the question type. Technical: point, explanation, example. "
            "Behavioural: Situation, Task, Action and Result."
        ),
    },
    "depth": {
        "1": "Only repeats the question's words, or gives no content.",
        "2": "A surface-level statement, with no reason or example.",
        "3": "Some reasoning or a general example.",
        "4": "A concrete example or a real reason, specific to the situation.",
        "5": "A concrete example with reasoning and reflection, such as what they'd do differently.",
    },
}
