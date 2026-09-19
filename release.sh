#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
UV_BIN="${UV_BIN:-uv}"
NODE_BIN="${NODE_BIN:-node}"
FRONTEND_PNPM_BIN="${FRONTEND_PNPM_BIN:-pnpm}"
DRY_RUN=false
ASSUME_YES=false
TARGET_SPEC=""
VERSION_SURFACES=(VERSION backend/VERSION backend/pyproject.toml backend/uv.lock frontend/VERSION frontend/package.json)

usage() {
    cat <<'EOF'
Usage: ./release.sh [--dry-run] [--yes] <patch|minor|major|X.Y.Z>

Examples:
  ./release.sh patch --dry-run
  ./release.sh 0.3.0 --yes

Options:
  --dry-run  Preview file changes and git commands without modifying files.
  --yes      Skip the interactive confirmation prompt.

Behavior:
  1. Resolve the target version from the monorepo release surfaces.
  2. In live release mode, validate the root repo is clean and current on main.
  3. Update VERSION, backend/VERSION, backend/pyproject.toml, backend/uv.lock,
     frontend/VERSION, and frontend/package.json. Plugin versions stay independent.
  4. Verify the lockfile, the backend health version, and the frontend build.
  5. Commit, tag vX.Y.Z, and push main and the tag. The tag publishes images only
     after CI passes on the release commit; this script does not deploy.

Dry-run notes:
  - previews the monorepo release flow without changing files
  - skips clean/main/current-origin guards so the flow can be inspected from feature branches
EOF
}

log() {
    echo "==> $*"
}

fail() {
    echo "Error: $*" >&2
    exit 1
}

require_command() {
    local command_name="$1"
    if ! command -v "$command_name" >/dev/null 2>&1; then
        fail "Missing required command: $command_name"
    fi
}

run_in_dir() {
    local dir="$1"
    shift

    if [[ "$DRY_RUN" == true ]]; then
        printf '[dry-run] (cd %q &&' "$dir"
        printf ' %q' "$@"
        printf ')\n'
        return 0
    fi

    (
        cd "$dir"
        "$@"
    )
}

write_version_file() {
    local path="$1"
    local version="$2"

    if [[ "$DRY_RUN" == true ]]; then
        echo "[dry-run] write $path -> $version"
        return 0
    fi

    printf '%s\n' "$version" > "$path"
}

write_frontend_package_version() {
    local version="$1"

    if [[ "$DRY_RUN" == true ]]; then
        echo "[dry-run] update $FRONTEND_DIR/package.json version -> $version"
        return 0
    fi

    "$NODE_BIN" - "$FRONTEND_DIR/package.json" "$version" <<'NODE'
const fs = require("node:fs");

const packagePath = process.argv[2];
const version = process.argv[3];
const data = JSON.parse(fs.readFileSync(packagePath, "utf8"));
data.version = version;
fs.writeFileSync(packagePath, `${JSON.stringify(data, null, 2)}\n`, "utf8");
NODE
}

read_text_file() {
    local path="$1"
    "$NODE_BIN" - "$path" <<'NODE'
const fs = require("node:fs");

process.stdout.write(fs.readFileSync(process.argv[2], "utf8").trim());
NODE
}

read_frontend_package_version() {
    "$NODE_BIN" - "$FRONTEND_DIR/package.json" <<'NODE'
const fs = require("node:fs");

const data = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
process.stdout.write(String(data.version ?? "").trim());
NODE
}

read_backend_project() {
    (cd "$BACKEND_DIR" && "$UV_BIN" version --frozen --color never)
}

read_backend_project_version() {
    read_backend_project | awk '{ print $2 }'
}

