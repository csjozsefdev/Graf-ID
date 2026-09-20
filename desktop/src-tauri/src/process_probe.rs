//! Runtime probes for editor process lifecycle (session-end detection).
//! Uses Win32 APIs on Windows — no `tasklist` / `taskkill` subprocess polling.

use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

use serde::Serialize;

#[derive(Debug, Serialize, PartialEq, Eq)]
pub struct EditorProcessProbe {
    pub launcher_pid: Option<u32>,
    pub launcher_pid_alive: bool,
    pub editor_image: Option<String>,
    pub editor_process_count: u32,
}

/// PID -> creation timestamp (Windows FILETIME ticks) of the process we last confirmed
/// alive at that PID. Guards against PID reuse: Windows recycles PIDs, so a bare
/// `OpenProcess` success some time after the original launch could silently be a
/// different, unrelated process that happened to get the same PID (M6).
fn pid_creation_cache() -> &'static Mutex<HashMap<u32, u64>> {
    static CACHE: OnceLock<Mutex<HashMap<u32, u64>>> = OnceLock::new();
    CACHE.get_or_init(|| Mutex::new(HashMap::new()))
}

/// True when `creation_ticks` for `pid` matches what we last observed for that PID
/// (same process, still alive), or when this is the first time we've seen `pid` (the
/// PID was only just handed to us by a fresh spawn, so trusting first sight is safe).
/// False when `pid` previously belonged to a process with a *different* creation time —
/// that process is gone and the PID has been recycled by something else. Pure/testable
/// without any OS calls; the only Windows-specific part is obtaining `creation_ticks`.
fn check_and_update_creation_cache(cache: &mut HashMap<u32, u64>, pid: u32, creation_ticks: u64) -> bool {
    match cache.get(&pid) {
        Some(&known) if known == creation_ticks => true,
        Some(_) => {
            // Recycled — rebase the cache to the new occupant so a legitimate future
            // probe of *that* process behaves correctly, but this call reports dead.
            cache.insert(pid, creation_ticks);
            false
        }
        None => {
            cache.insert(pid, creation_ticks);
            true
        }
    }
}

fn editor_image_name(editor: &str) -> Option<&'static str> {
    match editor {
        "cursor" => Some("Cursor.exe"),
        "vscode" => Some("Code.exe"),
        "pycharm" => Some("pycharm64.exe"),
        "intellij" => Some("idea64.exe"),
        "visualstudio" => Some("devenv.exe"),
        "notepadpp" => Some("notepad++.exe"),
        _ => None,
    }
}

#[cfg(windows)]
#[repr(C)]
#[derive(Clone, Copy, Default)]
struct FileTime {
    dw_low_date_time: u32,
    dw_high_date_time: u32,
}

#[cfg(windows)]
impl FileTime {
    fn as_u64(&self) -> u64 {
        ((self.dw_high_date_time as u64) << 32) | (self.dw_low_date_time as u64)
    }
}

#[cfg(windows)]
fn is_pid_alive(pid: u32) -> bool {
    extern "system" {
        fn OpenProcess(dwDesiredAccess: u32, bInheritHandle: i32, dwProcessId: u32) -> *mut std::ffi::c_void;
        fn CloseHandle(hObject: *mut std::ffi::c_void) -> i32;
        fn GetProcessTimes(
            h_process: *mut std::ffi::c_void,
            lp_creation_time: *mut FileTime,
            lp_exit_time: *mut FileTime,
            lp_kernel_time: *mut FileTime,
            lp_user_time: *mut FileTime,
        ) -> i32;
    }
    const PROCESS_QUERY_LIMITED_INFORMATION: u32 = 0x1000;
    if pid == 0 {
        return false;
    }
    let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
    if handle.is_null() {
        // Not running (or inaccessible) — not alive; forget any cached identity.
        if let Ok(mut cache) = pid_creation_cache().lock() {
            cache.remove(&pid);
        }
        return false;
    }

    let mut creation = FileTime::default();
    let mut exit = FileTime::default();
    let mut kernel = FileTime::default();
    let mut user = FileTime::default();
    let got_times = unsafe {
        GetProcessTimes(handle, &mut creation, &mut exit, &mut kernel, &mut user) != 0
    };
    unsafe {
        CloseHandle(handle);
    }

    if !got_times {
        // Couldn't confirm identity — fail safe rather than trusting a bare PID match,
        // which is exactly the TOCTOU gap PID-reuse checking exists to close.
        // M9 (found during re-audit): this path used to report "not alive" without
        // evicting the cached creation-time entry the way the null-handle branch
        // above does. If this GetProcessTimes failure was transient (the process is
        // in fact still running), the stale entry survives; a later successful probe
        // of the *same still-running* process would then see a "known" creation time
        // for that PID and — since it matches — report alive as expected, so the
        // window this actually causes wrong behavior in is one immediate transient
        // "not alive" report. Evicting here, exactly like the null-handle branch,
        // removes that asymmetry.
        if let Ok(mut cache) = pid_creation_cache().lock() {
            cache.remove(&pid);
        }
        return false;
    }

    match pid_creation_cache().lock() {
        Ok(mut cache) => check_and_update_creation_cache(&mut cache, pid, creation.as_u64()),
        Err(_) => true,
    }
}

