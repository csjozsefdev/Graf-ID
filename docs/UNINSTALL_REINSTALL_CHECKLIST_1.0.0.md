# Manual verification: uninstall / reinstall, data persistence (v1.0.0)

**Not automated.** Actually installing/uninstalling the MSI or NSIS package
writes to `Program Files` and the Windows registry (Add/Remove Programs
entries are created even for a per-user install) — a real, system-level
change beyond this repo, so this was deliberately left for you to run by
hand rather than scripted.

**Expected result, per the current installer configuration:** user data
should survive an uninstall/reinstall cycle. `tauri.conf.json` does not
configure the NSIS/MSI uninstaller to remove `%LOCALAPPDATA%\Graf-Id\`
(nothing in this repo does — Tauri's default uninstaller only removes
what it installed: the app binary, the bundled `runtime/`, and shortcuts),
and the app itself writes its database, config, and logs there, entirely
outside the install directory. This is documented in `README.md`'s Known
Limitations section. **This expectation has not been verified end-to-end
on a real machine — treat the steps below as the actual verification, not
this paragraph.**

## Steps

Use the built installer for this session's pinned-Python rebuild:
`desktop\src-tauri\target\release\bundle\msi\Graf-Id_1.0.0_x64_en-US.msi`
or the NSIS `...\nsis\Graf-Id_1.0.0_x64-setup.exe` — either is fine, pick
one (repeating with the other afterward is a nice-to-have, not required).

1. **Install** — run the installer normally (interactive is fine; no
   special flags needed). Note whether it asked for admin elevation or
   installed per-user.
2. **Launch Graf-Id** from the Start Menu shortcut the installer created
   (not by running the `.exe` directly from the build output — that's
   what the automated smoke test already covers; this step should exercise
   the actual installed shortcut/path).
3. **Add a test project** — any real folder on disk works (`Add project`
   in the sidebar). Note the project name you used.
4. **Create at least one session with an exit note** — Open the project,
   do anything briefly, then close the editor (or use `graf-id session
   close` / the exit-note dialog) and fill in an exit note, a blocker
   text, and a next-step text so there's real content to check for later.
5. **Record the data path** — Settings → "Open data folder" (or just
   check `%LOCALAPPDATA%\Graf-Id\`). Confirm `graf-id.db` and
   `config.json` exist there and note their last-modified timestamps.
6. **Uninstall** — via Windows Settings → Apps, or Control Panel →
   Programs and Features. Use the normal uninstall flow, not a manual
   delete of the install directory.
7. **Check `%LOCALAPPDATA%\Graf-Id\` again** — confirm `graf-id.db` and
   `config.json` are still there, unchanged from step 5's timestamps.
   Also confirm the *install* directory (wherever it was — check Program
   Files or `%LOCALAPPDATA%\Programs` depending on per-user vs per-machine)
   is gone.
8. **Reinstall** the same version.
9. **Launch again** and confirm: the test project from step 3 is still
   registered, and its resume panel shows the exit note / blocker / next
   step from step 4 — i.e. nothing was lost across the uninstall.

## What to report back

- Did install/uninstall require admin elevation, or was it per-user?
- Did step 7's data-folder check pass (data survived) or fail (data was
  deleted)?
- Did step 9 fully recover the project and its session content, or was
  anything missing/stale?
- Anything surprising in the installer or uninstaller UX itself (wrong
  app name, missing icon, odd Start Menu placement, leftover registry
  noise, etc.) — worth a quick note even if not directly about data
  persistence.

If step 7 or 9 fails, that's a real bug to fix before wider release, not
just a documentation gap — flag it and this shouldn't be waved through.
