import type { RubricJsonObject, RubricJsonValue } from "@/types/er-diagram.types";

const isObject = (value: RubricJsonValue | undefined): value is RubricJsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const asText = (value: RubricJsonValue | undefined): string | null =>
  typeof value === "string" && value.trim() ? value.trim() : null;

const asStringArray = (value: RubricJsonValue | undefined): string[] =>
  Array.isArray(value)
    ? value
        .map((item) => (typeof item === "string" && item.trim() ? item.trim() : null))
        .filter((item): item is string => Boolean(item))
    : [];

const addSection = (lines: string[], title: string, body: string[]): void => {
  if (body.length === 0) return;
  if (lines.length > 0) {
    lines.push("");
  }
  lines.push(`${title}:`);
  lines.push(...body);
};

const formatJsonFallback = (label: string, value: RubricJsonValue | undefined): string[] => {
  if (typeof value === "undefined") return [];
  const serialized = JSON.stringify(value, null, 2);
  if (!serialized) return [];
  return [`${label}:`, "```json", serialized, "```"];
};

const formatCardinalitySummary = (value: RubricJsonValue | undefined): string[] => {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item, index) => {
    if (!isObject(item)) {
      return [`- Cardinality ${index + 1}: ${JSON.stringify(item)}`];
    }

    const relationship = asText(item.relationship) || `Cardinality ${index + 1}`;
    const endpoints = Array.isArray(item.endpoints)
      ? item.endpoints
          .map((endpoint) => {
            if (!isObject(endpoint)) return null;
            const entity = asText(endpoint.entity) || "Unknown entity";
            const cardinality = asText(endpoint.cardinality) || asText(endpoint.expected_cardinality) || "?";
            const participation = asText(endpoint.participation) || asText(endpoint.expected_participation);
            return participation ? `${entity} ${cardinality} (${participation})` : `${entity} ${cardinality}`;
          })
          .filter((endpoint): endpoint is string => Boolean(endpoint))
      : [];
    const attributes = asStringArray(item.relationship_attributes);
    const notes = asText(item.notes);

    const parts = [
      endpoints.length > 0 ? endpoints.join("; ") : null,
      attributes.length > 0 ? `attributes: ${attributes.join(", ")}` : null,
      notes,
    ].filter((part): part is string => Boolean(part));

    return [`- ${relationship}: ${parts.join(". ")}`];
  });
};

const formatKeysConstraintSummary = (value: RubricJsonValue | undefined): string[] => {
  if (!Array.isArray(value)) return [];

  return value.flatMap((item, index) => {
    if (!isObject(item)) {
      return [`- Key constraint ${index + 1}: ${JSON.stringify(item)}`];
    }

    const entity = asText(item.entity) || `Entity ${index + 1}`;
    const primaryKey = asStringArray(item.primary_key);
    const constraints = asStringArray(item.other_constraints);
    const parts = [
      primaryKey.length > 0 ? `PK: ${primaryKey.join(", ")}` : "PK: none specified",
      constraints.length > 0 ? constraints.join("; ") : null,
    ].filter((part): part is string => Boolean(part));

    return [`- ${entity}: ${parts.join(". ")}`];
  });
};

const formatChecksSummary = (value: RubricJsonValue | undefined): string[] => {
  if (!Array.isArray(value)) return [];

  const grouped = new Map<string, string[]>();
  for (const item of value) {
    if (!isObject(item)) continue;
    const level = asText(item.requirement_level) || "other";
    const id = asText(item.id) || "?";
    const points = typeof item.points === "number" ? item.points : null;
    const criteria = asText(item.pass_criteria) || asText(item.label) || asText(item.notes) || "No criteria provided.";
    const prefix = points !== null ? `- ${id} (${points})` : `- ${id}`;
    const bucket = grouped.get(level) || [];
    bucket.push(`${prefix}: ${criteria}`);
    grouped.set(level, bucket);
  }

  const orderedLevels = ["must", "should", "optional", "not_applicable"];
  const remainingLevels = [...grouped.keys()].filter((level) => !orderedLevels.includes(level)).sort();
  const allLevels = [...orderedLevels.filter((level) => grouped.has(level)), ...remainingLevels];

  return allLevels.flatMap((level) => {
    const items = grouped.get(level) || [];
    const heading = `${level.charAt(0).toUpperCase() + level.slice(1)}-level checks`;
    return ["", `${heading}:`, ...items];
  }).filter((line, index, lines) => !(line === "" && (index === 0 || lines[index - 1] === "")));
};

export const buildRubricMarkdownFromJson = (rubricJson: RubricJsonObject): string => {
  if (Object.keys(rubricJson).length === 0) {
    return "";
  }

  const lines: string[] = [];

  const meta = isObject(rubricJson.meta) ? rubricJson.meta : undefined;
  const notation = meta ? asText(meta.notation_target) : null;
  const title = notation ? `Grading rubric (${notation} notation)` : "Grading rubric";
  lines.push(title);

  const gradingGoal = meta ? asText(meta.grading_goal) : null;
  if (gradingGoal) {
    lines.push("");
    lines.push(gradingGoal);
  }

  const metaLines = [
    meta ? asText(meta.version_hint) : null,
    meta ? asText(meta.assumptions) : null,
  ]
    .filter((item): item is string => Boolean(item))
    .map((item, index) => (index === 0 && meta && asText(meta.version_hint) ? `- Version: ${item}` : `- ${item}`));
  addSection(lines, "Meta", metaLines);

  const policy = isObject(rubricJson.policy) ? rubricJson.policy : undefined;
  if (policy) {
    const policyLines = Object.entries(policy)
      .map(([key, value]) => {
        const text = asText(value);
        return text ? `- ${key.replace(/_/g, " ")}: ${text}` : null;
      })
      .filter((line): line is string => Boolean(line));
    addSection(lines, "Policy", policyLines);
  }

  const canonicalTargets = isObject(rubricJson.canonical_targets) ? rubricJson.canonical_targets : undefined;
  if (canonicalTargets) {
    const entityLines = asStringArray(canonicalTargets.entities).map((item) => `- ${item}`);
    addSection(lines, "Entities", entityLines);

    const relationshipLines = asStringArray(canonicalTargets.relationships).map((item) => `- ${item}`);
    addSection(lines, "Relationships", relationshipLines);

    addSection(lines, "Cardinalities", formatCardinalitySummary(canonicalTargets.cardinalities));
    addSection(lines, "Keys & Constraints", formatKeysConstraintSummary(canonicalTargets.keys_constraints));
  }

  addSection(lines, "Checks", formatChecksSummary(rubricJson.checks));

  const unknownTopLevelKeys = Object.keys(rubricJson).filter(
    (key) => !["meta", "policy", "canonical_targets", "checks"].includes(key),
  );
  for (const key of unknownTopLevelKeys) {
    const fallback = formatJsonFallback(`Additional section: ${key}`, rubricJson[key]);
    if (fallback.length > 0) {
      if (lines.length > 0) {
        lines.push("");
      }
      lines.push(...fallback);
    }
  }

  return lines.join("\n").trim();
};
