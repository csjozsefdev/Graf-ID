mod process_probe;
mod python;
mod shell;
mod window_policy;

use serde_json::Value;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager};

const TRAY_MENU_SHOW: &str = "tray_show";
const TRAY_MENU_QUIT: &str = "tray_quit";

fn main_webview_window(app: &AppHandle) -> Result<tauri::WebviewWindow, String> {
    app.get_webview_window("main")
        .ok_or_else(|| "main_window_missing".to_string())
}

fn show_main_window_impl(app: &AppHandle) -> Result<(), String> {
    let window = main_webview_window(app)?;
    let recall_point = window_policy::cursor_recall_point(&window);
    window_policy::present_main_window(&window, recall_point)
}

#[tauri::command]
fn hide_main_window(app: AppHandle) -> Result<(), String> {
    main_webview_window(&app)?.hide().map_err(|e| e.to_string())
}

#[tauri::command]
fn show_main_window(app: AppHandle) -> Result<(), String> {
    show_main_window_impl(&app)
}

#[tauri::command]
fn quit_app(app: AppHandle) {
    app.exit(0);
}

fn setup_system_tray(app: &AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    let show_item = MenuItem::with_id(
        app,
        TRAY_MENU_SHOW,
        "Show Graf-Id",
        true,
        None::<&str>,
    )?;
    let quit_item = MenuItem::with_id(
        app,
        TRAY_MENU_QUIT,
        "Quit Graf-Id",
        true,
        None::<&str>,
    )?;
    let menu = Menu::with_items(app, &[&show_item, &quit_item])?;
    let icon = app
        .default_window_icon()
        .cloned()
        .ok_or("tray_icon_missing")?;

    TrayIconBuilder::new()
        .icon(icon)
        .menu(&menu)
        .tooltip("Graf-Id")
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id.as_ref() {
            TRAY_MENU_SHOW => {
                let _ = show_main_window_impl(app);
            }
            TRAY_MENU_QUIT => {
                app.exit(0);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::DoubleClick {
                button: MouseButton::Left,
                ..
            } = event
            {
                let _ = show_main_window_impl(tray.app_handle());
            }
        })
        .build(app)?;

    Ok(())
}

#[tauri::command]
fn ipc_bootstrap() -> Result<Value, String> {
    python::run_ipc("bootstrap", &[])
}

#[tauri::command]
fn ipc_project_detail(project_id: u32) -> Result<Value, String> {
    let id = project_id.to_string();
    python::run_ipc("project-detail", &[id.as_str()])
}

#[tauri::command]
fn ipc_project_history(project_id: u32) -> Result<Value, String> {
    let id = project_id.to_string();
    python::run_ipc("project-history", &[id.as_str()])
}

#[tauri::command]
fn ipc_export_project_summary(
    project_id: u32,
    export_format: String,
    output_path: Option<String>,
) -> Result<Value, String> {
    let id = project_id.to_string();
    let format_value = export_format;
    let mut args: Vec<String> = vec![id, "--format".into(), format_value];
    if let Some(path) = output_path {
        args.push("--path".into());
        args.push(path);
    }
    let arg_refs: Vec<&str> = args.iter().map(String::as_str).collect();
    python::run_ipc("export-project-summary", &arg_refs)
}

#[tauri::command]
fn ipc_export_grafitalk_inbox(output_dir: String) -> Result<Value, String> {
    python::run_ipc("export-grafitalk-inbox", &[output_dir.as_str()])
}

#[tauri::command]
fn ipc_preview_context_import(project_id: u32, file_path: String) -> Result<Value, String> {
    let id = project_id.to_string();
    python::run_ipc("preview-context-import", &[id.as_str(), file_path.as_str()])
}

#[tauri::command]
fn ipc_apply_context_import(
    project_id: u32,
    file_path: String,
    mode: String,
    fingerprint: String,
    confirmed: bool,
) -> Result<Value, String> {
    let id = project_id.to_string();
    let mut args: Vec<&str> = vec![
        id.as_str(),
        file_path.as_str(),
        "--mode",
        mode.as_str(),
        "--fingerprint",
        fingerprint.as_str(),
    ];
    if confirmed {
        args.push("--confirm");
    }
    python::run_ipc("apply-context-import", &args)
}

#[tauri::command]
fn ipc_create_backup(output_path: String, include_settings: bool) -> Result<Value, String> {
    let mut args: Vec<&str> = vec![output_path.as_str()];
    if include_settings {
        args.push("--include-settings");
    }
    python::run_ipc("create-backup", &args)
}

