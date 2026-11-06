# AI Mock Interview Coach

Practice spoken job interviews with an AI interviewer that asks follow-up questions, then get a scored feedback report.

> Work in progress: Week 6 of 8. You can already sign up, take a spoken interview in the browser, and get a report about a minute after it ends.
> Interview templates: Junior Backend, Junior Frontend, Junior AI Engineer, Junior Data Analyst, and a behavioural (HR) interview.

## Can the feedback be trusted?

An AI judge (Gemini) scores each interview on 4 criteria, 1 to 5: technical accuracy, clarity, structure and depth. To check it, I scored a test set of answers myself **before** running the AI, and then compared its scores with mine.

**Test set:** 20 answers to real interview questions (backend, frontend, AI and behavioural), mixing strong, average and weak answers, plus tricky ones: confident but wrong, correct but rambling, very short, broken English, and misheard by speech-to-text. That gives 80 scores. A further **8 answers (32 scores) were kept aside** and only used once at the end, to check that the chosen prompt wasn't just tuned to the first 20.

### Prompt versions (20 answers, average of 3 runs each)

| Version | Change | Within 1 of me | Exact | Average difference | Same score in all 3 runs |
|---|---|---|---|---|---|
| **v1** | Rubric with every level 1–5 described, examples, then reasoning, then the score | 82.5% | 41.7% | 0.76 | 68.8% |
| v2 | v1 + judge each criterion on its own | 83.3% | 43.9% | 0.73 | 64.5% |
| v3 | v2 + 3 example answers with their scores | 84.2% | 39.6% | 0.77 | 70.0% |
| *Lazy judge* | *Always answers 3* | *65.0%* | *15.0%* | *1.20* | — |

### Confirmation on the 8 held-out answers (3 runs each)

| Version | Within 1 of me | Exact | Average difference | Same score in all 3 runs |
|---|---|---|---|---|
| **v1** | 93.8% | 43.8% | 0.62 | 75.0% |
| v3 | 93.8% | 39.6% | 0.67 | 71.9% |
| *Lazy judge (always 3)* | *81.2%* | *40.6%* | *0.78* | — |

### What I learned from the numbers

- **The judge is useful, but it isn't exact.** It's within 1 point of my score about 4 times in 5, clearly better than a "lazy judge" that always says 3. It gives exactly my score less than half the time, so a single score is a guide, not a verdict.
- **The prompt changes didn't improve it.** v2 and v3 differ from v1 by less than v1 differs from itself between runs (it gives the same score in all 3 runs only about 70% of the time). On the held-out answers, v3 did slightly worse. **The reports keep v1**, the simplest version.
- **Where it disagrees with me:** answers that are correct but rambling (within 1 only 25% of the time) and very short correct answers (it scores them higher than I do). Depth is the hardest criterion: it matches my exact score only 20% of the time.
- **Halo effect:** the AI gives an answer's 4 criteria more similar scores than I do (average gap between an answer's highest and lowest score 1.00 vs my 1.35), so one impression partly sets all 4.
- **Code does what the AI can't be trusted to do:** the overall score is calculated in code, and every example the judge quotes is checked against the transcript before it reaches the report.

Scripts: `backend/scripts/evaluate.py`, `consistency.py` and `version_table.py`. Data and results: [evaluation/](evaluation/).

### The interviewer

I read 5 real interviews against a checklist (one question at a time, follow-ups react to the answer, no feedback or hints, and so on): [evaluation/interviewer_review.md](evaluation/interviewer_review.md). The main problem was that the interviewer sometimes corrected the candidate and hinted at the answer. Replaying the same moments 4 times each, before and after a prompt fix:

| Behaviour | Before | After |
|---|---|---|
| Corrects the candidate after a wrong answer | 2 of 4 | **0 of 4** |
| Hints at the answer in the follow-up | 4 of 4 | 4 of 4, milder: a question, not an explanation |
| Moves on after a reasonable or good answer | 11 of 12 | **12 of 12** |
| Follows up on an unclear answer | not measured | 5 of 6 |

## Local setup (backend)

```bash
cd backend
cp .env.example .env   # then add your API key
uv sync
uv run pytest
```

## Learning log

See [LEARNING_LOG.md](LEARNING_LOG.md).
