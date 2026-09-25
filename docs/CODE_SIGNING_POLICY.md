# Code signing policy

**Status:** the Graf-Id 1.0.0 installers are not code-signed yet. Windows SmartScreen may warn the first time you run them; verify the download with the SHA-256 checksums (`SHA256SUMS.txt`) attached to every release. We are applying for free code signing for open-source projects, and this policy describes how signed releases will work once it is granted.

## Attribution

Once signing is active for a release, this applies:

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org).

## What is signed

Only the Windows installers of Graf-Id, built from the tagged source code in this repository:

- `Graf-Id_<version>_x64-setup.exe` (NSIS installer)
- `Graf-Id_<version>_x64_en-US.msi` (MSI installer)

Nothing else is signed with this certificate. The installers also contain unmodified upstream components (the embedded CPython interpreter and the Microsoft Visual C++ runtime libraries); they are not signed as Graf-Id's own code. The full list of bundled third-party software and their licenses is in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Team roles

Graf-Id is maintained by one person, who holds all roles:

- **Authors** (may change the source code without review): József Csordás ([@csjozsefdev](https://github.com/csjozsefdev))
- **Reviewers** (review and merge changes from other contributors): József Csordás
- **Approvers** (approve each signing request): József Csordás

Contributions from other people are only merged after the maintainer has reviewed them. Every person with access to the repository or to the signing service must use multi-factor authentication.

## How a release is built and signed

1. A version tag (`v<version>`) is pushed. The [release workflow](../.github/workflows/release.yml) builds the installers from that exact commit on a GitHub-hosted runner; the build fails if the tag and the project version differ.
2. The workflow submits the unsigned installers to SignPath. SignPath verifies that they were built by this repository's workflow from this source code, and only accepts installers whose product name is `Graf-Id`.
3. The approver reviews and manually approves the signing request. There is no automatic signing.
4. The signed installers and their SHA-256 checksums are attached to a draft GitHub Release, which the maintainer reviews and publishes.

## Privacy policy

This program will not transfer any information to other networked systems unless specifically requested by the user or the person installing or operating it.

Graf-Id keeps its data on your machine (`%LOCALAPPDATA%\Graf-Id`, or the folder set in `GRAFID_DATA_DIR`). It contains no telemetry, analytics, crash reporting or automatic update check, and no code that opens network connections. The desktop shell renders its interface with Microsoft Edge WebView2, a Microsoft component that is governed by Microsoft's own privacy statement.

## Installation and removal

The installers announce what they install, and the app can be removed with the Windows uninstaller (Settings > Apps, or the MSI/NSIS uninstaller). Uninstalling does not delete your Graf-Id data folder; delete it yourself for a complete removal.

## Reporting a problem

To report a suspicious or wrongly signed file, or a security issue, follow [SECURITY.md](../SECURITY.md).
