#!/usr/bin/env bash
# instrument: retrieval
# draughtsman's own SessionStart briefing. Runs ALONGSIDE the vendored generic hook
# (.claude/hooks/session-start.sh) as a separate entry in .claude/settings.json, which
# is bugarach's pattern: the generic core carries a vendoring stamp and must stay
# byte-identical so it can be re-copied, so repo-specific facts are layered, never
# patched in.
#
# IT RUNS FIRST, AND THAT IS THE WHOLE DESIGN. bugarach's session_briefing.sh emitted
# 17,568 bytes on 2026-08-25 and the harness spilled it to a file, injecting a ~2KB
# preview that ended mid-sentence at line 27. Everything after that reached nobody and
# nothing said so -- the replacement for "CLAUDE.md is ignored" failed the same way
# CLAUDE.md did. The generic hook costs ~1,400 bytes here, so this one is kept small and
# ordered ahead of it: if anything is truncated it must be the generic tail (worktree
# list, recent commits), never the rules. The selftest ASSERTS this hook's own size.
#
# THE COMBINED TOTAL IS NOT SOMETHING THIS FILE CAN HOLD. The generic tail grows with
# worktrees and commits -- 1388 bytes at two worktrees, 1461 at four within the hour -- and
# it is vendored byte-identical on purpose. So this hook asserts only what it controls: it
# is bounded under 800 bytes and it runs first, which puts the payload inside the preview
# whatever the generic hook does. The tail belongs behind a flag upstream in interface2.
#
# WHY IT CORRECTS THE HOOK IT SHIPS WITH. The generic core hardcodes
# `board="<repo>-worktrees/SESSIONS.md"` and points at `docs/session_protocol.md`.
# draughtsman has neither: its board is CLAIMS.md, in-repo, checked by
# tests/test_claims.py. Left alone the briefing invites a session to create a second
# board -- a hand-maintained pointer going stale, in the repository whose entire subject
# is hand-maintained pointers going stale. The core is not configurable for this (no env
# var reaches its line 79), so the correction is stated here rather than forked in there.
#
# THE FENCED ROW IS DOCUMENTATION, NOT A CLAIM. CLAIMS.md carries a worked example
# inside a ``` block for the next session to copy. The first version of this hook
# reported it as live -- `draughtsman-e9 on name-every-axis`, a session that no longer
# exists and a branch that landed days ago. tests/test_claims.py's own parser skips
# fenced blocks and says why; this one had to learn it separately, which is the argument
# for one parser that both read. Filed as such rather than fixed twice.
#
# READS ONLY LOCAL REFS. No fetch, no network: this is on the blocking path to session
# start and the SDK aborts the whole handshake at 60s. `origin/main` is therefore as
# fresh as the last fetch, which the output says.
#
# EXIT 0 always, like every hook in this estate. Fail open: a briefing that blocks a
# session is worse than one that is missing.
#   .claude/hooks/draughtsman-briefing.sh --selftest   to check it still fires.

set +e

root=$(git rev-parse --show-toplevel 2>/dev/null)
[ -z "$root" ] && exit 0

