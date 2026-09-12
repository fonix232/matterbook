# Publishing MatterBook as a HACS repository

**The repository exists: [fonix232/matterbook](https://github.com/fonix232/matterbook).**
It was created by the split described below, and the steps here are now the
recurring procedure for publishing changes to it.

Everything in this directory is arranged so it can become that standalone
repository with one command. This document says why the step exists, and how to
repeat it.

## Why it cannot be installed from this monorepo

HACS reads a **repository's** releases, not a directory's. Concretely
(`hacs/integration`, `repositories/base.py`):

* the version offered is the newest release tag of the repository;
* with `zip_release`, the download URL is that release's asset named by
  `filename`, fetched with `github_release_asset(repository, version, filename)`.

`network-tools` publishes releases for its Unraid and TrueNAS plugins too. HACS
would offer whichever of those is newest as "the MatterBook version", then fail
to find `matterbook.zip` among its assets. That is not a configuration problem
to work around — it is what a monorepo means to HACS.

So: develop here, publish from a repository of its own.

## The split

```bash
# From the root of network-tools, on an up-to-date main:
git subtree split --prefix=homeassistant/matterbook -b matterbook-export
git push git@github.com:fonix232/matterbook.git matterbook-export:main
```

The target repository must be created empty (no README, no licence) — anything
committed there first makes the push a non-fast-forward.

It has to be its own repository rather than a directory in `fonix232/hacs-repo`:
HACS resolves an integration with `get_first_directory_in_directory(tree,
"custom_components")`, which takes the **first** directory it finds and stops.
Two integrations in one repository means HACS serves whichever sorts first and
silently ignores the other — which would have taken Renovate Updates' place.

`git subtree split` rewrites only this directory's history, with these files at
the repository root — which is exactly the layout HACS requires:

```
custom_components/matterbook/…   ← the integration
panel/                           ← TypeScript source for the sidebar panel
hacs.json                        ← already written for zip_release
.github/workflows/               ← CI, validation and release, already written
README.md  DESIGN.md  PANEL.md
```

The workflows in `.github/workflows/` do nothing inside the monorepo — GitHub
only reads workflows from a repository root — and start working the moment this
directory *is* the root.

## After the first push

1. **Repository settings.** HACS requires a repository description and at least
   one topic. Add both, or HACS validation fails before anything else does.

2. **Brand assets.** A custom integration wants an icon in
   [home-assistant/brands](https://github.com/home-assistant/brands); until that
   PR is merged, `validate.yml` passes `ignore: brands` to the HACS action.
   Remove that line once the brand is accepted.

3. **Release.** Run the **Version** workflow from the Actions tab, pick
   `patch`, `minor` or `major`, and it does the rest: works out the next
   version, stamps it into the manifest, tags that, builds and publishes.
   `dry_run` prints the version it would use and stops.

   Two things about it are worth knowing, because both look like bugs otherwise:

   * **The bump commit is not on `main`.** `main` has to stay byte-identical to
     what `git subtree split` produces, or every future publish becomes a
     non-fast-forward. So the workflow commits the manifest bump on a detached
     HEAD, tags *that*, and pushes only the tag. The tagged commit sits one
     ahead of `main` and is reachable through the tag alone. A consequence:
     `main`'s manifest shows the previous version between releases, and **the
     tags are the source of truth** for what has been released.
   * **The tag cannot trigger `release.yml` on its own.** GitHub suppresses
     workflow triggers for refs pushed with `GITHUB_TOKEN`, to stop runs
     recursing. Waiting for the `push: tags` trigger would wait forever, so
     Version calls `release.yml` directly as a reusable workflow.

   Tagging by hand still works and still publishes — `release.yml` keeps its
   `push: tags: v*` trigger:

   ```bash
   git tag v0.1.0 && git push origin v0.1.0
   ```

   Or from GitHub: *Releases → Draft a new release → Choose a tag → Create new
   tag on publish*, targeting `main`. `release.yml` copes with both — a pushed
   tag has no release yet so it creates one, and a release drafted in the UI
   already exists so it attaches the archive to it. Either way the run fails if
   `matterbook.zip` is not on the release at the end.

4. **Install.** In HACS: *Custom repositories* → the repository URL, category
   *Integration*. Users then get updates through HACS like any other.

   Note that `hacs.json` sets `zip_release` **and** `hide_default_branch`, so
   HACS offers nothing at all until the first release exists. Cut `v0.1.0`
   before telling anyone the repository is there.

## Keeping the two in step

Re-running `git subtree split` produces the same commits for unchanged history,
so subsequent pushes are fast-forwards:

```bash
git subtree split --prefix=homeassistant/matterbook -b matterbook-export
git push git@github.com:fonix232/matterbook.git matterbook-export:main
```

Treat the monorepo as the source of truth and the split repository as a
publishing mirror. If you ever start taking pull requests on the mirror, stop
splitting and move development there instead — merging in both directions is a
worse job than moving once.

## Until then

The integration installs perfectly well by hand, and
`release-ha-matterbook.yml` in the monorepo builds exactly the same archive:

```bash
# From a ha-matterbook-v* release, or built locally:
unzip matterbook.zip -d /config/custom_components/matterbook/
```

The archive holds the *contents* of `custom_components/matterbook` at its root —
the layout HACS extracts and the one a manual installer wants — so one artifact
serves both paths.
