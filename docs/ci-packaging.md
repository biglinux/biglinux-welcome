# CI and packaging

How a commit in `biglinux/biglinux-welcome` becomes a package in the BigLinux
repositories, what was wrong before, and how to release.

## Flow

```
push to main / testing-* / stable-*          (biglinux/biglinux-welcome)
  └─ Build Package workflow
       ├─ tests    tests.yml: lint, translations, test suite, package build+install+remove
       └─ build    needs: tests — fails for any other branch
          run ends with success
  └─ biglinux organization (outside this repository) triggers
     gitlab.bigib.org/builder/packagebuilder with
     org, url, user, package_name = repository, git_branch = branch of the run
       └─ job "biglinux-welcome": clone url, checkout git_branch, rewrite PKGBUILD,
          chrootbuild (Manjaro stable, x86_64), sign, rsync to the repository server
  └─ GitLab Status workflow (workflow_run) follows that job through the public
     GitLab API and fails if it does not start within 10 min or does not succeed;
     for testing/stable it then waits up to 1 h for
     repo.biglinux.com.br/<repo>/x86_64/<file> and fails if it never appears.
     If the builder's runners fail (GitLab failure reason runner_system_failure,
     scheduler_failure, api_failure, data_integrity_failure), nothing was
     built: it re-runs the "build" job of that run, at most twice, and follows
     the new request
```

Runner failures are not rare. On 2026-10-11 the request for
`testing-2026-10-11` reached the builder 1 s after the run (pipeline 37669),
but its first job died with `runner_system_failure` (Kubernetes
`502 Bad Gateway`), as did two other pipelines that day.

Destination repository, decided by the builder from `git_branch`
(`package-build` in packagebuilder):

| Branch | Repository |
|---|---|
| `main` (anything not below) | unstable |
| `testing-*` | testing |
| `stable-*` | stable (also a GitHub release in `biglinux/biglinux-welcome`) |

Only `x86_64` is built: `arch=('any')` is rewritten to `x86_64 aarch64`, but
the aarch64 step is commented out in the builder.

## How the builder is started (evidence)

No workflow in any BigLinux repository calls GitLab. The trigger was found by
comparing GitHub run times with GitLab pipeline creation times (2026-10-10):

| GitHub run that ended successfully | Ended (UTC) | GitLab pipeline created | Job |
|---|---|---|---|
| biglinux-welcome "Build Package", main | 10-10 08:36:18 | 08:36:19 | 62063 |
| biglinux-welcome "Build Package", main | 10-03 09:40:19 | 09:40:20 | 60306 |
| biglinux-settings "Translate and Build Package", main | 09-13 20:06:08 | 20:06:10 | 56153 |
| biglinux-settings "Translate and Build Package", stable-2026-09-13_17-55 | 09-13 20:57:01 | 20:57:04 | 56156 |

and no pipeline followed: "Tests" runs, a cancelled "Translate and Build
Package" run, or the creation of branches `testing-2026-10-10`,
`testing-2026-10-10-1` and `stable-2026-10-03_06-40` (no workflow ran for them).
Every build job logs `user sender: <GitHub user>` and the branch of the run.

So the biglinux organization reacts to successful runs of workflows named
"… Build Package" (all of them have a final job `build`). The webhook itself
needs organization admin access to see; its exact filter (workflow name, job
name, conclusion) is inferred from the table above. Keep the workflow name
`Build Package` and the job id `build`.

## What was wrong (before this change)

1. `build-package.yml` sent `repository_dispatch` events to
   `BigLinux-Package-Build/build-package` and `build-package-ARM`. That
   organization no longer exists (`github.com/BigLinux-Package-Build` is 404),
   and both calls answered `401 Bad credentials`
   (run 38038451785 in biglinux, 38099995866 in the fork, where the secret is
   empty). `curl` without `--fail` hid this, so the runs were green.
2. The workflow ran only for `main`. Releases to testing/stable are made by
   creating `testing-*`/`stable-*` branches, which need a successful
   "Build Package" run on that branch. Since 3.0.0 none ran, so
   `testing-2026-10-10` and `testing-2026-10-10-1` were never built and 3.0.1
   only reached unstable (job 62063).
3. The build was requested whatever the tests said: the run that requested
   it did not depend on them.
4. `WEBHOOK_TOKEN` was expanded straight into the shell command.

The packages built from `main` were fine: job 62063 built and uploaded
`biglinux-welcome-1-3.0.1-1-x86_64.pkg.tar.zst` from `biglinux/biglinux-welcome`.

## PKGBUILD and the builder