read_backend_lock_version() {
    local project_name
    project_name="$(read_backend_project | awk '{ print $1 }')"
    awk -v name="\"$project_name\"" '
        /^\[\[package\]\]/ { current = "" }
        /^name = / { current = $3 }
        /^version = / && current == name { gsub(/"/, "", $3); print $3; exit }
    ' "$BACKEND_DIR/uv.lock"
}

validate_exact_version() {
    local version="$1"
    [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

resolve_target_version() {
    local current_version="$1"
    local spec="$2"

    if validate_exact_version "$spec"; then
        printf '%s\n' "$spec"
        return 0
    fi

    if [[ ! "$current_version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
        fail "Automatic semver bumps require a plain X.Y.Z current version. Current value: $current_version"
    fi

    local major="${BASH_REMATCH[1]}"
    local minor="${BASH_REMATCH[2]}"
    local patch="${BASH_REMATCH[3]}"

    case "$spec" in
        patch)
            patch=$((patch + 1))
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        *)
            fail "Invalid version target '$spec'. Use patch, minor, major, or an exact X.Y.Z value."
            ;;
    esac

    printf '%s.%s.%s\n' "$major" "$minor" "$patch"
}

require_clean_repo() {
    local repo_dir="$1"
    local repo_label="$2"
    local status

    status="$(git -C "$repo_dir" status --porcelain)"
    if [[ -n "$status" ]]; then
        printf '%s\n' "$status" >&2
        fail "$repo_label has uncommitted changes. Commit or stash them before running release.sh"
    fi
}

require_main_branch() {
    local repo_dir="$1"
    local repo_label="$2"
    local branch

    branch="$(git -C "$repo_dir" rev-parse --abbrev-ref HEAD)"
    if [[ "$branch" != "main" ]]; then
        fail "$repo_label must be on main. Current branch: $branch"
    fi
}

fetch_and_require_current_origin_main() {
    local repo_dir="$1"
    local repo_label="$2"
    local remote_ref="refs/remotes/origin/main"

    log "Fetching $repo_label origin/main"
    git -C "$repo_dir" fetch origin main --tags >/dev/null 2>&1

    git -C "$repo_dir" show-ref --verify --quiet "$remote_ref" || fail "$repo_label is missing origin/main"

    if ! git -C "$repo_dir" merge-base --is-ancestor "$remote_ref" HEAD; then
        fail "$repo_label main is behind or diverged from origin/main. Fast-forward it before releasing."
    fi
}

require_local_tag_absent() {
    local repo_dir="$1"
    local repo_label="$2"
    local tag_name="$3"

    if git -C "$repo_dir" rev-parse -q --verify "refs/tags/$tag_name" >/dev/null 2>&1; then
        fail "$repo_label already has local tag $tag_name"
    fi
}

require_remote_tag_absent() {
    local repo_dir="$1"
    local repo_label="$2"
    local tag_name="$3"
    local existing

    existing="$(git -C "$repo_dir" ls-remote --tags origin "refs/tags/$tag_name")"
    if [[ -n "$existing" ]]; then
        fail "$repo_label remote already has tag $tag_name"
    fi
}

print_version_surfaces() {
    cat >&2 <<EOF
  VERSION                 = $(read_text_file "$ROOT_DIR/VERSION")
  backend/VERSION         = $(read_text_file "$BACKEND_DIR/VERSION")
  backend/pyproject.toml  = $(read_backend_project_version)
  backend/uv.lock         = $(read_backend_lock_version)
  frontend/VERSION        = $(read_text_file "$FRONTEND_DIR/VERSION")
  frontend/package.json   = $(read_frontend_package_version)
EOF
}

surfaces_equal() {
    local expected="$1"

    [[ "$(read_text_file "$ROOT_DIR/VERSION")" == "$expected" ]] &&
        [[ "$(read_text_file "$BACKEND_DIR/VERSION")" == "$expected" ]] &&
        [[ "$(read_backend_project_version)" == "$expected" ]] &&
        [[ "$(read_backend_lock_version)" == "$expected" ]] &&
        [[ "$(read_text_file "$FRONTEND_DIR/VERSION")" == "$expected" ]] &&
        [[ "$(read_frontend_package_version)" == "$expected" ]]
}

require_aligned_current_versions() {
    if surfaces_equal "$(read_text_file "$ROOT_DIR/VERSION")"; then
        return 0
    fi

    echo "Current version surfaces are not aligned:" >&2
    print_version_surfaces
    fail "Align all version surfaces before running release.sh"
}

verify_aligned_versions() {
    local expected_version="$1"

    if surfaces_equal "$expected_version"; then
        return 0
    fi

    echo "Version surfaces do not all equal $expected_version:" >&2
    print_version_surfaces
    fail "Version surfaces are not aligned to $expected_version"
}

require_forward_version() {
    local current_version="$1"
    local target_version="$2"
    local current_major
    local current_minor
    local current_patch
    local target_major
    local target_minor
    local target_patch

    [[ "$current_version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || fail "Current version must be plain X.Y.Z: $current_version"
    current_major="${BASH_REMATCH[1]}"
    current_minor="${BASH_REMATCH[2]}"
    current_patch="${BASH_REMATCH[3]}"

    [[ "$target_version" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+)$ ]] || fail "Target version must be plain X.Y.Z: $target_version"
    target_major="${BASH_REMATCH[1]}"
    target_minor="${BASH_REMATCH[2]}"
    target_patch="${BASH_REMATCH[3]}"

    if (( target_major < current_major )) || \
       (( target_major == current_major && target_minor < current_minor )) || \
       (( target_major == current_major && target_minor == current_minor && target_patch <= current_patch )); then
        fail "Target version must be greater than current version ($current_version): $target_version"
    fi
}

require_expected_repo_state() {
    local repo_dir="$1"
    local repo_label="$2"
    shift 2

    local expected_modified=""
    local actual_modified
    local staged_changes
    local untracked_files
    local path
    local numstat

    if [[ "$#" -gt 0 ]]; then
        expected_modified="$(printf '%s\n' "$@" | LC_ALL=C sort)"
    fi

    actual_modified="$(git -C "$repo_dir" diff --name-only | LC_ALL=C sort)"
    staged_changes="$(git -C "$repo_dir" diff --cached --name-only | LC_ALL=C sort)"
    untracked_files="$(git -C "$repo_dir" ls-files --others --exclude-standard | LC_ALL=C sort)"

    if [[ -n "$staged_changes" ]]; then
        printf '%s\n' "$staged_changes" >&2
        fail "$repo_label has unexpected staged changes before release commit"
    fi

    if [[ -n "$untracked_files" ]]; then
        printf '%s\n' "$untracked_files" >&2
        fail "$repo_label has unexpected untracked files after verification"
    fi

    if [[ "$actual_modified" != "$expected_modified" ]]; then
        cat >&2 <<EOF
Unexpected modified files in $repo_label.
Expected:
${expected_modified:-<none>}
Actual:
${actual_modified:-<none>}
EOF
        fail "$repo_label contains changes outside the expected release surfaces"
    fi

    # uv must only rewrite the project's own version, never re-resolve dependencies.
    for path in backend/pyproject.toml backend/uv.lock; do
        numstat="$(git -C "$repo_dir" diff --numstat -- "$path")"
        if [[ "$numstat" != $'1\t1\t'"$path" ]]; then
            printf '%s\n' "$numstat" >&2
            fail "$path changed more than its version line"
        fi
    done
}

confirm_release() {
    if [[ "$ASSUME_YES" == true || "$DRY_RUN" == true ]]; then
        return 0
    fi

    local response
    printf 'Proceed with release %s? [y/N] ' "$1"
    read -r response
    if [[ ! "$response" =~ ^[Yy]([Ee][Ss])?$ ]]; then
        fail "Release aborted by user"
    fi
}

prepare_release_repo() {
    if [[ "$DRY_RUN" == true ]]; then
        log "Dry run: skipping root clean-state and main-branch guards"
        return 0
    fi

    require_clean_repo "$ROOT_DIR" "Root repo"
    require_main_branch "$ROOT_DIR" "Root repo"
    fetch_and_require_current_origin_main "$ROOT_DIR" "Root repo"
}

update_version_surfaces() {
    local target_version="$1"

    log "Updating version surfaces to $target_version"
    write_version_file "$ROOT_DIR/VERSION" "$target_version"
    write_version_file "$BACKEND_DIR/VERSION" "$target_version"
    run_in_dir "$BACKEND_DIR" "$UV_BIN" version "$target_version" --no-sync --color never
    write_version_file "$FRONTEND_DIR/VERSION" "$target_version"
    write_frontend_package_version "$target_version"
}

run_release_verification() {
    log "Verifying backend lockfile"
    run_in_dir "$BACKEND_DIR" "$UV_BIN" lock --check

    log "Verifying backend health version"
    run_in_dir "$BACKEND_DIR" "$UV_BIN" run pytest -q tests/test_runtime_config_health.py

    log "Verifying frontend build"
    run_in_dir "$FRONTEND_DIR" "$FRONTEND_PNPM_BIN" run build
}

commit_tag_and_push_root() {
    local target_version="$1"
    local tag_name="$2"

    log "Committing and tagging monorepo release $target_version"
    run_in_dir "$ROOT_DIR" git add "${VERSION_SURFACES[@]}"
    run_in_dir "$ROOT_DIR" git commit -m "chore: bump version to $target_version"
    run_in_dir "$ROOT_DIR" git tag "$tag_name"
    run_in_dir "$ROOT_DIR" git push origin main
    run_in_dir "$ROOT_DIR" git push origin "$tag_name"
}

while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            ;;
        --yes|-y)
            ASSUME_YES=true
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        patch|minor|major)
            if [[ -n "$TARGET_SPEC" ]]; then
                fail "Version target was provided more than once"
            fi
            TARGET_SPEC="$1"
            ;;
        *)
            if [[ -n "$TARGET_SPEC" ]]; then
                fail "Unexpected argument: $1"
            fi
            TARGET_SPEC="$1"
            ;;
    esac
    shift
done

if [[ -z "$TARGET_SPEC" ]]; then
    usage
    exit 1
fi

require_command git
require_command "$UV_BIN"
require_command "$NODE_BIN"
require_command "$FRONTEND_PNPM_BIN"

prepare_release_repo
require_aligned_current_versions

CURRENT_VERSION="$(read_text_file "$ROOT_DIR/VERSION")"
TARGET_VERSION="$(resolve_target_version "$CURRENT_VERSION" "$TARGET_SPEC")"
require_forward_version "$CURRENT_VERSION" "$TARGET_VERSION"

TAG_NAME="v$TARGET_VERSION"
require_local_tag_absent "$ROOT_DIR" "Root repo" "$TAG_NAME"
require_remote_tag_absent "$ROOT_DIR" "Root repo" "$TAG_NAME"

echo "Release plan"
echo "  Current version : $CURRENT_VERSION"
echo "  Target version  : $TARGET_VERSION"
echo "  Root tag        : $TAG_NAME"
echo "  Release mode    : $([[ "$DRY_RUN" == true ]] && echo dry-run || echo live)"
echo ""

confirm_release "$TARGET_VERSION"
update_version_surfaces "$TARGET_VERSION"

if [[ "$DRY_RUN" == false ]]; then
    verify_aligned_versions "$TARGET_VERSION"
fi

run_release_verification

if [[ "$DRY_RUN" == false ]]; then
    require_expected_repo_state "$ROOT_DIR" "Root repo" "${VERSION_SURFACES[@]}"
fi

commit_tag_and_push_root "$TARGET_VERSION" "$TAG_NAME"

if [[ "$DRY_RUN" == false ]]; then
    verify_aligned_versions "$TARGET_VERSION"
fi

echo ""
if [[ "$DRY_RUN" == true ]]; then
    echo "Dry run for monorepo release $TARGET_VERSION completed. No changes were made."
else
    echo "Release $TARGET_VERSION completed."
fi
