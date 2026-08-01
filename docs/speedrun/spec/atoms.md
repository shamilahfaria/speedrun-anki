# Spec atoms — Friday early submission

Scope is the Friday bar only: Brainlift v1, working Rust change, review loop,
desktop installer, syncing phone companion, basic AI integration. The Sunday
evidence layer (calibration, ablation, paraphrase/leakage/crash suites) is
deliberately out of scope here and gets its own atoms.

Each atom states the check that decides it. A check is a command or an
observation someone other than the builder can perform.

### A1 · Rust engine measures memory, performance and readiness separately
New `TransferService` in `rslib`, reachable from Python and from the iOS FFI,
returning three intervals plus an explicit refusal when evidence is thin.

CHECK: `cargo test -p anki --lib transfer::` passes with >= 3 tests, and
`pytest tests/test_transfer.py` passes, exercising the Rust function through the
protobuf boundary rather than reimplementing it.
STATUS: DONE — 10 Rust unit tests, 4 Python integration tests, commit a84fb5e.

### A2 · Adding our service does not renumber existing protobuf services
The iOS client hardcodes service indices; renumbering silently breaks it.

CHECK: in generated `backend.rs`, the backend dispatch table still maps sync=1,
collection=3, scheduler=13, stats=41, tags=43, and `transfer` appears at a
higher index than every upstream service.
STATUS: DONE — verified, transfer=45, no existing index moved.

### A3 · Desktop surface shows the three scores, and shows refusals as refusals
A reachable view in the desktop client displaying memory, performance and
readiness per topic with their intervals. When the engine refuses to score, the
surface must show the refusal and what is missing — never a zero, never a blank
that reads as a low score.

CHECK: launch the desktop client against a collection with thin evidence and
observe a stated refusal naming the shortfall; then against sufficient evidence
and observe three distinct numbers each with an interval. Both observed by
someone who did not write the view.

### A4 · iOS companion builds against our engine, not upstream Anki
The iOS fork's engine submodule points at our fork and our branch, and its
service catalog knows `transfer`.

CHECK: `git config -f .gitmodules submodule.anki-upstream.url` names our fork;
the pinned submodule commit is an ancestor of our `speedrun` branch; and the
Swift service catalog contains a transfer entry whose index equals the index in
the generated Rust dispatch table.
NOTE: compiling this requires Xcode, which is not installed. If the build cannot
run, the honest status is "source-complete, unbuilt" — not "done".

### A5 · AI generates cards traceable to a named source, and is optional
Card generation from supplied source material, where every generated card
records which source and which passage it came from. A keyword-retrieval
baseline exists to compare against. The product must run fully with AI disabled.

CHECK: generate cards from a fixture source and assert every card carries a
non-empty source identifier and locator; run the same generation with the
provider disabled and assert the rest of the system still functions; and produce
a comparison of retrieval quality against the keyword baseline on a fixed set of
queries with a stated data cutoff.

### A6 · Desktop installer exists and installs on a machine that never built it
CHECK: a build artifact is produced, and installing it on a machine without the
source tree yields a launchable client reporting our version string.

### A7 · Brainlift v1
Written record of the thesis, the evidence behind it, the spiky points, and what
would falsify it.

CHECK: document exists, states at least one claim that could be proven wrong by
the Sunday ablation test, and every factual claim carries a citation that
`scripts/check-sources.sh` reports as reachable.