The builder clones `https://github.com/biglinux/biglinux-welcome` (the
organization that sent the event), checks out the branch, then edits the
PKGBUILD: `source=(git+….git)` becomes `….git#branch=<branch>`, `arch=('any')`
becomes `('x86_64' 'aarch64')` and `git` is added to `makedepends`.
`tests/check-pkgbuild.sh build` applies the same edits and checks the result.

- `url`/`source` must keep pointing to `github.com/biglinux/biglinux-welcome`:
  that is where official packages come from. Forks are not built
  (packagebuilder only accepts `org` biglinux, biglinuxaur*, xivastudio,
  bigcommunity).
- The builder builds the head of the branch when the job starts, not
  necessarily the commit of the run. The `concurrency` group cancels older
  runs on the same branch, so the last successful run is for the head.
- The package version is the build date (`pkgver=$(date +%y.%m.%d)`,
  `pkgrel=$(date +%H%M)`), like biglinux-settings. Never add an `epoch`:
  see below.
- `BIGLINUX_WELCOME_SRC` is unset on the builder, so it uses the git source.

## Why 1:3.0.1-1 never reached testing

Job [62182](https://gitlab.bigib.org/builder/packagebuilder/-/jobs/62182)
(branch `testing-2026-10-10-2`) built `1:3.0.1-1` and uploaded it for testing
without errors, but `repo.biglinux.com.br/testing/x86_64` never listed it,
although its database was updated later (04:14 UTC, adding chatai-plasmoid,
uploaded at 04:11 by the same user and the same builder steps).

The server-side step that turns testing uploads into the repository is not
public. What the repositories show (2026-10-11):

- every package in both testing and stable has a date version, and the
  testing one is newer;
- packages with an epoch are accepted in stable (`biglinux-driver-manager
  1:26.10.02-2252`, `tts-biglinux 1:4.1.0-3`) and in testing when stable has
  no version (`portainer-bin 1:2.18.3-1`);
- no package with an epoch is in testing while stable has an older version.
  `biglinux-welcome 1:3.0.1-1` (stable: `26.06.18-0104`) was dropped;
  `tts-biglinux 1:4.1.0-2`, after the same change from dates, went straight
  to stable.
- the same file name uploaded twice is not the cause: chatai-plasmoid
  `1.0.1-1` was built from main twice before its testing build, and that
  testing build was accepted.

The directory page `https://repo.biglinux.com.br/testing/x86_64/` is not a
reliable check: the CDN serves it from cache for days (on 2026-10-11 it showed
the 2026-10-09 state, without chatai-plasmoid). Request the file itself, or
run `pacman -Syl biglinux-testing`; GitLab Status requests the file.

So the testing step drops a package that does not look newer than stable and
reads `1:3.0.1-1` without its epoch (`3.0.1-1` < `26.06.18-0104`). Date
versions, as biglinux-settings and the earlier biglinux-welcome use, are
always newer. Confirming this needs access to the repository server.

`1:3.0.1-1` is still in the unstable repository. A date version is lower than
it for pacman, so unstable needs it removed (`repo-remove`) by whoever runs
that server, and machines that installed it must run
`sudo pacman -S biglinux-welcome` once.

## External configuration

None is needed for builds. Recommended, by a `biglinux` admin:

- Delete the unused `WEBHOOK_TOKEN` secret (organization or repository level).
- Protect `main` in `biglinux/biglinux-welcome` and require the **Tests**
  checks (`tests`, `package`) on pull requests, so nothing untested is merged.
  Direct pushes to `main` are still gated by the `build` job.
- If the organization webhook filter is ever changed, check that it still
  matches "Build Package" / `build`.

## Release checklist

1. For a new application version, bump `APP_VERSION` in `utils.py` (shown in
   About and `--version`). The package version is the build date and needs
   no change; every build gets a new one.
2. Open a pull request; **Tests** must pass (`tests` and `package`).
3. Merge into `main` in `biglinux/biglinux-welcome` → unstable. Check that
   **GitLab Status** is green; its summary links the job and the file uploaded.
4. To publish to testing: create branch `testing-YYYY-MM-DD` from `main`
   (`git push origin main:refs/heads/testing-$(date +%F)`). Same for stable
   with `stable-YYYY-MM-DD_HH-MM`. Check **GitLab Status** again.
5. If the builder job failed, open the job link. Runner failures are retried
   automatically; for anything else, fix it and re-run the `build` job of the
   **Build Package** run for that branch (or Actions → Run workflow).

Each branch gets one build per successful run; rerunning the workflow
requests another build of the same branch.
