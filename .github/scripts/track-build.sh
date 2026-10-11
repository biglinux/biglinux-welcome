#!/bin/bash
# Follow the BigLinux builder job started for a package, using the public API
# of https://gitlab.bigib.org/builder/packagebuilder (no token needed).
#
# Environment:
#   PACKAGE   package (and repository) name, e.g. biglinux-welcome
#   ORG       GitHub organization the builder clones from, e.g. biglinux
#   BRANCH    branch the build was requested for, e.g. main
#   SINCE     ISO 8601 time the request was made (the "Build Package" run end)
#   START_TIMEOUT, BUILD_TIMEOUT, PUBLISH_TIMEOUT   seconds to wait for the
#             job to appear / to end / for the package to be published
#
# Exits non-zero when no matching job starts, when it does not succeed, or when
# a testing/stable package does not reach https://repo.biglinux.com.br: the
# server drops some uploads without any error in the job.
set -euo pipefail

: "${PACKAGE:?}" "${ORG:?}" "${BRANCH:?}" "${SINCE:?}"
START_TIMEOUT=${START_TIMEOUT:-600}
BUILD_TIMEOUT=${BUILD_TIMEOUT:-3600}
PUBLISH_TIMEOUT=${PUBLISH_TIMEOUT:-3600}
api=https://gitlab.bigib.org/api/v4/projects/builder%2Fpackagebuilder
web=https://gitlab.bigib.org/builder/packagebuilder
url="https://github.com/$ORG/$PACKAGE"
summary=${GITHUB_STEP_SUMMARY:-/dev/null}

trap 'echo "::error::Request to the BigLinux builder failed (line $LINENO); is gitlab.bigib.org reachable?"' ERR

get() {
    curl -fsS --retry 3 --retry-delay 5 --retry-all-errors --max-time 30 "$@"
}

# One of the header lines the build job prints ("org: biglinux", ...)
header() {
    sed -nE "s/^[^ ]+ [0-9]+[OE]\+? ?$1: (.*)$/\1/p" <<<"$2" | head -n1
}

# Same rules as package-build in packagebuilder
case "$BRANCH" in
*update-stable*) repo=update-stable ;;
*update-testing*) repo=update-testing ;;
*unstable* | *development*) repo=unstable ;;
*testing*) repo=testing ;;
*stable*) repo=stable ;;
*) repo=unstable ;;
esac

since=$(date -u -d "$SINCE" +%s)
after=$(date -u -d "@$((since - 120))" +%FT%TZ)
echo "Looking for the $PACKAGE build of $url (branch $BRANCH) requested at $SINCE"

# 1. Find the job. Every request is a "trigger" pipeline whose child pipeline
#    has one job named after the package.
job='' child='' rejected=" " deadline=$((SECONDS + START_TIMEOUT))
while [ -z "$job" ]; do
    while read -r pid created; do
        [ "$(date -u -d "$created" +%s)" -ge $((since - 30)) ] || continue
        child=$(get "$api/pipelines/$pid/bridges" | jq -r '.[0].downstream_pipeline.id // empty')
        [ -n "$child" ] || continue
        id=$(get "$api/pipelines/$child/jobs" | jq -r --arg n "$PACKAGE" '.[] | select(.name == $n) | .id')
        if [ -z "$id" ] || [[ "$rejected" == *" $id "* ]]; then continue; fi
        log=$(get "$web/-/jobs/$id/raw" || true)
        [ -n "$(header git_branch "$log")" ] || continue # not started yet
        if [ "$(header url "$log")" = "$url" ] && [ "$(header git_branch "$log")" = "$BRANCH" ]; then
            job=$id
            echo "Builder accepted the request: pipeline $web/-/pipelines/$pid, job $web/-/jobs/$job"
            echo "  requested by $(header 'user sender' "$log"), created $created"
            break
        fi
        rejected+="$id "
    done < <(get "$api/pipelines?source=trigger&updated_after=$after&order_by=id&sort=asc&per_page=100" |
        jq -r '.[] | "\(.id) \(.created_at)"')

    if [ -z "$job" ]; then
        if [ "$SECONDS" -ge "$deadline" ]; then
            echo "::error::The builder started no $PACKAGE job for $url ($BRANCH) within ${START_TIMEOUT}s. See docs/ci-packaging.md."
            printf '### %s: no builder job\nNo job for %s, branch %s, started within %ss of %s.\n' \
                "$PACKAGE" "$url" "$BRANCH" "$START_TIMEOUT" "$SINCE" >>"$summary"
            exit 1
        fi
        sleep 20
    fi
done

# 2. Wait for it to finish
deadline=$((SECONDS + BUILD_TIMEOUT)) last=
while :; do
    status=$(get "$api/pipelines/$child/jobs" | jq -r --argjson id "$job" '.[] | select(.id == $id) | .status')
    [ "$status" = "$last" ] || echo "Job status: $status"
    last=$status
    case "$status" in
    success | failed | canceled | skipped) break ;;
    esac
    if [ "$SECONDS" -ge "$deadline" ]; then
        echo "::error::Builder job $web/-/jobs/$job still '$status' after ${BUILD_TIMEOUT}s"
        exit 1
    fi
    sleep 30
done

# 3. Report what was built and uploaded
log=$(get "$web/-/jobs/$job/raw" | sed -E 's/^[^ ]+ [0-9]+[OE]\+? ?//')
built=$(grep -m1 -oE '^==> Finished making: .*' <<<"$log" | sed 's/^==> Finished making: //' || true)
uploaded=$(grep -A1 '^sending incremental file list' <<<"$log" | grep -E '\.pkg\.tar\.[a-z]+$' || true)
{
    printf '### %s: builder job %s\n\n' "$PACKAGE" "$status"
    printf '| Step | Result |\n|---|---|\n'
    printf '| Request accepted | [job %s](%s/-/jobs/%s), branch %s |\n' "$job" "$web" "$job" "$BRANCH"
    printf '| Package built | %s |\n' "${built:-no}"
    printf '| Uploaded for the %s repository | %s |\n' "$repo" "${uploaded:-no}"
} >>"$summary"
echo "Built: ${built:-nothing}"
echo "Uploaded for the $repo repository: ${uploaded:-nothing}"

if [ "$status" != success ] || [ -z "$built" ] || [ -z "$uploaded" ]; then
    echo "::error::Builder job $web/-/jobs/$job ended '$status'"
    exit 1
fi

# 4. Wait for the repository to publish it. Only testing and stable are public.
case "$repo" in
testing | stable) ;;
*) exit 0 ;;
esac
# Ask for the file itself: the directory page is cached by the CDN for days.
published="https://repo.biglinux.com.br/$repo/x86_64/$(head -n1 <<<"$uploaded")"
echo "Waiting for $published"
deadline=$((SECONDS + PUBLISH_TIMEOUT))
until curl -fsI --max-time 30 -o /dev/null "$published"; do
    if [ "$SECONDS" -ge "$deadline" ]; then
        echo "::error::Uploaded, but $published is still missing after ${PUBLISH_TIMEOUT}s: the repository server dropped it. See docs/ci-packaging.md."
        printf '| Published in %s | **no**, dropped by the repository server |\n' "$repo" >>"$summary"
        exit 1
    fi
    sleep 120
done
echo "Published: $published"
printf '| Published in %s | [yes](%s) |\n' "$repo" "$published" >>"$summary"
