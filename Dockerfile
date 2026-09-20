# Reproducible test/build environment for Graf-Id — NOT for running the
# native desktop app. The GUI (WebView2 window, tray, installers) is
# Windows-only and stays host-only; see docs/DOCKER.md.
#
# Two build targets:
#   test        (default) — Python 3.12 + Node 20 + git. Runs the Python
#                suite, the frontend suite/build, and TypeScript typecheck.
#   rust-check  (optional, larger) — everything in `test` plus the Linux
#                system libraries Tauri's build.rs needs, so `cargo check`/
#                `cargo test` can run on the desktop/src-tauri crate.
#
# Build:
#   docker build --target test -t graf-id:test .
#   docker build --target rust-check -t graf-id:rust-check .
#
# Run (see docs/DOCKER.md for the full command list):
#   docker run --rm graf-id:test python -m pytest grafid/tests -q

# ---------------------------------------------------------------------------
# base: Python 3.12 + Node 20 (Node binaries copied from the official image
# rather than curl-piping a setup script, so the version is pinned and the
# layer is reproducible) + git (several tests skip cleanly without it, but
# real coverage needs it present).
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node:20-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version && npm --version

WORKDIR /app

# ---------------------------------------------------------------------------
# test: Python deps + editable install, then frontend deps, then the rest
# of the source. Ordered so a change to one toolchain's source doesn't
# invalidate the other toolchain's dependency-install layer.
#
# The editable install (`pip install -e`) needs the real grafid/ package on
# disk to resolve — setuptools' [tool.setuptools.packages.find] discovers it
# from the actual source tree, so pyproject.toml alone is not enough here
# (unlike a plain requirements.txt install). That means this layer reruns
# whenever Python source changes, not just when pyproject.toml changes —
# correctness over a cache trick that would need a fake stand-in package.
# ---------------------------------------------------------------------------
FROM base AS test

COPY pyproject.toml README.md ./
COPY grafid/ grafid/
RUN pip install --no-cache-dir -e ".[dev]"

COPY desktop/package.json desktop/package-lock.json desktop/
RUN cd desktop && npm ci

COPY desktop/index.html desktop/tsconfig.json desktop/tsconfig.node.json desktop/vite.config.ts desktop/
COPY desktop/src/ desktop/src/
COPY desktop/public/ desktop/public/

CMD ["python", "-m", "pytest", "grafid/tests", "-q"]

# ---------------------------------------------------------------------------
# rust-check: adds the Tauri Linux prerequisites (see tauri.app's own Linux
# setup docs — Tauri 2 needs these even just to `cargo check`, since
# tauri-build's build.rs probes them via pkg-config) and a stable Rust
# toolchain via rustup.
# ---------------------------------------------------------------------------
FROM test AS rust-check

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential curl pkg-config \
        libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev \
        librsvg2-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
        | sh -s -- -y --profile minimal --default-toolchain stable \
    && rustc --version && cargo --version

COPY desktop/src-tauri/ desktop/src-tauri/
# Tauri's bundle.resources config expects runtime/ to exist at compile time
# (mirrors the "Ensure runtime resource directory" step in .github/workflows/ci.yml —
# .dockerignore already preserves the tracked runtime/.gitkeep, this is a
# defensive fallback for any build context where it's missing).
RUN mkdir -p desktop/src-tauri/runtime && touch desktop/src-tauri/runtime/.gitkeep

WORKDIR /app/desktop/src-tauri
CMD ["cargo", "check", "--locked"]
