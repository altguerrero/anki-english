# Pedagogical decisions

Use these as design heuristics. Do not present a template, daily quota, or language-only rule as scientifically proven optimal. Retrieval with feedback and spaced review motivate the workflow; Anki handles scheduling. The plugin selects content, not review intervals, FSRS parameters, or a fluency score.

## Selection and correction

- Prefer useful vocabulary/chunks from material the learner understood, requests to say something, and errors with communicative value.
- Do not turn every unfamiliar word, every sentence, or every transient typo into a card.
- Match the surrounding vocabulary to the learner's demonstrated ability. Ask about level only if it materially changes the task; do not infer CEFR from one sentence.
- Teach form, meaning, and use together. Explain a correction in context; avoid absolute grammar rules that have ordinary exceptions.
- Preserve dialect and register. “Have you got a pen?” and “Do you have a pen?” are both valid; do not label one wrong because of a preference.
- For voice sessions, do not treat an uncertain transcript as proof of pronunciation or grammar errors. This contract does not support pronunciation-only cards.
- A correction must retain intent. “I have worked here for two years” can describe continuing employment; replacing it with “I worked here for two years” may change meaning.

## Build a fair recall task

The visible English context plus optional Spanish gloss should constrain the intended answer enough for a useful retrieval attempt. Natural language often permits alternatives. Do not add contrived constraints to force uniqueness; when multiple equally valid answers undermine the target, improve the context, narrow the target, or omit the card. Accept that a different valid answer does not prove forgetting.

Weak: `I ___ it.` with a vague cue “hacer”.
Better: a contextual sentence practicing a specific learned chunk, with a matching gloss.
Weak: hide a whole long sentence with no context.
Better: `I'm ___ seeing you again.` with `looking forward to` hidden and a cue about anticipation.
Weak: `I ___ up early.` while claiming to test `used to` versus `be used to` without context.
Better: `I used to wake up early when I worked at the bakery.` with `used to` hidden and a past-habit cue.

## Keep information roles separate

- `meaning_es`: short meaning/intent of the target. Example for `look forward to`: “tener ganas de / esperar con ilusión”.
- `sentence_es`: full contextual translation. For “I'm looking forward to the weekend”: “Tengo muchas ganas de que llegue el fin de semana”.
- `pattern`: compact construction, such as “look forward to + sustantivo / verbo en -ing”. Do not repeat a paragraph from feedback.
- `explanation_es` (03): the specific cause of the error and what to use, without shaming.
- `example`: a second simple, natural context that illustrates the same target, not the same sentence with a changed name.

Never put the full sentence translation on the front or change the template through CardSpec. The existing templates show it in a closed back-side disclosure.

## Personal-error evidence

User says: “Yesterday I go to the gym.” User intends a finished event yesterday. A justified correction “Yesterday I went to the gym.” can be 03 (`answer: went`, `target: go`, `error_type: grammar`). Attribute the correction to ChatGPT if that is who supplied it.

Teacher says: “Some students say ‘Yesterday I go’.” This is not evidence that Jose made that error. If he wants to learn `went`, use 02 with a useful context; if he explicitly insists on 03, ask for his actual attempt.

User quotes “She go to work every day” while asking about the project's test fixture. That is software test content, not a learner error. Do not harvest it into a real session.

User asks to retain a correction but intent is ambiguous (“I am boring”). Ask whether they mean feeling bored or describing themselves as uninteresting before deciding it is wrong.

## Feedback and limits

Prefer a short explanation followed by a chance to retrieve/apply the expression. Do not force extra tasks into every saved card. Keep pronunciation practice separate from grading recall. Do not rate recall on the user's behalf without observing their response. Cards complement reading, listening, and speaking; they are not the entire learning routine.