# The board as ORIGIN/MAIN has it. CLAIMS.md rule 2: a branch's copy is one nobody else
# can read, so the working tree's version is the wrong thing to brief from.
rows=""
age=""
claims=$(git -C "$root" show origin/main:CLAIMS.md 2>/dev/null)
if [ -n "$claims" ]; then
    rows=$(printf '%s\n' "$claims" \
        | sed -n '/## Open claims/,/## Queue/p' \
        | awk '
            /^```/      { fenced = !fenced; next }     # documentation, not data
            fenced      { next }
            /^\| `/ {
                gsub(/`/, "", $0)
                n = split($0, c, "|")
                if (n < 6) next
                for (i = 2; i <= 3; i++) gsub(/^ +| +$/, "", c[i])
                gsub(/^ +| +$/, "", c[6])
                if (length(c[6]) > 30) c[6] = substr(c[6], 1, 29) "~"
                shown++
                if (shown <= 3) printf "   %s on %s -- %s\n", c[2], c[3], c[6]
            }
            END { if (shown > 3) printf "   +%d more -- see CLAIMS.md\n", shown - 3 }' )
    age=$(git -C "$root" log -1 --format=%cr origin/main 2>/dev/null)
fi

echo "===== draughtsman: THE FACTS THAT BIND ====="
echo "Board = CLAIMS.md on origin/main (tests/test_claims.py). The"
echo "SESSIONS.md and docs/session_protocol.md named below do not exist."
if [ -n "$rows" ]; then
    echo "OPEN CLAIMS (origin/main, ${age:-unknown}):"
    printf '%s\n' "$rows"
else
    echo "OPEN CLAIMS: none (origin/main, ${age:-unknown})."
fi
echo "NO pytest here, ever; the suite runs in CI:"
echo "   gh run list --branch <branch> --limit 3"
echo "An empty search is not absence: python3 tools/dragnet.py TERM"
echo "RULES: own worktree; claim before writing, land the row on main"
echo "FIRST; rows name paths; release in the commit BEFORE landing."
echo "============================================"

# ------------------------------------------------------------------- selftest
#
# GUARDED ON $0 rather than on $1 alone: short-course's session_identity.sh was
# sourced by a hook invoked as `hook --selftest` and ran the LIBRARY's selftest,
# printing PASS having tested nothing it owned.
case "$0" in
  *draughtsman-briefing.sh) : ;;
  *) return 0 2>/dev/null || exit 0 ;;
esac
if [ "${1:-}" = "--selftest" ]; then
    fail=0
    # ABSOLUTE, because two checks below re-invoke this script from another
    # directory. With a relative $0 they died 127 and the failure looked like the
    # hook's, not the test's.
    self=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
    t() { if [ "$2" = "1" ]; then printf '  ok   %s\n' "$1"
          else printf '  FAIL %s\n' "$1"; fail=1; fi; }

    out=$("$self" 2>/dev/null)

    # ASSERT THE CONTENT, NOT THE SHAPE. A selftest checking only that the hook
    # printed something passes on a hook that prints a banner and nothing else --
    # the failure mode that matters here, because this file exists to deliver four
    # specific facts and a banner delivers none of them.
    case "$out" in *"CLAIMS.md on origin/main"*) t "names the real board" 1;;
                   *) t "names the real board" 0;; esac
    case "$out" in *"SESSIONS.md and docs/session_protocol.md named below do not exist"*) t "corrects the generic board pointer" 1;;
                   *) t "corrects the generic board pointer" 0;; esac
    case "$out" in *"NO pytest"*) t "says the suite runs in CI, not here" 1;;
                   *) t "says the suite runs in CI, not here" 0;; esac
    case "$out" in *"dragnet.py"*) t "names the tool that refuses absence" 1;;
                   *) t "names the tool that refuses absence" 0;; esac
    case "$out" in *"OPEN CLAIMS"*) t "reports the board" 1;;
                   *) t "reports the board" 0;; esac

    # THE FENCED WORKED EXAMPLE MUST NOT BE REPORTED AS A LIVE CLAIM. Named by its
    # branch, because that is what the example row carries and no real row will:
    # `name-every-axis` landed on 2026-09-02 and its session is gone.
    case "$out" in *"name-every-axis"*)
            t "fenced example read as a live claim" 0;;
        *)  t "skips the fenced worked example" 1;; esac

    # THE SIZE BUDGET IS THE POINT OF THE ORDERING, so it is asserted rather than
    # intended. 2000 bytes is the harness preview that truncated bugarach's
    # briefing on 2026-08-25.
    #
    # IT ASSERTS THIS HOOK'S SIZE, AND REPORTS THE COMBINED TOTAL WITHOUT
    # ASSERTING IT. Both numbers were tried. The combined one is the quantity that
    # actually matters -- it is what the session receives -- but it is not a
    # quantity this file can hold: the generic hook's tail grows with every
    # worktree and every commit (1388 bytes at 2 worktrees, 1461 at 4 within the
    # hour), and it is vendored byte-identical on purpose, so the only lever is
    # upstream in interface2. A check whose failure names no action its owner can
    # take is one the next session learns to skip past.
    #
    # WHAT THIS FILE CAN GUARANTEE, and therefore what is asserted: it is bounded
    # by construction (at most three claim rows, each clipped) and it runs FIRST.
    # Between them the payload lands inside the first 2000 bytes no matter what
    # the generic hook does, which is the whole reason for the ordering. 800 is
    # 2000 less the generic hook's own header and alarms (~1200), leaving its tail
    # -- worktree list, recent commits -- as the designated casualty.
    n=$(printf '%s' "$out" | wc -c | tr -d ' ')
    if [ "$n" -le 800 ]; then t "bounded: $n bytes of the 2000-byte preview" 1
    else t "OVER 800 bytes at $n -- clip the claim rows, not the rules" 0; fi

    gen=0
    [ -f "$(dirname "$self")/session-start.sh" ] && \
      gen=$(IF2_HOOK_STATE=$(mktemp -u) bash "$(dirname "$self")/session-start.sh" \
            2>/dev/null | wc -c | tr -d ' ')
    tot=$(( n + gen ))
    printf '  note combined injection %s + %s = %s bytes' "$n" "$gen" "$tot"
    [ "$tot" -gt 2000 ] && printf ' -- OVER 2000, the generic TAIL is what is lost'
    printf '\n'

    # Fail-open: outside a git repo it must exit 0 and say nothing, not error.
    o=$(cd / && "$self" 2>&1); rc=$?
    if [ "$rc" = "0" ] && [ -z "$o" ]; then t "outside a repo: silent, exit 0" 1
    else t "outside a repo: rc=$rc output='$o'" 0; fi

    [ $fail -eq 0 ] && { echo "PASS"; exit 0; } || { echo "FAIL"; exit 1; }
fi
