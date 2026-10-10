#!/usr/bin/env bash
# Apply branch protection to `main` with the GitHub CLI.
#
#   bash tools/protect_main.sh              # recommended defaults for a solo maintainer
#   REQUIRED_REVIEWS=1 ENFORCE_ADMINS=true bash tools/protect_main.sh   # team settings
#
# Requires: gh auth login (with admin rights on the repository).
#
# Settings (environment variables):
#   REPO               owner/name                    (default: jordanbrais1-hub/mdConverter)
#   REQUIRED_REVIEWS   approvals needed to merge     (default: 1)
#   ENFORCE_ADMINS     apply rules to admins too     (default: false)
#                      With a single maintainer, "true" plus REQUIRED_REVIEWS>=1 means
#                      nothing can ever be merged (GitHub does not let you approve your
#                      own PR). Keep "false" until a second maintainer joins.
#   REQUIRE_SIGNED     require signed commits        (default: false)
#                      Turn on only after setting up commit signing locally, e.g.:
#                        git config --global gpg.format ssh
#                        git config --global user.signingkey ~/.ssh/id_ed25519.pub
#                        git config --global commit.gpgsign true
#                      and adding the key on GitHub as a *Signing key*.
set -euo pipefail

REPO="${REPO:-jordanbrais1-hub/mdConverter}"
REQUIRED_REVIEWS="${REQUIRED_REVIEWS:-1}"
ENFORCE_ADMINS="${ENFORCE_ADMINS:-false}"
REQUIRE_SIGNED="${REQUIRE_SIGNED:-false}"

# Exact check names produced by .github/workflows/ci.yml and security.yml.
CHECKS='[
  {"context": "test (windows-latest, 3.11)"},
  {"context": "test (windows-latest, 3.12)"},
  {"context": "test (windows-latest, 3.13)"},
  {"context": "test (ubuntu-latest, 3.11)"},
  {"context": "test (ubuntu-latest, 3.12)"},
  {"context": "test (ubuntu-latest, 3.13)"},
  {"context": "build-windows"},
  {"context": "Dependency audit (pip-audit)"},
  {"context": "SAST (Bandit)"},
  {"context": "SAST (CodeQL) (python)"},
  {"context": "SAST (CodeQL) (actions)"},
  {"context": "Secret scan (gitleaks, full history)"},
  {"context": "Dependency review (PRs)"}
]'

echo "Protecting main on $REPO (reviews=$REQUIRED_REVIEWS, enforce_admins=$ENFORCE_ADMINS, signed=$REQUIRE_SIGNED)"

gh api -X PUT "repos/$REPO/branches/main/protection" \
  -H "Accept: application/vnd.github+json" --input - <<EOF
{
  "required_status_checks": { "strict": true, "checks": $CHECKS },
  "enforce_admins": $ENFORCE_ADMINS,
  "required_pull_request_reviews": {
    "required_approving_review_count": $REQUIRED_REVIEWS,
    "require_code_owner_reviews": true,
    "dismiss_stale_reviews": true,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true,
  "block_creations": false,
  "lock_branch": false
}
EOF

if [ "$REQUIRE_SIGNED" = "true" ]; then
  gh api -X POST "repos/$REPO/branches/main/protection/required_signatures" >/dev/null
  echo "Signed commits required."
else
  gh api -X DELETE "repos/$REPO/branches/main/protection/required_signatures" >/dev/null 2>&1 || true
fi

# Repository-level merge settings that complement linear history.
gh api -X PATCH "repos/$REPO" >/dev/null --input - <<'EOF'
{
  "allow_merge_commit": false,
  "allow_squash_merge": true,
  "allow_rebase_merge": true,
  "delete_branch_on_merge": true,
  "allow_auto_merge": true
}
EOF

echo "Done. Current protection:"
gh api "repos/$REPO/branches/main/protection" --jq '{
  checks: [.required_status_checks.checks[].context],
  strict: .required_status_checks.strict,
  reviews: .required_pull_request_reviews.required_approving_review_count,
  code_owners: .required_pull_request_reviews.require_code_owner_reviews,
  enforce_admins: .enforce_admins.enabled,
  linear_history: .required_linear_history.enabled,
  force_pushes: .allow_force_pushes.enabled,
  deletions: .allow_deletions.enabled,
  signed_commits: .required_signatures.enabled
}'