#[cfg(not(windows))]
fn is_pid_alive(pid: u32) -> bool {
    // POSIX kill(2)/kill(1) treats pid 0 as "signal my own process group",
    // not "the process with id 0" — so `kill -0 0` always succeeds via the
    // caller's own group, unlike Windows' OpenProcess(pid=0), which fails.
    // Mirror the Windows branch's explicit guard so both platforms agree
    // that pid 0 (never a real launcher PID) is never "alive" (Docker M2b).
    if pid == 0 {
        return false;
    }
    use std::process::Command;
    Command::new("kill")
        .args(["-0", &pid.to_string()])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

#[cfg(windows)]
fn count_image_processes(image: &str) -> u32 {
    use std::ffi::c_void;
    use std::mem::{size_of, zeroed};

    #[link(name = "kernel32")]
    extern "system" {
        fn CreateToolhelp32Snapshot(dwFlags: u32, th32ProcessID: u32) -> *mut c_void;
        fn Process32FirstW(hSnapshot: *mut c_void, lppe: *mut PROCESSENTRY32W) -> i32;
        fn Process32NextW(hSnapshot: *mut c_void, lppe: *mut PROCESSENTRY32W) -> i32;
        fn CloseHandle(hObject: *mut c_void) -> i32;
    }

    const TH32CS_SNAPPROCESS: u32 = 0x0000_0002;
    const INVALID_HANDLE_VALUE: isize = -1;

    #[repr(C)]
    struct PROCESSENTRY32W {
        dw_size: u32,
        cnt_usage: u32,
        th32_process_id: u32,
        th32_default_heap_id: usize,
        th32_module_id: u32,
        cnt_threads: u32,
        th32_parent_process_id: u32,
        pc_pri_class_base: i32,
        dw_flags: u32,
        sz_exe_file: [u16; 260],
    }

    let target = image.to_ascii_lowercase();
    let snapshot = unsafe { CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) };
    if snapshot as isize == INVALID_HANDLE_VALUE {
        return 0;
    }

    let mut count = 0u32;
    let mut entry: PROCESSENTRY32W = unsafe { zeroed() };
    entry.dw_size = size_of::<PROCESSENTRY32W>() as u32;

    let mut has_entry = unsafe { Process32FirstW(snapshot, &mut entry) != 0 };
    while has_entry {
        let end = entry
            .sz_exe_file
            .iter()
            .position(|&ch| ch == 0)
            .unwrap_or(entry.sz_exe_file.len());
        let exe = String::from_utf16_lossy(&entry.sz_exe_file[..end]).to_ascii_lowercase();
        if exe == target {
            count += 1;
        }
        has_entry = unsafe { Process32NextW(snapshot, &mut entry) != 0 };
    }

    unsafe {
        CloseHandle(snapshot);
    }
    count
}

#[cfg(not(windows))]
fn count_image_processes(image: &str) -> u32 {
    use std::process::Command;
    let output = Command::new("pgrep")
        .args(["-fc", image])
        .output();
    let Ok(output) = output else {
        return 0;
    };
    String::from_utf8_lossy(&output.stdout)
        .trim()
        .parse::<u32>()
        .unwrap_or(0)
}

pub fn probe_editor_processes(
    launcher_pid: Option<u32>,
    editor: Option<&str>,
) -> EditorProcessProbe {
    let launcher_pid_alive = launcher_pid.map(is_pid_alive).unwrap_or(false);
    let editor_image = editor.and_then(|e| editor_image_name(e)).map(str::to_string);
    let editor_process_count = editor_image
        .as_deref()
        .map(count_image_processes)
        .unwrap_or(0);

    EditorProcessProbe {
        launcher_pid,
        launcher_pid_alive,
        editor_image,
        editor_process_count,
    }
}

