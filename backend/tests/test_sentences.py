import pytest

from app.speech.sentences import split_sentences


@pytest.mark.parametrize(
    ("pieces", "sentences"),
    [
        (
            ["Let's move on to Databases. What is an index?"],
            ["Let's move on to Databases.", "What is an index?"],
        ),
        (
            ["Let's move on to Data", "bases. Wh", "at is an index?"],
            ["Let's move on to Databases.", "What is an index?"],
        ),
        (
            ["We use Node.", "js and it works fine. Right?"],
            ["We use Node.js and it works fine.", "Right?"],
        ),
        (["Version 3.5 is out today. Why?"], ["Version 3.5 is out today.", "Why?"]),
        (
            ["Use a tool, e.g. Redis, for the cache. Why?"],
            ["Use a tool, e.g. Redis, for the cache.", "Why?"],
        ),
        (
            ["Thanks. Let's move on to Git now. What is a branch?"],
            ["Thanks. Let's move on to Git now.", "What is a branch?"],
        ),
        (["What is an index?"], ["What is an index?"]),
        (["What is an index"], ["What is an index"]),
        (
            ["First sentence here.\nSecond sentence here."],
            ["First sentence here.", "Second sentence here."],
        ),
        (
            ["Well, let me think... Can you say more?"],
            ["Well, let me think...", "Can you say more?"],
        ),
        (
            ["This is sentence one. This is sentence two. This is sentence three."],
            ["This is sentence one.", "This is sentence two.", "This is sentence three."],
        ),
        (
            ["We are now using Node.", "js in this project. Why?"],
            ["We are now using Node.js in this project.", "Why?"],
        ),
        ([], []),
    ],
)
def test_split_sentences(pieces, sentences):
    assert list(split_sentences(pieces)) == sentences
