#!/bin/bash

set -euo pipefail

workflow="${1:-.github/workflows/verl-e2e-weekly.yml}"

if grep -qE 'verl_ref|VERL_REF' "$workflow"; then
  echo "verl workflow accepts a mutable external ref" >&2
  exit 1
fi

test "$(grep -Ec '^      VERL_COMMIT: [0-9a-f]{40}$' "$workflow")" = 1
grep -Fq 'git -C /workspace/verl fetch --depth 1 origin "$VERL_COMMIT"' "$workflow"
grep -Fq 'git -C /workspace/verl checkout --detach FETCH_HEAD' "$workflow"
grep -Fq 'test "$(git -C /workspace/verl rev-parse HEAD)" = "$VERL_COMMIT"' "$workflow"

if grep -Fq 'git clone https://github.com/verl-project/verl.git' "$workflow"; then
  echo "verl workflow clones and executes an unverified external default branch" >&2
  exit 1
fi