#[tauri::command]
pub fn probe_editor_process(
    launcher_pid: Option<u32>,
    editor: Option<String>,
) -> Result<EditorProcessProbe, String> {
    Ok(probe_editor_processes(launcher_pid, editor.as_deref()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn probe_without_editor_returns_zero_count() {
        let probe = probe_editor_processes(Some(1), None);
        assert_eq!(probe.editor_process_count, 0);
        assert!(probe.editor_image.is_none());
    }

    #[test]
    fn probe_maps_editor_token_to_image_name() {
        let probe = probe_editor_processes(None, Some("cursor"));
        assert_eq!(probe.editor_image.as_deref(), Some("Cursor.exe"));
    }

    #[test]
    fn dead_launcher_pid_is_not_alive() {
        let probe = probe_editor_processes(Some(0), Some("cursor"));
        assert!(!probe.launcher_pid_alive);
    }

    // --- Docker M2b: is_pid_alive(0) parity between the Windows and
    // non-Windows branches (the non-Windows `kill -0 0` fallback used to
    // report pid 0 as "alive" due to POSIX's own-process-group broadcast
    // semantics for pid 0, unlike Windows' explicit `pid == 0` guard) ---

    #[test]
    fn pid_zero_is_never_alive() {
        assert!(!is_pid_alive(0));
    }

    #[test]
    fn current_process_pid_is_alive() {
        assert!(is_pid_alive(std::process::id()));
    }

    // A third case ("a just-exited PID reports not-alive") was tried here
    // and dropped: Windows reuses exited PIDs fast enough — especially with
    // `cargo test`'s parallel test threads spawning/exiting processes
    // concurrently — that it failed on the very first host run (a different,
    // real process had already taken the just-freed PID by the time
    // is_pid_alive() checked it). Not stably testable, so left out rather
    // than kept as a flaky test (Docker M2b).

    // --- M6: PID-reuse / TOCTOU protection (check_and_update_creation_cache) ---

    #[test]
    fn first_observation_of_a_pid_is_trusted() {
        let mut cache = HashMap::new();
        assert!(check_and_update_creation_cache(&mut cache, 4242, 1_000));
        assert_eq!(cache.get(&4242), Some(&1_000));
    }

    #[test]
    fn same_pid_same_creation_time_stays_alive_across_repeated_polls() {
        let mut cache = HashMap::new();
        assert!(check_and_update_creation_cache(&mut cache, 4242, 1_000));
        assert!(check_and_update_creation_cache(&mut cache, 4242, 1_000));
        assert!(check_and_update_creation_cache(&mut cache, 4242, 1_000));
    }

    #[test]
    fn recycled_pid_with_different_creation_time_is_reported_not_alive() {
        // Simulates: we launched a process at PID 4242 (creation tick 1_000), it exited,
        // and Windows later reused PID 4242 for a completely unrelated process
        // (creation tick 5_000). A bare OpenProcess-succeeds check would wrongly say
        // "still alive"; the creation-time cross-check must catch the swap.
        let mut cache = HashMap::new();
        assert!(check_and_update_creation_cache(&mut cache, 4242, 1_000));
        assert!(!check_and_update_creation_cache(&mut cache, 4242, 5_000));
    }

    #[test]
    fn cache_rebases_to_the_new_occupant_after_a_recycle_is_detected() {
        // After a recycle is flagged (not-alive for the launched process), the cache
        // should track the new occupant from then on, so it doesn't repeatedly flag
        // that same still-consistent new process as "different" on every subsequent poll.
        let mut cache = HashMap::new();
        assert!(check_and_update_creation_cache(&mut cache, 4242, 1_000));
        assert!(!check_and_update_creation_cache(&mut cache, 4242, 5_000));
        assert!(check_and_update_creation_cache(&mut cache, 4242, 5_000));
    }

    #[test]
    fn distinct_pids_are_tracked_independently() {
        let mut cache = HashMap::new();
        assert!(check_and_update_creation_cache(&mut cache, 100, 1_000));
        assert!(check_and_update_creation_cache(&mut cache, 200, 2_000));
        assert!(check_and_update_creation_cache(&mut cache, 100, 1_000));
        assert!(check_and_update_creation_cache(&mut cache, 200, 2_000));
    }
}
