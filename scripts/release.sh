#!/usr/bin/env bash
# Usage: scripts/release.sh [major|minor|patch|X.Y.Z]   (default: patch)
#
# Bumps the version, merges to main via admin bypass (no review needed),
# tags the result, and pushes the tag to trigger the PyPI release workflow.

set -euo pipefail

# Require admin/maintainer bypass access
if [[ "$(gh api repos/DinobaseHQ/dinobase/rulesets/14643398 --jq '.current_user_can_bypass')" != "always" ]]; then
    echo "Error: releases require admin or maintainer access." >&2
    exit 1
fi

PYPROJECT="$(git rev-parse --show-toplevel)/pyproject.toml"

current_version() {
    grep '^version = ' "$PYPROJECT" | head -1 | sed 's/version = "\(.*\)"/\1/'
}

bump_version() {
    local current="$1" bump="$2"
    IFS='.' read -r major minor patch <<< "$current"
    case "$bump" in
        major) echo "$((major + 1)).0.0" ;;
        minor) echo "${major}.$((minor + 1)).0" ;;
        patch) echo "${major}.${minor}.$((patch + 1))" ;;
        [0-9]*.[0-9]*.[0-9]*) echo "$bump" ;;
        *) echo "Error: use major, minor, patch, or X.Y.Z" >&2; exit 1 ;;
    esac
}

bump="${1:-patch}"
current="$(current_version)"
new_version="$(bump_version "$current" "$bump")"
tag="v${new_version}"
branch="release/${tag}"

echo "Releasing ${current} → ${new_version}"

# Ensure clean main
git fetch origin main
git checkout main
git pull origin main

# Create release branch
git checkout -b "$branch"

# Bump version
sed -i.bak "s/^version = \"${current}\"/version = \"${new_version}\"/" "$PYPROJECT"
rm "${PYPROJECT}.bak"

git add "$PYPROJECT"
git commit -m "chore: bump version to ${new_version}"
git push origin "$branch"

# Open PR and immediately merge it via admin bypass (skips required review)
pr_url=$(gh pr create \
    --title "chore: release ${tag}" \
    --body "Automated version bump ${current} → ${new_version}." \
    --base main \
    --head "$branch")

echo "PR: $pr_url"

gh pr merge "$pr_url" --squash --admin --delete-branch

# Tag the merged commit
git fetch origin main
git checkout main
git pull origin main

git tag "$tag"
git push origin "$tag"

echo "Done. Tagged ${tag} — release workflow will publish to PyPI."
