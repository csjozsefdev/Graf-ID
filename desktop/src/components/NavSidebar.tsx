import type { DashboardProject, NavSection } from "../ipc/types";
import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../utils/grafiHelpRegistry";
import { ProjectDashboard } from "./ProjectDashboard";

interface NavSidebarProps {
  section: NavSection;
  onNav: (section: NavSection) => void;
  hasProjects: boolean;
  projects: DashboardProject[];
  selectedId: number | null;
  onSelectProject: (id: number) => void;
  onAddProject: () => void;
  onRemoveProject: (project: DashboardProject) => void;
  onReorderProjects: (orderedIds: number[]) => Promise<void>;
}

const NAV_ITEMS: { id: NavSection; label: string }[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "history", label: "History" },
  { id: "settings", label: "Settings" },
];

export function NavSidebar({
  section,
  onNav,
  hasProjects,
  projects,
  selectedId,
  onSelectProject,
  onAddProject,
  onRemoveProject,
  onReorderProjects,
}: NavSidebarProps) {
  return (
    <aside className="sidebar" aria-label="Navigation">
      <nav className="sidebar__nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={
              section === item.id ? "sidebar__nav-btn sidebar__nav-btn--active" : "sidebar__nav-btn"
            }
            onClick={() => onNav(item.id)}
            {...grafiHelpProps(
              item.id === "history"
                ? GRAFI_HELP_TOPIC.HISTORY
                : item.id === "settings"
                  ? GRAFI_HELP_TOPIC.SETTINGS
                  : GRAFI_HELP_TOPIC.DASHBOARD
            )}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {hasProjects ? (
        <ProjectDashboard
          projects={projects}
          selectedId={selectedId}
          onSelect={onSelectProject}
          onAddProject={onAddProject}
          onRemoveProject={onRemoveProject}
          onReorder={(orderedIds) => onReorderProjects(orderedIds)}
        />
      ) : (
        <p className="sidebar__hint muted">
          Add a project to start tracking where you left off.
        </p>
      )}
    </aside>
  );
}
