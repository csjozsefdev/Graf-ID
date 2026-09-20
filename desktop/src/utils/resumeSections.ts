import type { MvpSection } from "../ipc/types";

/** Primary continuity sections — shown first without scrolling. */
const PRIMARY_TITLES = new Set([
  "where you left off",
  "suggested next step",
  "blocker",
  "notes on file",
  "recent file changes",
  "context",
  "project",
]);

const PRIMARY_ORDER = [
  "where you left off",
  "suggested next step",
  "blocker",
  "notes on file",
  "recent file changes",
  "context",
  "project",
];

function normalizeTitle(title: string): string {
  return title.trim().toLowerCase();
}

function primaryRank(title: string): number {
  const key = normalizeTitle(title);
  const index = PRIMARY_ORDER.indexOf(key);
  return index === -1 ? PRIMARY_ORDER.length : index;
}

export function partitionMvpSections(sections: MvpSection[]): {
  primary: MvpSection[];
  secondary: MvpSection[];
} {
  const primary: MvpSection[] = [];
  const secondary: MvpSection[] = [];

  for (const section of sections) {
    if (PRIMARY_TITLES.has(normalizeTitle(section.title))) {
      primary.push(section);
    } else {
      secondary.push(section);
    }
  }

  primary.sort((a, b) => primaryRank(a.title) - primaryRank(b.title));
  return { primary, secondary };
}

/** True when blocker/next/exit grid duplicates an MVP section body. */
export function sessionFieldsDuplicatedInSections(
  sections: MvpSection[],
  fields: { blocker: string | null; nextStep: string | null; exitNote: string | null }
): { showBlocker: boolean; showNextStep: boolean; showExitNote: boolean } {
  const bodies = new Set(
    sections.map((section) => section.body.trim().toLowerCase()).filter(Boolean)
  );
  const titles = new Set(sections.map((section) => normalizeTitle(section.title)));

  const includes = (value: string | null, titleKeys: string[]) => {
    if (!value) return false;
    const normalized = value.trim().toLowerCase();
    if (bodies.has(normalized)) return true;
    return titleKeys.some((key) => titles.has(key));
  };

  return {
    showBlocker: !includes(fields.blocker, ["blocker"]),
    showNextStep: !includes(fields.nextStep, ["suggested next step"]),
    showExitNote: !includes(fields.exitNote, ["where you left off", "session"]),
  };
}

const LEAD_TITLES = new Set(["suggested next step", "blocker"]);

/**
 * Panel layout: "Where you left off", then the sections the Project Snapshot does
 * not already show (next step / blocker fallbacks), then everything technical as
 * collapsible evidence (file changes, notes on file, code markers, session, context).
 */
export function layoutResumeSections(
  sections: MvpSection[],
  covered: MvpSection[] = []
): { whereLeftOff: MvpSection | null; lead: MvpSection[]; evidence: MvpSection[] } {
  const coveredTitles = new Set(covered.map((section) => normalizeTitle(section.title)));
  const coveredBodies = covered.map((section) => section.body.trim().toLowerCase());

  let whereLeftOff: MvpSection | null = null;
  const lead: MvpSection[] = [];
  const evidence: MvpSection[] = [];

  for (const section of sections) {
    const title = normalizeTitle(section.title);
    if (title === "where you left off" && whereLeftOff === null) {
      whereLeftOff = section;
    } else if (LEAD_TITLES.has(title)) {
      const body = section.body.trim().toLowerCase();
      const alreadyShown =
        coveredTitles.has(title) && coveredBodies.some((c) => c.includes(body) || body.includes(c));
      if (!alreadyShown) lead.push(section);
    } else {
      evidence.push(section);
    }
  }
  lead.sort((a, b) => primaryRank(a.title) - primaryRank(b.title));
  return { whereLeftOff, lead, evidence };
}