#[tauri::command]
fn ipc_restore_backup(backup_path: String, restore_settings: bool) -> Result<Value, String> {
    let mut args: Vec<&str> = vec![backup_path.as_str()];
    if restore_settings {
        args.push("--restore-settings");
    }
    python::run_ipc("restore-backup", &args)
}

#[tauri::command]
fn ipc_detect_build_caches(project_id: u32) -> Result<Value, String> {
    let id = project_id.to_string();
    python::run_ipc("detect-build-caches", &[id.as_str()])
}

#[tauri::command]
fn ipc_clean_build_cache(project_id: u32, manifest_path: String) -> Result<Value, String> {
    let id = project_id.to_string();
    python::run_ipc(
        "clean-build-cache",
        &[id.as_str(), "--manifest-path", manifest_path.as_str()],
    )
}

#[tauri::command]
fn ipc_open_project(project_id: u32) -> Result<Value, String> {
    let id = project_id.to_string();
    python::run_ipc("open-project", &[id.as_str()])
}

#[tauri::command]
fn ipc_app_settings() -> Result<Value, String> {
    let response = python::run_ipc("app-settings", &[])?;
    python::patch_settings_paths(response)
}

#[tauri::command]
fn ipc_close_session(
    project_id: u32,
    exit_note: Option<String>,
    unfinished: Option<String>,
    blocker: Option<String>,
    next_step: Option<String>,
    skip_notes: bool,
) -> Result<Value, String> {
    let pid = project_id.to_string();
    let mut args: Vec<&str> = vec![pid.as_str()];
    let exit_value;
    if let Some(ref v) = exit_note {
        if !v.trim().is_empty() {
            exit_value = v.clone();
            args.push("--exit-note");
            args.push(exit_value.as_str());
        }
    }
    let unfinished_value;
    if let Some(ref v) = unfinished {
        if !v.trim().is_empty() {
            unfinished_value = v.clone();
            args.push("--unfinished");
            args.push(unfinished_value.as_str());
        }
    }
    let blocker_value;
    if let Some(ref v) = blocker {
        if !v.trim().is_empty() {
            blocker_value = v.clone();
            args.push("--blocker");
            args.push(blocker_value.as_str());
        }
    }
    let next_value;
    if let Some(ref v) = next_step {
        if !v.trim().is_empty() {
            next_value = v.clone();
            args.push("--next-step");
            args.push(next_value.as_str());
        }
    }
    if skip_notes {
        args.push("--skip-notes");
    }
    python::run_ipc("close-session", &args)
}

#[tauri::command]
fn ipc_refresh_resume(project_id: u32, git_only: Option<bool>) -> Result<Value, String> {
    let id = project_id.to_string();
    let mut args: Vec<&str> = vec![id.as_str()];
    if git_only == Some(true) {
        args.push("--git-only");
    }
    python::run_ipc("refresh-resume", &args)
}

#[tauri::command]
fn ipc_save_app_settings(
    opener: String,
    usage_journal: bool,
    debug_timing: bool,
    compact_mode: bool,
    python_interpreter_mode: Option<String>,
    python_interpreter_custom_path: Option<String>,
    custom_opener_path: Option<String>,
    coding_agents: Option<String>,
    builtin_agents: Option<String>,
) -> Result<Value, String> {
    let uj = if usage_journal { "true" } else { "false" };
    let dt = if debug_timing { "true" } else { "false" };
    let cm = if compact_mode { "true" } else { "false" };
    let mut args: Vec<&str> = vec![
        "--opener",
        opener.as_str(),
        "--usage-journal",
        uj,
        "--debug-timing",
        dt,
        "--compact-mode",
        cm,
    ];
    let mode_value;
    if let Some(mode) = python_interpreter_mode.as_ref().filter(|s| !s.trim().is_empty()) {
        mode_value = mode.clone();
        args.push("--python-interpreter-mode");
        args.push(mode_value.as_str());
    }
    let interpreter_path_value;
    if let Some(path) = python_interpreter_custom_path
        .as_ref()
        .filter(|s| !s.trim().is_empty())
    {
        interpreter_path_value = path.clone();
        args.push("--python-interpreter-custom-path");
        args.push(interpreter_path_value.as_str());
    }
    let opener_path_value;
    if let Some(path) = custom_opener_path.as_ref().filter(|s| !s.trim().is_empty()) {
        opener_path_value = path.clone();
        args.push("--custom-opener-path");
        args.push(opener_path_value.as_str());
    }
    let coding_agents_value;
    if let Some(agents_json) = coding_agents.as_ref() {
        coding_agents_value = agents_json.clone();
        args.push("--coding-agents");
        args.push(coding_agents_value.as_str());
    }
    let builtin_agents_value;
    if let Some(builtin_json) = builtin_agents.as_ref() {
        builtin_agents_value = builtin_json.clone();
        args.push("--builtin-agents");
        args.push(builtin_agents_value.as_str());
    }
    python::run_ipc("save-app-settings", &args)
}

