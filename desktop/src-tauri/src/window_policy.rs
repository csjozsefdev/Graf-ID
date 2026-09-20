use tauri::{
    PhysicalRect, Position, Size, WebviewWindow, WindowEvent,
};

pub fn cursor_recall_point(window: &WebviewWindow) -> Option<(f64, f64)> {
    window
        .cursor_position()
        .ok()
        .map(|pos| (pos.x, pos.y))
}

pub fn should_reapply_work_area_layout(
    visible: bool,
    minimized: bool,
    layout_matches: bool,
) -> bool {
    visible && !minimized && !layout_matches
}

fn target_monitor(
    window: &WebviewWindow,
    recall_point: Option<(f64, f64)>,
) -> Result<Option<tauri::Monitor>, String> {
    if let Some((x, y)) = recall_point {
        return window.monitor_from_point(x, y).map_err(|e| e.to_string());
    }

    if let Ok(Some(monitor)) = window.current_monitor() {
        return Ok(Some(monitor));
    }

    window.primary_monitor().map_err(|e| e.to_string())
}

fn window_matches_work_area(
    window: &WebviewWindow,
    work_area: &PhysicalRect<i32, u32>,
) -> bool {
    let position_matches = window.outer_position().ok().is_some_and(|pos| {
        pos.x == work_area.position.x && pos.y == work_area.position.y
    });

    let size_matches = window.outer_size().ok().is_some_and(|size| {
        size.width == work_area.size.width && size.height == work_area.size.height
    });

    position_matches && size_matches
}

fn clear_non_work_area_window_states(window: &WebviewWindow) -> Result<(), String> {
    if window.is_fullscreen().unwrap_or(false) {
        window
            .set_fullscreen(false)
            .map_err(|e| e.to_string())?;
    }

    if window.is_maximized().unwrap_or(false) {
        window.unmaximize().map_err(|e| e.to_string())?;
    }

    Ok(())
}

pub fn fill_window_work_area(
    window: &WebviewWindow,
    recall_point: Option<(f64, f64)>,
) -> Result<(), String> {
    let Some(monitor) = target_monitor(window, recall_point)? else {
        return Ok(());
    };

    let work_area = *monitor.work_area();
    clear_non_work_area_window_states(window)?;

    if window_matches_work_area(window, &work_area) {
        return Ok(());
    }

    window
        .set_position(Position::Physical(work_area.position))
        .map_err(|e| e.to_string())?;
    window
        .set_size(Size::Physical(work_area.size))
        .map_err(|e| e.to_string())?;

    Ok(())
}

pub fn present_main_window(
    window: &WebviewWindow,
    recall_point: Option<(f64, f64)>,
) -> Result<(), String> {
    window.unminimize().map_err(|e| e.to_string())?;
    window.show().map_err(|e| e.to_string())?;
    fill_window_work_area(window, recall_point)?;
    window.set_focus().map_err(|e| e.to_string())
}

pub fn apply_main_window_startup_policy(window: &WebviewWindow) -> Result<(), String> {
    window.set_decorations(false).map_err(|e| e.to_string())?;
    window.set_resizable(false).map_err(|e| e.to_string())?;
    window.set_maximizable(false).map_err(|e| e.to_string())?;
    fill_window_work_area(window, None)
}

pub fn handle_main_window_event(window: &WebviewWindow, event: &WindowEvent) {
    match event {
        WindowEvent::Resized(_)
        | WindowEvent::Moved(_)
        | WindowEvent::ScaleFactorChanged { .. } => {
            let visible = window.is_visible().unwrap_or(false);
            let minimized = window.is_minimized().unwrap_or(false);
            let layout_matches = target_monitor(window, None)
                .ok()
                .flatten()
                .map(|monitor| window_matches_work_area(window, monitor.work_area()))
                .unwrap_or(true);

            if should_reapply_work_area_layout(visible, minimized, layout_matches) {
                let _ = fill_window_work_area(window, None);
            }
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::should_reapply_work_area_layout;

    #[test]
    fn reapply_work_area_only_for_visible_non_minimized_mismatched_layout() {
        assert!(should_reapply_work_area_layout(true, false, false));
        assert!(!should_reapply_work_area_layout(true, true, false));
        assert!(!should_reapply_work_area_layout(true, false, true));
        assert!(!should_reapply_work_area_layout(false, false, false));
    }
}
