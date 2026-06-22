import type {
  ERRubricCheck,
  ERRubricJson,
  ERSubmissionCheck,
  ERSubmissionCheckStatus,
  ERSubmissionStructuredOutput,
} from "@/types/er-diagram.types";

export type RubricDisplayStatus = ERSubmissionCheckStatus | "not_evaluated";

export type RubricSummaryCount = {
  status: RubricDisplayStatus;
  label: string;
  color: string;
  count: number;
};

export type RubricDisplayItem = {
  id: string;
  dimension: string;
  dimensionLabel: string;
  requirementText: string;
  feedbackText: string;
  requirementLevelLabel: string;
  pointsLabel: string;
  status: RubricDisplayStatus;
};

export type RubricDisplayGroup = {
  key: string;
  label: string;
  items: RubricDisplayItem[];
};

const STATUS_META: Record<RubricDisplayStatus, { label: string; color: string }> = {
  pass: { label: "Passed", color: "green" },
  fail: { label: "Failed", color: "red" },
  partial: { label: "Partial", color: "yellow" },
  not_applicable: { label: "Not applicable", color: "gray" },
  not_evaluated: { label: "Not evaluated", color: "gray" },
};

const DIMENSION_LABELS: Record<string, string> = {
  entities: "Entities",
  attributes: "Attributes",
  relationships: "Relationships",
  cardinality: "Cardinality",
  keys_constraints: "Keys & Constraints",
  equivalences: "Equivalences",
};

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const formatTitleCase = (value: string): string =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1).toLowerCase())
    .join(" ");

const formatPoints = (value: unknown): string => {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "Points unavailable";
  }
  const normalized = Number.isInteger(value) ? value.toString() : value.toFixed(1).replace(/\.0$/, "");
  return `${normalized} pts`;
};

const formatRequirementLevel = (value: unknown): string => {
  if (typeof value !== "string" || !value.trim()) {
    return "Optional";
  }
  const normalized = value.trim().toLowerCase();
  if (normalized === "should") {
    return "Optional";
  }
  return formatTitleCase(normalized);
};

const formatDimension = (value: unknown): string => {
  if (typeof value !== "string" || !value.trim()) {
    return "Other";
  }
  const normalized = value.trim().toLowerCase();
  return DIMENSION_LABELS[normalized] || formatTitleCase(normalized);
};

const getFeedbackText = (matchedCheck: ERSubmissionCheck | undefined): string =>
  matchedCheck?.brief_reason?.trim() || "Not evaluated yet.";

const getRequirementText = (rubricCheck: ERRubricCheck): string => {
  const raw = rubricCheck.pass_criteria;
  if (typeof raw === "string" && raw.trim()) {
    return raw.trim();
  }
  return "No rubric description was provided for this item.";
};

const isRubricCheck = (value: unknown): value is ERRubricCheck => {
  if (!isObject(value)) return false;
  return typeof value.id === "string" && value.id.trim().length > 0
    && typeof value.dimension === "string" && value.dimension.trim().length > 0;
};

export const isStructuredRubricJson = (value: unknown): value is ERRubricJson =>
  isObject(value) && Array.isArray(value.checks) && value.checks.some(isRubricCheck);

export const getRubricStatusMeta = (status: RubricDisplayStatus): { label: string; color: string } =>
  STATUS_META[status];

export const buildRubricDisplayGroups = (
  rubricJson: ERRubricJson | null | undefined,
  structuredOutput: ERSubmissionStructuredOutput | null | undefined,
): RubricDisplayGroup[] | null => {
  if (!isStructuredRubricJson(rubricJson)) {
    return null;
  }

  const rubricChecks = (rubricJson.checks || []).filter(isRubricCheck);
  if (rubricChecks.length === 0) {
    return null;
  }

  const matchedChecksById = new Map<string, ERSubmissionCheck>();
  for (const check of structuredOutput?.checks || []) {
    if (!matchedChecksById.has(check.id)) {
      matchedChecksById.set(check.id, check);
    }
  }

  const groups = new Map<string, RubricDisplayGroup>();
  for (const rubricCheck of rubricChecks) {
    const key = rubricCheck.dimension.trim().toLowerCase();
    const matchedCheck = matchedChecksById.get(rubricCheck.id);
    const status: RubricDisplayStatus = matchedCheck?.status || "not_evaluated";
    const groupLabel = formatDimension(rubricCheck.dimension);
    const item: RubricDisplayItem = {
      id: rubricCheck.id,
      dimension: key,
      dimensionLabel: groupLabel,
      requirementText: getRequirementText(rubricCheck),
      feedbackText: getFeedbackText(matchedCheck),
      requirementLevelLabel: formatRequirementLevel(rubricCheck.requirement_level),
      pointsLabel: formatPoints(rubricCheck.points),
      status,
    };

    const existingGroup = groups.get(key);
    if (existingGroup) {
      existingGroup.items.push(item);
      continue;
    }

    groups.set(key, {
      key,
      label: groupLabel,
      items: [item],
    });
  }

  return Array.from(groups.values());
};

export const summarizeRubricStatuses = (groups: RubricDisplayGroup[]): RubricSummaryCount[] => {
  const counts: Record<RubricDisplayStatus, number> = {
    pass: 0,
    fail: 0,
    partial: 0,
    not_applicable: 0,
    not_evaluated: 0,
  };

  for (const group of groups) {
    for (const item of group.items) {
      counts[item.status] += 1;
    }
  }

  return (Object.keys(STATUS_META) as RubricDisplayStatus[]).map((status) => ({
    status,
    label: STATUS_META[status].label,
    color: STATUS_META[status].color,
    count: counts[status],
  }));
};

export const formatScoreValue = (value: number | string | undefined | null): string => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Number.isInteger(value) ? value.toString() : value.toFixed(1).replace(/\.0$/, "");
  }
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }
  return "0";
};