#[tauri::command]
fn ipc_reset_app_settings() -> Result<Value, String> {
    python::run_ipc("reset-app-settings", &[])
}

#[tauri::command]
fn ipc_add_project(name: String, path: String, category: Option<String>) -> Result<Value, String> {
    let mut args: Vec<&str> = vec![name.as_str(), path.as_str()];
    let category_value;
    if let Some(ref cat) = category {
        if !cat.trim().is_empty() {
            category_value = cat.clone();
            args.push("--category");
            args.push(category_value.as_str());
        }
    }
    python::run_ipc("add-project", &args)
}

#[tauri::command]
fn ipc_remove_project(project_id: u32) -> Result<Value, String> {
    let pid = project_id.to_string();
    python::run_ipc("remove-project", &[pid.as_str()])
}

#[tauri::command]
fn ipc_reorder_projects(project_ids: Vec<u32>) -> Result<Value, String> {
    let joined = project_ids
        .iter()
        .map(|id| id.to_string())
        .collect::<Vec<_>>()
        .join(",");
    python::run_ipc("reorder-projects", &[joined.as_str()])
}

/// Open Folder boundary: show the registered project root in Explorer only.
/// Rust-only — no Python IPC, no DB/session updates, no subfolder navigation.
#[tauri::command]
fn open_project_folder(path: String) -> Result<(), String> {
    shell::open_folder(&path)
}

/// Resolve a coding agent + registered project into a launch spec
/// (executable/args/cwd). Read-only — does not launch anything and does not
/// touch sessions (M7).
#[tauri::command]
fn ipc_resolve_coding_agent_launch(agent_id: String, project_id: u32) -> Result<Value, String> {
    let id = project_id.to_string();
    python::run_ipc("resolve-coding-agent-launch", &[agent_id.as_str(), id.as_str()])
}

/// Launch a coding agent in a visible terminal at `cwd`. Rust-only — no
/// Python IPC call for the spawn itself, no PID returned, no process
/// tracking of any kind (M7). Never uses the hidden CREATE_NO_WINDOW editor
/// launch path.
#[tauri::command]
fn launch_coding_agent(cwd: String, executable: String, args: Vec<String>) -> Result<(), String> {
    shell::open_terminal_with_command(&cwd, &executable, &args)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            if let Ok(resource_dir) = app.path().resource_dir() {
                std::env::set_var("GRAFID_RESOURCE_DIR", resource_dir.to_string_lossy().to_string());
            }
            setup_system_tray(app.handle())?;
            if let Some(window) = app.get_webview_window("main") {
                window_policy::apply_main_window_startup_policy(&window)?;
                let window_for_events = window.clone();
                window.on_window_event(move |event| {
                    window_policy::handle_main_window_event(&window_for_events, &event);
                });
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            hide_main_window,
            show_main_window,
            quit_app,
            ipc_bootstrap,
            ipc_project_detail,
            ipc_project_history,
            ipc_export_project_summary,
            ipc_export_grafitalk_inbox,
            ipc_create_backup,
            ipc_preview_context_import,
            ipc_apply_context_import,
            ipc_restore_backup,
            ipc_detect_build_caches,
            ipc_clean_build_cache,
            ipc_open_project,
            ipc_app_settings,
            ipc_refresh_resume,
            ipc_close_session,
            ipc_save_app_settings,
            ipc_reset_app_settings,
            ipc_add_project,
            ipc_remove_project,
            ipc_reorder_projects,
            open_project_folder,
            ipc_resolve_coding_agent_launch,
            launch_coding_agent,
            process_probe::probe_editor_process,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Graf-Id desktop");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tray_menu_ids_are_stable() {
        assert_eq!(TRAY_MENU_SHOW, "tray_show");
        assert_eq!(TRAY_MENU_QUIT, "tray_quit");
    }
}
