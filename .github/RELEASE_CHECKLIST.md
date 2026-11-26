# Release checklist

For a release from the dev branch (e.g. `0.3.0`) to `main`. Publishing to the
Comfy Registry happens when `pyproject.toml` changes on `main`
(`publish_action.yml`); a minor or major version (patch 0) then gets a GitHub
release with its CHANGELOG section (`github_release.yml`). A published version
can't be replaced, so everything below happens before the merge.

## Before merging

- [ ] All feature branches for the release are merged into the dev branch.
- [ ] `version` in `pyproject.toml` is the new version, not yet published.
- [ ] `CHANGELOG.md`: the heading reads `## <version> (<YYYY-MM-DD>)` (not
      "unreleased"); its sections use `###` (the release notes stop at the
      next `## `).
- [ ] Tests: `python -m unittest discover -s tests`
- [ ] Node page reference tables are current: `python tools/node_docs.py --check`
- [ ] Example workflows load and run in a current ComfyUI (Nodes 2.0 and
      classic): `node tools/smoke_workflows.mjs http://127.0.0.1:8188` against
      a running ComfyUI with the pack installed (needs Node.js and Playwright).
- [ ] A 0.2.x workflow that uses `PDOutput` still loads and saves the same
      files (the hidden alias).
- [ ] Manual check in ComfyUI: each node's help panel page shows; PD Sound
      plays; Copy Path copies; PD Profiler's **profile** button reports and
      charts.
- [ ] Links: README and `docs/` links resolve on the branch (absolute
      `blob/main` links go live with the merge).
- [ ] Media for the docs pages is in `docs/images/` / `docs/media/` and
      referenced pages render on GitHub.
- [ ] Nothing new a registry scan would flag: no `subprocess`, `eval`/`exec`,
      new environment reads or network calls. `.comfyignore` still leaves out
      `tests/`, `.github/` and `tools/`.

## Merge

- [ ] Merge the dev branch into `main` (PR, merge commit).
- [ ] Actions: "Publish to Comfy registry" succeeds, then "GitHub release"
      creates `<version>` marked latest.

## After

- [ ] The registry page shows the new version, and its security scan isn't
      flagged (registry.comfy.org, or ComfyUI's Manager / extension browser).
- [ ] The GitHub release notes read correctly.
- [ ] ComfyUI-Manager installs the new version on a clean ComfyUI.
- [ ] Start the next dev branch from `main`.
