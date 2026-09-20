//! Spawn the Graf-Id Python IPC CLI and parse JSON from stdout.

use serde_json::Value;
use std::collections::HashMap;
use std::fs::OpenOptions;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Instant;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const IPC_TIMEOUT_HINT: &str = "Python IPC did not return valid JSON";

/// Win32 `CREATE_NO_WINDOW` — child process does not allocate a console.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// When true, IPC subprocesses on Windows use `CREATE_NO_WINDOW`.
fn should_suppress_ipc_console() -> bool {
    !std::env::var("GRAFID_SHOW_IPC_CONSOLE")
        .map(|v| {
            let lower = v.to_lowercase();
            matches!(lower.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
}

#[cfg(windows)]
fn apply_ipc_console_policy(cmd: &mut Command) {
    if should_suppress_ipc_console() {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
}

#[cfg(not(windows))]
fn apply_ipc_console_policy(_cmd: &mut Command) {}

fn debug_timing_enabled() -> bool {
    std::env::var("GRAFID_DEBUG_TIMING")
        .map(|v| {
            let lower = v.to_lowercase();
            matches!(lower.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
}

/// Resolve the Python executable used to run `graf-id ipc` commands.
pub fn resolve_python_executable() -> Result<PathBuf, String> {
    // Release builds: bundled runtime wins over inherited dev env vars (GRAFID_PYTHON).
    if !cfg!(debug_assertions) {
        if let Some(sidecar) = resolve_packaged_python() {
            return Ok(sidecar);
        }
    }

    // Debug builds (tauri:dev): prefer repo .venv so IPC matches current source.
    // Ignore stale GRAFID_PYTHON left over from a packaged install on the same machine.
    if cfg!(debug_assertions) {
        if let Some(venv) = resolve_dev_venv_python() {
            return Ok(venv);
        }
    }

    if let Ok(path) = std::env::var("GRAFID_PYTHON") {
        let candidate = PathBuf::from(path);
        if candidate.is_file() {
            return Ok(candidate);
        }
        if !cfg!(debug_assertions) {
            return Err(user_backend_error(&format!(
                "Configured Python runtime is missing at {}.",
                candidate.display()
            )));
        }
    }

    if let Some(sidecar) = resolve_packaged_python() {
        return Ok(sidecar);
    }

    if let Some(venv) = resolve_dev_venv_python() {
        return Ok(venv);
    }

    Err(user_backend_error(
        "The Graf-Id backend runtime is not installed. Reinstall the application or contact support.",
    ))
}

fn resolve_dev_venv_python() -> Option<PathBuf> {
    let repo_root = resolve_repo_root();
    let venv_python = repo_root.join(".venv").join("Scripts").join("python.exe");
    if venv_python.is_file() {
        return Some(venv_python);
    }
    let venv_unix = repo_root.join(".venv").join("bin").join("python");
    if venv_unix.is_file() {
        return Some(venv_unix);
    }
    None
}

fn user_backend_error(detail: &str) -> String {
    format!("backend_unavailable: {detail}")
}

/// Search bundled and install-dir layouts for embedded python.exe.
fn resolve_packaged_python() -> Option<PathBuf> {
    let mut bases: Vec<PathBuf> = Vec::new();
    if let Ok(dir) = std::env::var("GRAFID_RESOURCE_DIR") {
        bases.push(PathBuf::from(dir));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            bases.push(parent.to_path_buf());
            bases.push(parent.join("resources"));
        }
    }

    let rel_paths: &[&[&str]] = &[
        &["runtime", "python.exe"],
        &["runtime", "python", "python.exe"],
    ];

    for base in bases {
        for parts in rel_paths {
            let candidate = parts.iter().fold(base.clone(), |p, segment| p.join(segment));
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

fn is_packaged_mode() -> bool {
    // Debug shells (tauri dev) must not inherit packaged-mode env from an installed Graf-Id.
    if cfg!(debug_assertions) {
        return std::env::var("GRAFID_FORCE_PACKAGED")
            .map(|v| {
                let lower = v.to_lowercase();
                matches!(lower.as_str(), "1" | "true" | "yes" | "on")
            })
            .unwrap_or(false);
    }

    if let Ok(mode) = std::env::var("GRAFID_RUNTIME_MODE") {
        let lower = mode.to_lowercase();
        if lower == "development" || lower == "dev" {
            return false;
        }
        if lower == "packaged" || lower == "production" || lower == "release" {
            return true;
        }
    }

    resolve_packaged_python().is_some()
}

/// Writable user data directory (config, database, logs).
fn resolve_user_data_dir() -> PathBuf {
    if let Ok(local) = std::env::var("LOCALAPPDATA") {
        return PathBuf::from(local).join("Graf-Id");
    }
    if let Ok(home) = std::env::var("USERPROFILE") {
        return PathBuf::from(home).join("Graf-Id");
    }
    resolve_repo_root().join("graf-id-data")
}

/// Writable user data directory (config, database, logs).
pub fn resolve_data_dir() -> PathBuf {
    if let Ok(dir) = std::env::var("GRAFID_DATA_DIR") {
        return PathBuf::from(dir);
    }

    // Dev and packaged builds share the same per-user folder as the CLI.
    // Do not use the repo root — it often has an empty graf-id.db from earlier dev runs.
    resolve_user_data_dir()
}

/// Directory on PYTHONPATH (site-packages when bundled).
fn resolve_resource_root() -> PathBuf {
    if cfg!(debug_assertions) && resolve_dev_venv_python().is_some() {
        return resolve_repo_root();
    }

    if let Ok(root) = std::env::var("GRAFID_RESOURCE_ROOT") {
        return PathBuf::from(root);
    }

    if let Some(python) = resolve_packaged_python() {
        if let Some(runtime_dir) = python.parent() {
            let site_packages = runtime_dir.join("Lib").join("site-packages");
            if site_packages.is_dir() {
                return site_packages;
            }
            return runtime_dir.to_path_buf();
        }
    }

    resolve_repo_root()
}

fn is_valid_repo_root(dir: &Path) -> bool {
    is_repo_root(dir) && dir.is_dir()
}

/// Strip Windows verbatim `\\?\` prefix for CreateProcess current-directory.
fn normalize_spawn_directory(path: &Path) -> PathBuf {
    let mut text = path.display().to_string();
    if text.starts_with(r"\\?\UNC\") {
        text = format!(r"\\{}", &text[8..]);
    } else if text.starts_with(r"\\?\") {
        text = text[4..].to_string();
    }
    PathBuf::from(text)
}

/// Repository root — walk up from cwd and exe dir (tauri:dev cwd is often target/debug).
pub fn resolve_repo_root() -> PathBuf {
    if let Ok(root) = std::env::var("GRAFID_REPO_ROOT") {
        let candidate = PathBuf::from(root);
        if is_valid_repo_root(&candidate) {
            return candidate;
        }
    }

    let mut starts: Vec<PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        starts.push(cwd);
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            starts.push(parent.to_path_buf());
        }
    }

    for mut dir in starts {
        for _ in 0..12 {
            if is_repo_root(&dir) {
                return dir;
            }
            if !dir.pop() {
                break;
            }
        }
    }

    std::env::current_dir()
        .unwrap_or_else(|_| PathBuf::from("."))
        .parent()
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| PathBuf::from(".."))
}

fn is_repo_root(dir: &Path) -> bool {
    dir.join("grafid").join("__init__.py").is_file()
        || dir.join("pyproject.toml").is_file()
        || dir.join(".venv").join("Scripts").join("python.exe").is_file()
        || dir.join(".venv").join("bin").join("python").is_file()
}

fn ipc_subprocess_env(
    python: &Path,
    resource_root: &Path,
    data_dir: &Path,
    packaged: bool,
) -> HashMap<String, String> {
    let mut env: HashMap<String, String> = std::env::vars().collect();
    let mode = if packaged { "packaged" } else { "development" };

    if !packaged {
        env.remove("PYTHONHOME");
        env.remove("PYTHONNOUSERSITE");
        env.remove("GRAFID_PYTHON");
        env.remove("GRAFID_RUNTIME_MODE");
        env.remove("GRAFID_RESOURCE_ROOT");
    }

    env.insert("GRAFID_RUNTIME_MODE".into(), mode.into());
    env.insert("GRAFID_DATA_DIR".into(), data_dir.display().to_string());
    env.insert(
        "GRAFID_RESOURCE_ROOT".into(),
        resource_root.display().to_string(),
    );
    env.insert("PYTHONPATH".into(), resource_root.display().to_string());
    env.insert("GRAFID_PYTHON".into(), python.display().to_string());
    env.insert("PYTHONUTF8".into(), "1".into());
    env.insert("PYTHONIOENCODING".into(), "utf-8".into());
    if packaged {
        if let Some(runtime_dir) = python.parent() {
            env.insert("PYTHONHOME".into(), runtime_dir.display().to_string());
        }
        env.insert("PYTHONNOUSERSITE".into(), "1".into());
    }
    env
}

/// Apply IPC env to the child process. In dev mode, explicitly strip packaged-runtime
/// vars so inherited `PYTHONHOME` from a release smoke test cannot break `.venv`.
fn apply_ipc_subprocess_env(
    cmd: &mut Command,
    python: &Path,
    resource_root: &Path,
    data_dir: &Path,
    packaged: bool,
) {
    if !packaged {
        cmd.env_remove("PYTHONHOME");
        cmd.env_remove("PYTHONNOUSERSITE");
        cmd.env_remove("GRAFID_PYTHON");
        cmd.env_remove("GRAFID_RUNTIME_MODE");
        cmd.env_remove("GRAFID_RESOURCE_ROOT");
    }
    cmd.envs(ipc_subprocess_env(python, resource_root, data_dir, packaged));
}

fn append_backend_log(data_dir: &Path, message: &str) {
    let log_dir = data_dir.join("logs");
    if std::fs::create_dir_all(&log_dir).is_err() {
        return;
    }
    let log_path = log_dir.join("desktop-backend.log");
    let timestamp = chrono_lite_timestamp();
    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(log_path) {
        let _ = writeln!(file, "{timestamp} | {message}");
    }
}

fn chrono_lite_timestamp() -> String {
    format!("{:?}", std::time::SystemTime::now())
}

/// Run `python -m grafid.ipc <subcommand> [args...]` and return parsed JSON.
pub fn run_ipc(subcommand: &str, extra_args: &[&str]) -> Result<Value, String> {
    let ipc_start = Instant::now();
    let python = resolve_python_executable().map_err(|e| {
        let data_dir = resolve_data_dir();
        append_backend_log(&data_dir, &e);
        e
    })?;
    let resource_root = resolve_resource_root();
    let data_dir = resolve_data_dir();
    let packaged = is_packaged_mode();

    let mut args: Vec<&str> = vec!["-m", "grafid.ipc", subcommand];
    args.extend_from_slice(extra_args);

    let cwd = if packaged {
        resource_root.clone()
    } else {
        resolve_repo_root()
    };
    let spawn_cwd = normalize_spawn_directory(&cwd);
    if !spawn_cwd.is_dir() {
        let msg = user_backend_error(&format!(
            "Backend working directory is missing or invalid: {}.",
            spawn_cwd.display()
        ));
        append_backend_log(&data_dir, &msg);
        return Err(msg);
    }

    let mut cmd = Command::new(&python);
    cmd.current_dir(&spawn_cwd)
        .args(&args);
    apply_ipc_subprocess_env(
        &mut cmd,
        &python,
        &resource_root,
        &data_dir,
        packaged,
    );
    apply_ipc_console_policy(&mut cmd);

    let output = cmd.output().map_err(|e| {
            let msg = user_backend_error(&format!("Failed to start the backend process: {e}"));
            append_backend_log(
                &data_dir,
                &format!(
                    "spawn failed | python={} | cwd={} | {msg}",
                    python.display(),
                    spawn_cwd.display()
                ),
            );
            msg
        })?;

    if debug_timing_enabled() {
        append_backend_log(
            &data_dir,
            &format!(
                "ipc_timing | subcommand={subcommand} | spawned_python=true | elapsed_ms={} | ok={}",
                ipc_start.elapsed().as_millis(),
                output.status.success()
            ),
        );
    }

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let msg = format!(
            "backend_command_failed: Backend command '{subcommand}' failed. See desktop-backend.log in your Graf-Id data folder."
        );
        append_backend_log(
            &data_dir,
            &format!(
                "ipc {} exit {:?} | python={} | cwd={} | stderr={}",
                subcommand,
                output.status.code(),
                python.display(),
                cwd.display(),
                stderr.trim()
            ),
        );
        return Err(msg);
    }

    let stdout = String::from_utf8(output.stdout).map_err(|e| {
        let msg = format!("{IPC_TIMEOUT_HINT}: backend stdout was not valid UTF-8: {e}");
        append_backend_log(&data_dir, &format!("ipc {subcommand} | {msg}"));
        msg
    })?;
    let line = stdout
        .lines()
        .find(|l| !l.trim().is_empty())
        .ok_or_else(|| {
            let msg = format!("{IPC_TIMEOUT_HINT} (empty stdout)");
            append_backend_log(&data_dir, &format!("ipc {subcommand} | {msg}"));
            msg
        })?;

    serde_json::from_str(line).map_err(|e| {
        let msg = format!("{IPC_TIMEOUT_HINT}: {e}");
        append_backend_log(&data_dir, &format!("ipc {subcommand} | parse error | line={line}"));
        msg
    })
}

fn path_to_utf8_string(path: &Path) -> Result<String, String> {
    path.to_str()
        .map(str::to_owned)
        .ok_or_else(|| format!("path_not_utf8: {}", path.display()))
}

/// Patch settings payload paths from the OS (avoids mojibake from legacy Python stdout).
pub fn patch_settings_paths(mut response: serde_json::Value) -> Result<serde_json::Value, String> {
    let data_dir = resolve_data_dir();
    let logs_dir = data_dir.join("logs");
    let config_path = data_dir.join("config.json");
    let Some(data) = response
        .get_mut("data")
        .and_then(|value| value.as_object_mut())
    else {
        return Ok(response);
    };
    data.insert(
        "data_dir".into(),
        serde_json::Value::String(path_to_utf8_string(&data_dir)?),
    );
    data.insert(
        "logs_dir".into(),
        serde_json::Value::String(path_to_utf8_string(&logs_dir)?),
    );
    data.insert(
        "config_dir".into(),
        serde_json::Value::String(path_to_utf8_string(&data_dir)?),
    );
    data.insert(
        "config_path".into(),
        serde_json::Value::String(path_to_utf8_string(&config_path)?),
    );
    Ok(response)
}
