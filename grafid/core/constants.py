"""Shared application constants."""

CONFIG_DIR_NAME = "Graf-Id"
CONFIG_FILENAME = "config.json"
DB_FILENAME = "graf-id.db"
LOG_DIR_NAME = "logs"
LOG_FILENAME = "graf-id.log"
SCHEMA_VERSION = 12

# Scanner defaults (Milestone 2A)
SCAN_MAX_FILE_SIZE_BYTES = 512 * 1024
SCAN_MAX_DEPTH = 8
SCAN_PREVIEW_MAX_CHARS = 200

# Scanner resource limits (Milestone 5 — M7): a pathological tree (huge
# unignored directory, extreme fan-out/depth) can no longer make a scan run
# or consume memory without bound. Generous enough to never trigger on a
# normal project.
SCAN_MAX_FILES = 50_000
SCAN_MAX_SECONDS = 60.0
SCAN_MAX_WARNINGS = 200

# Git status/log parsing limits (Milestone 5 — L2): bounds how much a
# pathological repo (huge uncommitted change set, absurdly long commit
# subject) can inflate collected git state.
GIT_MAX_STATUS_ENTRIES = 500
GIT_MAX_SUBJECT_CHARS = 300

# Free-text field length limit (Milestone 5B — real audit finding L1):
# applies uniformly to project notes and session exit_note/blocker/next_step.
# Enforced only at the write boundary (raises, never silently truncates);
# existing stored data longer than this is left untouched and still reads
# back and displays normally.
MAX_FREE_TEXT_FIELD_CHARS = 4_000
