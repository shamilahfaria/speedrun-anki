# Speedrun addition.
#
# One command for the Section 10 performance targets:
#
#     make bench
#
# It builds pylib if needed, builds the 50,000-card deck if it is not already
# there, then measures every target and prints one table. Exits non-zero if any
# measured target misses its budget. Targets that cannot be measured in this
# environment print SKIPPED with a reason and are never given a number.

SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c

REPO       := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
TOOLCHAIN  := /opt/homebrew/opt/rustup/bin:/opt/homebrew/bin
PYTHON     := $(REPO)/out/pyenv/bin/python
PYLIB_OUT  := $(REPO)/out/pylib
DECK       := $(REPO)/out/bench/speedrun-50k.anki2

CARDS            ?= 50000
REVIEWS_PER_CARD ?= 8
REVIEWS          ?= 200
REFRESHES        ?= 12
COLD_RUNS        ?= 5
BENCH_ARGS       ?=

# Everything that touches the built library needs these two.
RUN := PATH="$(TOOLCHAIN):$$PATH" PYTHONPATH="$(PYLIB_OUT)" $(PYTHON)

.PHONY: bench bench-quick bench-json deck leakage test-bench clean-bench help

help:
	@echo "make bench      - all Section 10 targets on the 50k deck (builds it if needed)"
	@echo "make bench-json - the same run, as JSON"
	@echo "make bench-quick- a 5k-card smoke run, for checking the harness itself"
	@echo "make deck       - build the 50k benchmark deck only"
	@echo "make leakage    - eval-set vs. corpus leakage check"
	@echo "make test-bench - unit tests for the harness and the leakage check"
	@echo "make ablation   - Section 9 ablation test: full vs feature-off vs plain Anki"
	@echo "make ablation-quick - the three arms without the parameter sweep"
	@echo "make test-ablation  - unit tests for the ablation harness"
	@echo "make clean-bench- delete the built deck"

# pylib is the thing under test; ninja no-ops when it is already current.
$(PYLIB_OUT):
	cd $(REPO) && PATH="$(TOOLCHAIN):$$PATH" ./ninja pylib

pylib: $(PYLIB_OUT)
.PHONY: pylib

$(DECK): | $(PYLIB_OUT)
	@echo "==> building the $(CARDS)-card benchmark deck (one-off, reused later)"
	cd $(REPO) && $(RUN) tools/bench_all.py \
		--collection "$(DECK)" --cards $(CARDS) \
		--reviews-per-card $(REVIEWS_PER_CARD) --build-only

deck: $(DECK)

bench: $(DECK)
	cd $(REPO) && $(RUN) tools/bench_all.py \
		--collection "$(DECK)" --cards $(CARDS) \
		--reviews-per-card $(REVIEWS_PER_CARD) \
		--reviews $(REVIEWS) --refreshes $(REFRESHES) --cold-runs $(COLD_RUNS) \
		$(BENCH_ARGS)

bench-json: $(DECK)
	cd $(REPO) && $(RUN) tools/bench_all.py \
		--collection "$(DECK)" --cards $(CARDS) \
		--reviews-per-card $(REVIEWS_PER_CARD) \
		--reviews $(REVIEWS) --refreshes $(REFRESHES) --cold-runs $(COLD_RUNS) \
		--json $(BENCH_ARGS)

bench-quick: | $(PYLIB_OUT)
	cd $(REPO) && $(RUN) tools/bench_all.py \
		--collection "$(REPO)/out/bench/speedrun-5k.anki2" --cards 5000 \
		--reviews 50 --refreshes 5 --cold-runs 2 $(BENCH_ARGS)

leakage:
	cd $(REPO) && $(PYTHON) -m speedrun_ai.leakage_check

test-bench:
	cd $(REPO) && $(RUN) -m pytest tools/tests/test_bench_all.py \
		speedrun_ai/tests/test_leakage_check.py -q

clean-bench:
	rm -f "$(DECK)" "$(DECK)-wal" "$(DECK)-journal" \
		"$(REPO)/out/bench/speedrun-5k.anki2"

# --- Section 9: the ablation test -------------------------------------------
#
# Appended below the Section 10 bench targets. Touches none of them: the
# ablation is pure Python over checked-in fixtures and never opens a collection,
# so it needs neither the built pylib nor the 50k deck.

ABL_LEARNERS ?= 120
ABL_REVIEWS  ?= 3000
ABL_SEED     ?= 20260803
ABL_ARGS     ?=

# No PYTHONPATH to out/pylib on purpose -- this harness must not be able to
# reach the real collection layer, so it cannot accidentally depend on one.
RUN_ABL := PATH="$(TOOLCHAIN):$$PATH" $(PYTHON)

.PHONY: ablation ablation-sweep ablation-json test-ablation

ablation:
	cd $(REPO) && $(RUN_ABL) tools/ablation.py \
		--learners $(ABL_LEARNERS) --reviews $(ABL_REVIEWS) --seed $(ABL_SEED) \
		--sweep $(ABL_ARGS)

# The three arms only, without the parameter sweep.
ablation-quick:
	cd $(REPO) && $(RUN_ABL) tools/ablation.py \
		--learners $(ABL_LEARNERS) --reviews $(ABL_REVIEWS) --seed $(ABL_SEED) \
		$(ABL_ARGS)
.PHONY: ablation-quick

ablation-json:
	cd $(REPO) && $(RUN_ABL) tools/ablation.py \
		--learners $(ABL_LEARNERS) --reviews $(ABL_REVIEWS) --seed $(ABL_SEED) \
		--sweep --json $(ABL_ARGS)

test-ablation:
	cd $(REPO) && PYTHONPATH="$(REPO)/tools" $(RUN_ABL) -m pytest \
		tools/tests/test_ablation.py -q
