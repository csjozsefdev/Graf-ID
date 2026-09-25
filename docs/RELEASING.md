# Releasing Graf-Id

For maintainers. A release is built by the [release workflow](../.github/workflows/release.yml), which ends in a **draft** GitHub Release. Nothing is published until you press Publish.

## Cutting a release

1. Bump the version everywhere it lives (a test, `grafid/tests/test_version_sync.py`, fails if one is missed): `pyproject.toml`, `grafid/__init__.py`, `desktop/package.json`, `desktop/package-lock.json` (two places), `desktop/src-tauri/tauri.conf.json`, `desktop/src-tauri/Cargo.toml` and `desktop/src-tauri/Cargo.lock`.
2. Add a `## [<version>] — <date>` section to `CHANGELOG.md`; it becomes the release notes (`packaging/release_notes.py`).
3. If dependencies changed, regenerate the license notices and commit the result:
   `.venv\Scripts\python.exe packaging\generate_third_party_notices.py` (needs `npm ci` and a runtime build first; `--check` verifies it is current).
4. Merge to `main`, wait for CI, then tag: `git tag -a v<version> -m "Graf-Id <version>"` and `git push origin v<version>`.
5. The workflow builds the installers, signs them when SignPath is configured, and creates the draft release. If signing is configured, approve the signing request in SignPath when it arrives.
6. Review the draft (notes, both installers, `SHA256SUMS.txt`) and publish it.

The workflow can also be started by hand (Actions > Release > Run workflow) to test the build; a manual run creates a draft release for the version in `pyproject.toml`.

## One-time setup for SignPath signing

Signing is provided free of charge to open-source projects by the [SignPath Foundation](https://signpath.org/). The conditions are listed on <https://signpath.org/terms.html>; the ones that matter here:

- an OSI-approved license, a public repository, active maintenance, and a release that already exists in the form to be signed (publish the first, unsigned release before applying);
- a public code signing policy page: [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md). Make sure every statement in it is true for you before applying, in particular multi-factor authentication on GitHub and SignPath;
- builds that SignPath can verify (this is why the release is built by a GitHub Actions workflow), and manual approval of every signing request.

Steps:

1. Apply through the SignPath Foundation website (<https://signpath.org/>), pointing to the repository and the policy page.
2. When approved, create the SignPath project (slug `graf-id`) and a signing policy (slug `release-signing`) with manual approval. Paste [signpath/artifact-configuration.xml](../signpath/artifact-configuration.xml) as its artifact configuration and connect the GitHub repository as the trusted build system.
3. In the GitHub repository settings add the secret `SIGNPATH_API_TOKEN` and the variables `SIGNPATH_ORGANIZATION_ID` (this enables the signing job), and optionally `SIGNPATH_PROJECT_SLUG` / `SIGNPATH_SIGNING_POLICY_SLUG` if you chose other slugs.
4. Update the status line at the top of [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md) and the README once the first signed release is out.

## Build details worth knowing

- The runtime is built with the pinned CPython 3.12.10 (`packaging/build_runtime.ps1`); the workflow installs exactly that version.
- The workflow remaps the runner's cargo, rustup and checkout paths out of the Rust binary (`--remap-path-prefix`), so no account or machine names are embedded.
- Installers are unsigned unless the signing job ran; the release notes say which case applies.
