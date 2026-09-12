# Releasing MatterBook

How a version gets out, and the two things about it that look like bugs but are
not.

## Cutting a release

Run the **Version** workflow from the Actions tab and pick a bump. It works out
the next version from the newest tag, stamps it into the manifest, tags that,
builds the panel and publishes the archive. Tick `dry_run` to see the version it
would use and stop.

| | For |
| --- | --- |
| `patch` | Hotfixes and bug fixes. Nothing new. |
| `minor` | New features and other non-breaking changes. |
| `major` | Breaking changes, or a release big enough to mark as one. |

"Breaking" means something an existing install notices: a column the book no
longer reads, an action or event renamed, an entity removed that someone's
automation refers to.

### The bump commit is not on `main`

The workflow commits the manifest bump on a detached HEAD, tags *that*, and
pushes only the tag. The tagged commit sits one ahead of `main` and is reachable
through the tag alone.

That keeps release bookkeeping out of the branch history: `main` is what was
written, and the tags are what was shipped. The consequence to know about is
that **`main`'s manifest reads one version behind between releases** — the tags
are the source of truth for what has been released, not the file.

(This began as a hard requirement: the repository was produced by `git subtree
split` from a monorepo, and a CI commit on `main` would have made every future
publish a non-fast-forward. Development moved here, so it is now a choice rather
than a constraint — but a deliberate one.)

### The tag cannot trigger `release.yml` by itself

GitHub suppresses workflow triggers for refs pushed with `GITHUB_TOKEN`, so runs
cannot recurse. A version workflow that pushed a tag and trusted
`push: tags: v*` would appear to work and then silently never publish. Version
therefore calls `release.yml` directly, as a reusable workflow.

## Releasing by hand

`release.yml` keeps its `push: tags` trigger, so this still works:

```bash
git tag v0.3.0 && git push origin v0.3.0
```

As does *Releases → Draft a new release → Choose a tag → Create new tag on
publish* in the GitHub UI. The workflow copes with both: a pushed tag has no
release yet so it creates one; a release drafted in the UI already exists so it
attaches the archive to it. Either way the run fails if `matterbook.zip` is not
on the release at the end — a release without it installs nothing.

Tagging by hand means the manifest version has to match the tag yourself;
`release.yml` refuses to publish if they disagree. HACS reads the tag and Home
Assistant reads the manifest, so a mismatch means an install that reports the
wrong version forever.

## What ships

`matterbook.zip` holds the **contents** of `custom_components/matterbook` at the
archive root, because that is what HACS extracts into
`<config>/custom_components/matterbook/`. The same layout is what someone
unzipping by hand wants, so one artefact serves both.

The panel bundle is built during the release and is also committed to the
repository; CI fails if the committed copy is stale, so the two cannot drift.

## Installing through HACS

*Custom repositories* → this repository's URL, category **Integration**.

`hacs.json` sets `zip_release` **and** `hide_default_branch`, so HACS offers
nothing at all until a release exists. That is deliberate — the default branch
carries an unbuilt version number — but it does mean a fresh fork shows an empty
list until the first tag.

## Checks

* `ci.yml` — ruff, the tests, the panel build, and the committed-bundle check.
* `validate.yml` — hassfest and the HACS validator, on every push and weekly,
  since both tighten their rules over time and a repository that passed can
  start failing without anything here changing.

`validate.yml` passes `ignore: brands` to the HACS action. Remove that once the
icon is accepted into [home-assistant/brands](https://github.com/home-assistant/brands);
until then the brands check cannot pass for a new domain.
