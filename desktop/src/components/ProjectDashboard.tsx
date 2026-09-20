import { useEffect, useMemo, useState, type DragEvent } from "react";
import type { DashboardProject } from "../ipc/types";
import {
  formatTimeSince,
  sidebarGitChip,
  sidebarSessionChip,
  sidebarSummaryPreviewText,
} from "../utils/continuity";
import {
  applyFilteredReorder,
  applyReorder,
  initializeSidebarOrderIds,
  sortProjectsForSidebar,
} from "../utils/projectOrdering";
import {
  PROJECT_CATEGORIES,
  groupProjectsByCategory,
} from "../utils/projectCategories";
import { GRAFI_HELP_TOPIC, grafiHelpProps } from "../utils/grafiHelpRegistry";
import { PROJECT_STATUSES, statusLabel } from "../utils/projectStatus";

interface ProjectDashboardProps {
  projects: DashboardProject[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onAddProject: () => void;
  onRemoveProject: (project: DashboardProject) => void;
  onReorder: (orderedIds: number[]) => Promise<void>;
}

function ProjectListItem({
  project,
  isSelected,
  menuOpen,
  onSelect,
  onMenuToggle,
  onRemoveProject,
  draggable,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: {
  project: DashboardProject;
  isSelected: boolean;
  menuOpen: boolean;
  onSelect: (id: number) => void;
  onMenuToggle: (projectId: number) => void;
  onRemoveProject: (project: DashboardProject) => void;
  draggable: boolean;
  onDragStart: (projectId: number) => void;
  onDragOver: (event: DragEvent<HTMLDivElement>, projectId: number) => void;
  onDrop: (event: DragEvent<HTMLDivElement>, projectId: number) => void;
  onDragEnd: () => void;
}) {
  const summary = sidebarSummaryPreviewText(project);
  const sessionChip = sidebarSessionChip(project.latest_session);
  const gitChip = sidebarGitChip(project.git_status?.state);
  const lastOpened = formatTimeSince(project.last_opened_at);
  const menuId = `project-menu-${project.id}`;

  return (
    <div
      className={
        isSelected
          ? "project-dashboard__row project-dashboard__row--active"
          : "project-dashboard__row"
      }
      {...grafiHelpProps(GRAFI_HELP_TOPIC.PROJECT_SELECT)}
      draggable={draggable}
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", String(project.id));
        onDragStart(project.id);
      }}
      onDragOver={(event) => onDragOver(event, project.id)}
      onDrop={(event) => onDrop(event, project.id)}
      onDragEnd={onDragEnd}
    >
      <button
        type="button"
        className="project-dashboard__drag-handle"
        aria-label={`Reorder ${project.name}`}
        draggable={draggable}
        onDragStart={(event) => {
          event.stopPropagation();
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", String(project.id));
          onDragStart(project.id);
        }}
      >
        ⋮⋮
      </button>
      <button
        type="button"
        role="option"
        aria-selected={isSelected}
        className="project-dashboard__item"
        onClick={() => onSelect(project.id)}
      >
        <span className="project-dashboard__item-name" title={project.name}>
          {project.name}
        </span>
        <span className="project-dashboard__item-summary">{summary}</span>
        <span className="sidebar__project-meta" aria-label="Project status">
          <span
            className={`sidebar__project-chip sidebar__project-chip--session${
              sessionChip === "Active" ? " sidebar__project-chip--session-active" : ""
            }`}
          >
            {sessionChip}
          </span>
          <span
            className={`sidebar__project-chip sidebar__project-chip--git sidebar__project-chip--git-${gitChip === "Dirty" ? "dirty" : gitChip === "Clean" ? "clean" : "none"}`}
          >
            {gitChip}
          </span>
          {lastOpened ? (
            <span className="sidebar__project-chip sidebar__project-chip--time">{lastOpened}</span>
          ) : null}
        </span>
      </button>

      <div className="project-dashboard__menu-wrap">
        <button
          type="button"
          className="project-dashboard__menu-trigger"
          aria-label={`Project actions for ${project.name}`}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-controls={menuOpen ? menuId : undefined}
          onClick={(event) => {
            event.stopPropagation();
            onMenuToggle(project.id);
          }}
        >
          ⋯
        </button>
        {menuOpen ? (
          <div
            id={menuId}
            className="project-dashboard__menu"
            role="menu"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              type="button"
              className="project-dashboard__menu-item"
              role="menuitem"
              onClick={() => {
                onMenuToggle(project.id);
                onRemoveProject(project);
              }}
            >
              Remove from Graf-Id
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

export function ProjectDashboard({
  projects,
  selectedId,
  onSelect,
  onAddProject,
  onRemoveProject,
  onReorder,
}: ProjectDashboardProps) {
  const [activeCategory, setActiveCategory] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [openMenuId, setOpenMenuId] = useState<number | null>(null);
  const [draggingId, setDraggingId] = useState<number | null>(null);
  const [reorderBusy, setReorderBusy] = useState(false);

  useEffect(() => {
    if (openMenuId !== null && !projects.some((p) => p.id === openMenuId)) {
      setOpenMenuId(null);
    }
  }, [projects, openMenuId]);

  const grouped = useMemo(() => groupProjectsByCategory(projects), [projects]);

  const visibleProjects = useMemo(() => {
    let list =
      activeCategory === "all"
        ? projects
        : (grouped.get(activeCategory) ?? []);
    if (statusFilter !== "all") {
      list = list.filter((p) => (p.status ?? "active") === statusFilter);
    }
    const q = searchQuery.trim().toLowerCase();
    if (q) {
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          p.path.toLowerCase().includes(q) ||
          (p.category ?? "").toLowerCase().includes(q)
      );
    }
    return sortProjectsForSidebar(list);
  }, [activeCategory, grouped, projects, searchQuery, statusFilter]);

  const filtersActive =
    activeCategory !== "all" || statusFilter !== "all" || searchQuery.trim().length > 0;

  const handleDrop = async (event: DragEvent<HTMLDivElement>, targetProjectId: number) => {
    event.preventDefault();
    if (reorderBusy || draggingId == null || draggingId === targetProjectId) {
      setDraggingId(null);
      return;
    }
    const globalIds = initializeSidebarOrderIds(projects);
    const visibleIds = visibleProjects.map((item) => item.id);
    const targetIndex = visibleProjects.findIndex((item) => item.id === targetProjectId);
    if (targetIndex < 0) {
      setDraggingId(null);
      return;
    }
    const nextIds = filtersActive
      ? applyFilteredReorder(globalIds, visibleIds, draggingId, targetIndex)
      : applyReorder(globalIds, draggingId, targetIndex);
    setDraggingId(null);
    if (nextIds.join(",") === globalIds.join(",")) {
      return;
    }
    setReorderBusy(true);
    try {
      await onReorder(nextIds);
    } finally {
      setReorderBusy(false);
    }
  };

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const category of PROJECT_CATEGORIES) {
      counts.set(category, grouped.get(category)?.length ?? 0);
    }
    return counts;
  }, [grouped]);

