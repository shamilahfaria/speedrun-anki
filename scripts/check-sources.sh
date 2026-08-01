#!/usr/bin/env bash
# Verify that every URL cited in a document actually resolves.
#
# This closes half of the gap in Gate 1's `grep -c 'https?://'`, which counts
# citations without visiting them -- a fabricated URL passes that check.
#
# What this proves: the URL exists and a server answered for it.
# What this does NOT prove: that the page says what the document claims it says.
# That is a judgement call and belongs to a human or a restricted verifier, not
# to a status code. A live URL under a false claim still passes this script.
#
# Usage: scripts/check-sources.sh problem-statement.md
set -uo pipefail

DOC="${1:-problem-statement.md}"
UA='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'

if [[ ! -f "$DOC" ]]; then
  echo "no such document: $DOC" >&2
  exit 2
fi

# Pull URLs out of <angle brackets> and bare text, strip trailing punctuation.
# Deliberately avoids `mapfile`, which needs bash 4 -- macOS ships bash 3.2, and
# a check that only runs on the author's machine is not a check.
URLS=$(grep -oE 'https?://[^ )>"]+' "$DOC" | sed 's/[.,]$//' | sort -u)

if [[ -z "$URLS" ]]; then
  echo "no URLs found in $DOC" >&2
  exit 2
fi

echo "Checking $(printf '%s\n' "$URLS" | wc -l | tr -d ' ') unique source URLs from $DOC"
echo

ok=0; blocked=0; dead=0

while IFS= read -r url; do
  [[ -z "$url" ]] && continue
  # -L follows redirects; some hosts reject HEAD, so fall back to a ranged GET.
  code=$(curl -sSL -o /dev/null -w '%{http_code}' --max-time 25 \
           -A "$UA" -r 0-0 "$url" 2>/dev/null || echo "000")

  case "$code" in
    2*|206)
      printf '  OK       %s  %s\n' "$code" "$url"; ((ok++)) ;;
    401|403|429)
      # Bot protection. The URL is real; this environment just is not allowed in.
      # Distinguished from dead deliberately -- treating these as failures would
      # push you toward citing whatever is easiest to scrape, not what is true.
      printf '  BLOCKED  %s  %s\n' "$code" "$url"; ((blocked++)) ;;
    *)
      printf '  DEAD     %s  %s\n' "$code" "$url"; ((dead++)) ;;
  esac
done <<< "$URLS"

echo
echo "reachable: $ok   bot-blocked: $blocked   unreachable: $dead"
echo
if [[ $dead -gt 0 ]]; then
  echo "FAIL: $dead source(s) did not resolve. A citation nobody can open is not a citation."
  exit 1
fi
echo "PASS: every cited URL resolved or was bot-blocked (none dead)."
echo "Reminder: this proves the pages exist, not that they support the claims."
