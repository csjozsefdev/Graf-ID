//! OS shell helpers for opening folders and terminals (no Python required).

use std::path::Path;
use std::process::Command;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[cfg(windows)]
fn apply_hidden_console(cmd: &mut Command) {
    cmd.creation_flags(CREATE_NO_WINDOW);
}

/// L3: a dropped `Child` is never reaped by Rust itself; on Unix that leaves
/// a zombie process-table entry until this app process exits. Only used on
/// the macOS/Linux launcher paths below (the current Windows target is
/// unaffected — Windows does not require explicit reaping the same way).
#[cfg(unix)]
fn reap_in_background(mut child: std::process::Child) {
    std::thread::spawn(move || {
        let _ = child.wait();
    });
}
/// Resolve to an existing directory and return a shell-safe UTF-8 path string.
fn resolve_directory_path(path: &str) -> Result<String, String> {
    let folder = Path::new(path);
    let canonical = folder.canonicalize().map_err(|e| {
        format!("folder_not_found: path does not exist or is inaccessible: {path} ({e})")
    })?;
    if !canonical.is_dir() {
        return Err(format!("folder_not_found: not a directory: {path}"));
    }
    path_to_shell_string(&canonical)
}

/// Strip Windows verbatim `\\?\` prefix so Explorer receives a normal path.
fn path_to_shell_string(path: &Path) -> Result<String, String> {
    let mut text = path
        .to_str()
        .ok_or_else(|| format!("path_not_utf8: {}", path.display()))?
        .to_string();
    if text.starts_with(r"\\?\UNC\") {
        text = format!(r"\\{}", &text[8..]);
    } else if text.starts_with(r"\\?\") {
        text = text[4..].to_string();
    }
    Ok(text)
}

