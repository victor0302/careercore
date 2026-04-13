#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <issue-number> [repo]"
  echo "Example: $0 6"
  echo "Example: $0 6 victor0302/careercore"
  exit 1
fi

ISSUE_NUMBER="$1"
REPO="${2:-victor0302/careercore}"
WORKDIR="$(cd "$(dirname "$0")" && pwd)"

PROMPT=$(cat <<EOF
Work issue #$ISSUE_NUMBER in repo $REPO end to end.

First inspect the GitHub issue and current codebase.

Follow this workflow exactly:
1. Assign the issue to victor0302 if unassigned.
2. Move its GitHub Project item to In Progress if it exists.
3. Branch from main using a descriptive issue-based branch name.
4. Implement only the scope of that issue with good coding practices.
5. Avoid unrelated changes and do not revert user changes.
6. Run the best available checks/tests.
7. Commit with a clear message.
8. Push the branch.
9. Open a PR against main that links the issue with Closes #$ISSUE_NUMBER.
10. Summarize verification gaps honestly.

Do not merge the PR.
EOF
)

exec codex exec --full-auto -C "$WORKDIR" "$PROMPT"