  useEffect(() => {
    if (openMenuId === null) {
      return;
    }
    const closeMenu = () => setOpenMenuId(null);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeMenu();
      }
    };
    document.addEventListener("click", closeMenu);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("click", closeMenu);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openMenuId]);

  const handleMenuToggle = (projectId: number) => {
    setOpenMenuId((current) => (current === projectId ? null : projectId));
  };

  if (projects.length === 0) {
    return null;
  }

  return (
    <div className="sidebar__projects" aria-label="Project picker">
      <div className="sidebar__projects-head">
        <h2>Projects</h2>
        <button
          type="button"
          className="sidebar__add-project"
          onClick={onAddProject}
          {...grafiHelpProps(GRAFI_HELP_TOPIC.ADD_PROJECT)}
        >
          Add project
        </button>
      </div>

      <div className="project-dashboard__filters sidebar__project-filters">
        <label className="project-dashboard__search" {...grafiHelpProps(GRAFI_HELP_TOPIC.PROJECT_SEARCH)}>
          Search
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Name or path"
          />
        </label>
        <label {...grafiHelpProps(GRAFI_HELP_TOPIC.PROJECT_FILTER)}>
          Status
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All statuses</option>
            {PROJECT_STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div
        className="project-dashboard__categories sidebar__project-categories"
        role="tablist"
        aria-label="Project categories"
      >
        <button
          type="button"
          role="tab"
          aria-selected={activeCategory === "all"}
          className={
            activeCategory === "all"
              ? "project-dashboard__category project-dashboard__category--active"
              : "project-dashboard__category"
          }
          onClick={() => setActiveCategory("all")}
        >
          All ({projects.length})
        </button>
        {PROJECT_CATEGORIES.map((category) => {
          const count = categoryCounts.get(category) ?? 0;
          if (count === 0 && activeCategory !== category) {
            return null;
          }
          return (
            <button
              key={category}
              type="button"
              role="tab"
              aria-selected={activeCategory === category}
              className={
                activeCategory === category
                  ? "project-dashboard__category project-dashboard__category--active"
                  : "project-dashboard__category"
              }
              onClick={() => setActiveCategory(category)}
            >
              {category} ({count})
            </button>
          );
        })}
      </div>

      <div
        className="project-dashboard__list-wrap sidebar__project-list-wrap"
        role="listbox"
        aria-label="Project list"
      >
        {visibleProjects.length === 0 ? (
          <p className="muted project-dashboard__empty-category sidebar__empty">
            No projects in {activeCategory === "all" ? "any category" : activeCategory}.
          </p>
        ) : (
          <div className="project-dashboard__list">
            {visibleProjects.map((project) => (
              <ProjectListItem
                key={project.id}
                project={project}
                isSelected={project.id === selectedId}
                menuOpen={openMenuId === project.id}
                onSelect={onSelect}
                onMenuToggle={handleMenuToggle}
                onRemoveProject={onRemoveProject}
                draggable={!reorderBusy}
                onDragStart={setDraggingId}
                onDragOver={(event) => {
                  event.preventDefault();
                  event.dataTransfer.dropEffect = "move";
                }}
                onDrop={handleDrop}
                onDragEnd={() => setDraggingId(null)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