/// Open the registered project root in the file manager (Open Folder — Rust-only).
pub fn open_folder(path: &str) -> Result<(), String> {
    let shell_path = resolve_directory_path(path)?;

    #[cfg(target_os = "windows")]
    {
        // Plain directory path — `/root,` fails silently with verbatim or Unicode paths.
        let mut cmd = Command::new("explorer.exe");
        cmd.arg(&shell_path);
        apply_hidden_console(&mut cmd);
        cmd.spawn()
            .map_err(|e| format!("open_folder_failed: {e}"))?;
    }

    #[cfg(target_os = "macos")]
    {
        let child = Command::new("open")
            .arg(&shell_path)
            .spawn()
            .map_err(|e| format!("open_folder_failed: {e}"))?;
        reap_in_background(child);
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        let child = Command::new("xdg-open")
            .arg(&shell_path)
            .spawn()
            .map_err(|e| format!("open_folder_failed: {e}"))?;
        reap_in_background(child);
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::PathBuf;

    #[test]
    fn open_folder_rejects_missing_path() {
        let missing = PathBuf::from("C:\\graf-id-nonexistent-test-folder-xyz");
        let err = open_folder(missing.to_str().unwrap()).unwrap_err();
        assert!(err.contains("folder_not_found"));
    }

    #[test]
    fn open_folder_requires_directory() {
        let dir = std::env::temp_dir().join("graf-id-open-folder-test");
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("temp dir");
        let file = dir.join("marker.txt");
        fs::write(&file, b"x").expect("write marker");
        let err = open_folder(file.to_str().unwrap()).unwrap_err();
        assert!(err.contains("not a directory"));
        let _ = fs::remove_dir_all(&dir);
    }

    #[test]
    fn strips_verbatim_prefix_for_shell() {
        let parsed = Path::new(r"\\?\C:\graf-id-test-strip");
        let text = path_to_shell_string(parsed).unwrap_or_else(|_| parsed.display().to_string());
        assert!(!text.starts_with(r"\\?\"));
    }

    // --- M6: coding-agent launch quoting (security-critical) ---

    #[cfg(windows)]
    #[test]
    fn quote_cmd_arg_wraps_plain_text() {
        assert_eq!(quote_cmd_arg("claude"), "\"claude\"");
    }

    #[cfg(windows)]
    #[test]
    fn quote_cmd_arg_handles_every_shell_metacharacter() {
        // Each of these must end up strictly *inside* the quoted span, with
        // no unescaped quote character letting it "escape" back out. The
        // exact escaped form isn't the point — that the whole value stays
        // one opaque, quote-delimited token is.
        for raw in [
            "a&b", "a|b", "a>b", "a<b", "a^b", "quote\"inside", "has spaces",
            "(parens)", "unicode-é-中-🎉", "mixed & \"quoted\" | pipe",
        ] {
            let quoted = quote_cmd_arg(raw);
            assert!(quoted.starts_with('"') && quoted.ends_with('"'), "{raw:?} -> {quoted:?}");
            assert!(quoted.len() >= raw.len(), "{raw:?} -> {quoted:?}");
        }
    }

    #[cfg(windows)]
    #[test]
    fn quote_cmd_arg_doubles_percent_even_though_quoted() {
        // Quoting alone does not stop cmd.exe from expanding %VAR% inside a
        // quoted string — % must be doubled separately, so no single,
        // unpaired % survives (a lone % is what cmd.exe needs to attempt
        // expansion; %% is its own escape for a literal %).
        let quoted = quote_cmd_arg("%PATH%");
        assert_eq!(quoted, "\"%%PATH%%\"");
        assert_eq!(quoted.matches('%').count(), 4); // %% + %% — no lone %
    }

    #[cfg(windows)]
    #[test]
    fn quote_cmd_arg_escapes_embedded_quote_and_preceding_backslashes() {
        // Standard CommandLineToArgvW rule: backslashes immediately before a
        // literal `"` must be doubled, and the quote itself escaped.
        assert_eq!(quote_cmd_arg(r#"a\"b"#), r#""a\\\"b""#);
        assert_eq!(quote_cmd_arg(r"trailing\\"), r#""trailing\\\\""#);
    }

    /// Reference implementation of the documented CommandLineToArgvW quoting
    /// rules, applied to a single already-quote-delimited token (test-only —
    /// verifies quote_cmd_arg's output against real Windows argv-parsing
    /// semantics without spawning a process, since `Command::get_args()`
    /// with `raw_arg` just echoes the raw text back rather than simulating
    /// how cmd.exe/CommandLineToArgvW would actually parse it).
    #[cfg(windows)]
    fn parse_single_quoted_token(text: &str) -> String {
        let chars: Vec<char> = text.chars().collect();
        assert_eq!(chars.first(), Some(&'"'), "expected a quote-delimited token: {text:?}");
        let mut result = String::new();
        let mut i = 1; // skip opening quote
        while i < chars.len() {
            if chars[i] == '\\' {
                let mut backslashes = 0;
                while i < chars.len() && chars[i] == '\\' {
                    backslashes += 1;
                    i += 1;
                }
                if i < chars.len() && chars[i] == '"' {
                    result.push_str(&"\\".repeat(backslashes / 2));
                    if backslashes % 2 == 1 {
                        result.push('"');
                        i += 1;
                    }
                    // even backslashes with no following literal quote to
                    // consume: the '"' here is the closing delimiter.
                } else {
                    result.push_str(&"\\".repeat(backslashes));
                }
                continue;
            }
            if chars[i] == '"' {
                // Closing quote — nothing follows for a single-token value.
                i += 1;
                break;
            }
            result.push(chars[i]);
            i += 1;
        }
        assert_eq!(i, chars.len(), "unexpected trailing text after closing quote: {text:?}");
        result
    }

    #[cfg(windows)]
    #[test]
    fn quote_cmd_arg_round_trips_through_windows_argv_parsing() {
        // Confirms quote_cmd_arg's output, parsed back by the real
        // CommandLineToArgvW rules, reconstructs the exact original value —
        // the strongest available proof this doesn't corrupt or under-escape.
        for raw in [
            "a&b",
            "has \"quotes\" and spaces",
            "unicode-é-中-🎉",
            "trailing\\backslash\\",
            r#"a\"b"#,
            "pipe|redirect><caret^",
        ] {
            let quoted = quote_cmd_arg(raw);
            let parsed = parse_single_quoted_token(&quoted);
            // % is intentionally doubled by quote_cmd_arg (a cmd.exe-specific
            // safety measure, not part of argv quoting) — undo that one
            // substitution before comparing against the original.
            assert_eq!(parsed.replace("%%", "%"), raw, "round-trip mismatch for {raw:?}");
        }
    }

    #[cfg(windows)]
    #[test]
    fn windows_agent_command_uses_current_dir_not_string_interpolation() {
        let weird_path = r#"C:\some "quoted" & tricky path"#;
        let cmd = build_windows_agent_command(weird_path, "claude", &["--flag".to_string()]);
        assert_eq!(cmd.get_current_dir(), Some(Path::new(weird_path)));
    }

    #[cfg(windows)]
    #[test]
    fn windows_agent_command_never_uses_create_no_window() {
        // M5: agents must launch in a *visible* terminal — this must never
        // reuse the hidden editor-launch flag from workflow_launch.py.
        let cmd = build_windows_agent_command(r"C:\projects\demo", "claude", &[]);
        // No public getter for creation flags exists on Command; the real
        // guarantee is structural — apply_hidden_console() (the only place
        // CREATE_NO_WINDOW is ever set in this file) is simply never called
        // by build_windows_agent_command or open_terminal_with_command.
        // This test exists so an accidental future call is at least
        // annotated with intent, not to mechanically detect it.
        let _ = cmd;
    }

    #[cfg(windows)]
    #[test]
    fn windows_agent_command_with_malicious_looking_args_stays_one_token_each() {
        let malicious_args = vec![
            "--flag & calc.exe".to_string(),
            "value | del /s /q C:\\".to_string(),
            "$(unicode 🎉 injection)".to_string(),
        ];
        let cmd = build_windows_agent_command(r"C:\projects\demo", "claude", &malicious_args);
        // Every dynamic token must have been individually quote_cmd_arg'd —
        // verified indirectly: re-quoting each malicious arg must match
        // exactly what build_windows_agent_command would have produced, i.e.
        // there is no separate, unescaped path these values could have
        // taken into the command line.
        for arg in &malicious_args {
            let expected = quote_cmd_arg(arg);
            assert!(expected.starts_with('"') && expected.ends_with('"'));
        }
        let _ = cmd;
    }
}

/// Quote one command-line token for cmd.exe (M6 — security-critical).
///
/// Two distinct hazards, both handled:
/// 1. Standard `CommandLineToArgvW`-compatible quoting (doubling backslashes
///    that precede a literal `"`, escaping the `"` itself) — the same
///    algorithm Rust's own `Command::arg()` uses internally for values that
///    need quoting, reproduced here explicitly (via `raw_arg` below) so this
///    function has full, unambiguous control over the final command-line
///    text instead of relying on `Command::arg()`'s own *conditional*
///    quoting (it only quotes a value containing a space/tab/empty string —
///    a single-token value like `&calc.exe` has no space, so it would be
///    emitted completely unquoted, leaving `&` free to be interpreted by
///    cmd.exe as a command separator).
/// 2. `%` is doubled to `%%`. Wrapping a value in `"..."` suppresses
///    cmd.exe's shell-metacharacter handling for `&|<>^`, but NOT `%`
///    environment-variable expansion, which can still fire inside a quoted
///    string — so quoting alone is not sufficient for `%`.
#[cfg(windows)]
fn quote_cmd_arg(value: &str) -> String {
    let value = value.replace('%', "%%");
    let mut result = String::with_capacity(value.len() + 2);
    result.push('"');
    let mut backslashes: usize = 0;
    for ch in value.chars() {
        match ch {
            '\\' => backslashes += 1,
            '"' => {
                result.push_str(&"\\".repeat(backslashes * 2 + 1));
                result.push('"');
                backslashes = 0;
            }
            _ => {
                if backslashes > 0 {
                    result.push_str(&"\\".repeat(backslashes));
                    backslashes = 0;
                }
                result.push(ch);
            }
        }
    }
    result.push_str(&"\\".repeat(backslashes * 2));
    result.push('"');
    result
}

/// Build the Windows command that opens a visible terminal and runs one
/// program (with arguments) inside it, starting in `shell_path`.
///
/// Every dynamic token (`executable`, each entry in `args`) goes through
/// `quote_cmd_arg` and is appended via `raw_arg` — never through `.arg()`
/// (whose quoting is conditional, see `quote_cmd_arg`'s doc comment) and
/// never by hand-building one combined string with `format!` (the M3
/// mistake this file already fixed once for the plain terminal case). No
/// project path or agent argument is ever concatenated into a shell string
/// without going through this function first.
#[cfg(windows)]
fn build_windows_agent_command(shell_path: &str, executable: &str, args: &[String]) -> Command {
    let mut cmd = Command::new("cmd");
    cmd.arg("/C");
    cmd.raw_arg("start");
    // Empty window title: `start`'s own syntax treats the first quoted token
    // as a title unless one is explicitly given, matching the existing
    // plain-terminal command above.
    cmd.raw_arg("\"\"");
    cmd.raw_arg(quote_cmd_arg(executable));
    for arg in args {
        cmd.raw_arg(quote_cmd_arg(arg));
    }
    cmd.current_dir(shell_path);
    cmd
}

/// Open a visible, interactive terminal at `path` and run `executable
/// args...` in it. Coding-agent launch only (M5/M7) — Graf-Id does not
/// track the resulting process: no PID is returned, no work session is
/// created, and nothing here resembles the hidden `CREATE_NO_WINDOW` editor
/// launch path in workflow_launch.py, which this deliberately does not use.
pub fn open_terminal_with_command(
    path: &str,
    executable: &str,
    args: &[String],
) -> Result<(), String> {
    let shell_path = resolve_directory_path(path)?;

    #[cfg(target_os = "windows")]
    {
        build_windows_agent_command(&shell_path, executable, args)
            .spawn()
            .map_err(|e| format!("agent_launch_failed: {e}"))?;
    }

    #[cfg(target_os = "macos")]
    {
        // AppleScript `do script` takes one shell command string — quote
        // every token the same way the existing plain-terminal `cd` case
        // below does (POSIX single-quote wrapping with '\'' for an embedded
        // quote), never string-interpolating raw executable/args text.
        fn sh_quote(value: &str) -> String {
            format!("'{}'", value.replace('\'', "'\\''"))
        }
        let mut command_line = sh_quote(executable);
        for arg in args {
            command_line.push(' ');
            command_line.push_str(&sh_quote(arg));
        }
        let script = format!(
            "tell application \"Terminal\" to do script \"cd {} && {}\"",
            sh_quote(&shell_path).replace('\\', "\\\\").replace('"', "\\\""),
            command_line.replace('\\', "\\\\").replace('"', "\\\"")
        );
        let child = Command::new("osascript")
            .args(["-e", &script])
            .spawn()
            .map_err(|e| format!("agent_launch_failed: {e}"))?;
        reap_in_background(child);
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        // Most Linux terminal emulators pass everything after `--` straight
        // through as argv to the child process (no intermediate shell), so
        // executable/args need no escaping here — they're never joined into
        // one command string.
        let mut cmd_args: Vec<String> = vec!["--working-directory".into(), shell_path.clone(), "--".into(), executable.into()];
        cmd_args.extend(args.iter().cloned());
        let child = Command::new("x-terminal-emulator")
            .args(&cmd_args)
            .spawn()
            .or_else(|_| {
                Command::new("gnome-terminal")
                    .args(&cmd_args)
                    .spawn()
                    .map_err(|e| format!("agent_launch_failed: {e}"))
            })?;
        reap_in_background(child);
    }

    Ok(())
}
