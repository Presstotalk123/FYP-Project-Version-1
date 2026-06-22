import type {
  RubricFormSectionKey,
  RubricJsonArray,
  RubricJsonObject,
  RubricJsonPrimitive,
  RubricJsonValue,
} from "@/types/er-diagram.types";

export type RubricPathSegment = string | number;
export type RubricPath = RubricPathSegment[];
export type RubricScalarControl = "text" | "textarea" | "number" | "switch" | "select";

export type RubricFieldConfig = {
  control: RubricScalarControl;
  options?: string[];
  clearable?: boolean;
  rows?: number;
};

export const RUBRIC_TOP_LEVEL_SECTION_ORDER: RubricFormSectionKey[] = [
  "meta",
  "policy",
  "canonical_targets",
  "checks",
];

const FIELD_LABELS: Record<string, string> = {
  id: "ID",
  meta: "Meta",
  policy: "Policy",
  canonical_targets: "Canonical Targets",
  keys_constraints: "Keys & Constraints",
  primary_key: "Primary Key",
  requirement_level: "Requirement Level",
  pass_criteria: "Pass Criteria",
  fail_reason_template: "Fail Reason Template",
  instruction_history: "Instruction History",
  show_rubric_on_attempt: "Show Rubric On Attempt",
};

const LONG_TEXT_KEYS = new Set([
  "grading_goal",
  "assumptions",
  "naming_tolerance",
  "allow_equivalences",
  "cardinality_strictness",
  "ambiguity_handling",
  "pass_criteria",
  "fail_reason_template",
  "notes",
  "description",
  "rule",
]);

const SELECT_OPTIONS: Record<string, string[]> = {
  dimension: ["entities", "attributes", "relationships", "cardinality", "keys_constraints", "equivalences", "global"],
  requirement_level: ["must", "should", "optional", "not_applicable"],
  evidence: ["either", "diagram_llm_extraction", "explicit_diagram_evidence", "model_answer"],
  participation: ["total", "partial"],
  ambiguous_label_policy: ["fail", "partial", "accept"],
  missing_policy: ["fail", "partial", "ignore"],
  unclear_evidence_policy: ["fail", "partial", "accept"],
};

const PREFERRED_KEY_ORDER: Record<string, string[]> = {
  root: ["meta", "policy", "canonical_targets", "checks"],
  meta: ["notation_target", "grading_goal", "version_hint", "assumptions"],
  policy: ["naming_tolerance", "allow_equivalences", "cardinality_strictness", "ambiguity_handling"],
  canonical_targets: ["entities", "relationships", "cardinalities", "keys_constraints"],
  "canonical_targets.cardinalities.*": ["relationship", "endpoints", "relationship_attributes", "notes"],
  "canonical_targets.cardinalities.*.endpoints.*": ["entity", "cardinality", "participation", "expected_cardinality", "expected_participation"],
  "canonical_targets.keys_constraints.*": ["entity", "primary_key", "other_constraints"],
  "checks.*": [
    "id",
    "dimension",
    "type",
    "target",
    "requirement_level",
    "points",
    "pass_criteria",
    "fail_reason_template",
    "evidence",
    "equivalence_options",
    "notes",
    "decision_policy",
  ],
  "checks.*.target": [
    "entity",
    "entities",
    "attribute",
    "attributes_required",
    "relationship",
    "relationships_required",
    "participant",
    "participants",
    "cardinality",
    "endpoints",
    "relationship_attributes_required",
    "keys_required",
    "rule",
    "description",
    "label",
    "note",
  ],
  "checks.*.target.endpoints.*": ["entity", "cardinality", "participation", "expected_cardinality", "expected_participation"],
  "checks.*.target.keys_required.*": ["entity", "primary_key", "rule", "description", "label", "note"],
  "checks.*.equivalence_options.*": ["type", "description", "notes"],
  "checks.*.decision_policy": [
    "exact_name_required",
    "semantic_alias_allowed",
    "abbreviation_allowed",
    "owner_must_match",
    "ambiguous_label_policy",
    "missing_policy",
    "explicit_diagram_evidence_required",
    "unclear_evidence_policy",
    "partial_allowed",
  ],
};

const pathToPattern = (path: RubricPath): string =>
  path
    .map((segment) => (typeof segment === "number" ? "*" : segment))
    .join(".");

const formatTitleCase = (value: string): string =>
  value
    .trim()
    .replace(/[_-]+/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");

const createEmptyCanonicalEndpoint = (): RubricJsonObject => ({
  entity: "",
  cardinality: "",
  participation: "partial",
});

const createEmptyTargetEndpoint = (): RubricJsonObject => ({
  entity: null,
  cardinality: null,
  participation: null,
  expected_cardinality: null,
  expected_participation: null,
});

const createEmptyKeysConstraint = (): RubricJsonObject => ({
  entity: "",
  primary_key: [],
  other_constraints: [],
});

const createEmptyKeyRequirement = (): RubricJsonObject => ({
  entity: "",
  primary_key: null,
  rule: null,
  description: null,
  label: null,
  note: null,
});

const createEmptyEquivalenceOption = (): RubricJsonObject => ({
  type: "",
  description: "",
  notes: null,
});

const createEmptyCardinality = (): RubricJsonObject => ({
  relationship: "",
  endpoints: [createEmptyCanonicalEndpoint()],
  relationship_attributes: [],
  notes: "",
});

const createEmptyCheck = (): RubricJsonObject => ({
  id: "",
  dimension: "entities",
  type: "",
  target: {
    entity: null,
    entities: [],
    attribute: null,
    attributes_required: [],
    relationship: null,
    relationships_required: [],
    participant: null,
    participants: [],
    cardinality: null,
    endpoints: [],
    relationship_attributes_required: [],
    keys_required: [],
    rule: "",
    description: "",
    label: "",
    note: null,
  },
  requirement_level: "must",
  points: 0,
  pass_criteria: "",
  fail_reason_template: "",
  evidence: "either",
  equivalence_options: [],
  notes: "",
  decision_policy: {
    exact_name_required: false,
    semantic_alias_allowed: true,
    abbreviation_allowed: true,
    owner_must_match: false,
    ambiguous_label_policy: "partial",
    missing_policy: "fail",
    explicit_diagram_evidence_required: false,
    unclear_evidence_policy: "fail",
    partial_allowed: true,
  },
});

const cloneEmptyLike = (value: RubricJsonValue | undefined): RubricJsonValue => {
  if (typeof value === "string") return "";
  if (typeof value === "number") return 0;
  if (typeof value === "boolean") return false;
  if (value === null || typeof value === "undefined") return "";
  if (Array.isArray(value)) return [];

  const next: RubricJsonObject = {};
  for (const [key, nestedValue] of Object.entries(value)) {
    next[key] = cloneEmptyLike(nestedValue);
  }
  return next;
};

const getDefaultArrayItem = (path: RubricPath, currentArray: RubricJsonArray): RubricJsonValue => {
  const pattern = pathToPattern(path);

  if (pattern === "checks") return createEmptyCheck();
  if (pattern === "canonical_targets.cardinalities") return createEmptyCardinality();
  if (pattern === "canonical_targets.keys_constraints") return createEmptyKeysConstraint();
  if (pattern.endsWith(".target.keys_required")) return createEmptyKeyRequirement();
  if (pattern.endsWith(".equivalence_options")) return createEmptyEquivalenceOption();
  if (pattern === "canonical_targets.entities" || pattern === "canonical_targets.relationships") return "";
  if (pattern.endsWith(".attributes_required")) return "";
  if (pattern.endsWith(".relationships_required")) return "";
  if (pattern.endsWith(".relationship_attributes")) return "";
  if (pattern.endsWith(".relationship_attributes_required")) return "";
  if (pattern.endsWith(".participants")) return "";
  if (pattern.endsWith(".primary_key")) return "";
  if (pattern.endsWith(".other_constraints")) return "";
  if (pattern === "canonical_targets.cardinalities.*.endpoints") return createEmptyCanonicalEndpoint();
  if (pattern.endsWith(".endpoints")) return createEmptyTargetEndpoint();

  if (currentArray.length > 0) {
    return cloneEmptyLike(currentArray[0]);
  }

  return "";
};

const ensureSelectOptions = (options: string[], value: string | null): string[] => {
  if (!value || options.includes(value)) {
    return options;
  }
  return [...options, value];
};

const sortKeysWithPreference = (keys: string[], preferred: string[]): string[] => {
  const preferredIndex = new Map(preferred.map((key, index) => [key, index]));
  return [...keys].sort((left, right) => {
    const leftIndex = preferredIndex.get(left);
    const rightIndex = preferredIndex.get(right);
    if (typeof leftIndex === "number" && typeof rightIndex === "number") {
      return leftIndex - rightIndex;
    }
    if (typeof leftIndex === "number") return -1;
    if (typeof rightIndex === "number") return 1;
    return left.localeCompare(right);
  });
};

const withUpdatedChild = (
  current: RubricJsonValue | undefined,
  segment: RubricPathSegment,
  updater: (child: RubricJsonValue | undefined) => RubricJsonValue,
): RubricJsonValue => {
  if (typeof segment === "number") {
    const source = Array.isArray(current) ? [...current] : [];
    source[segment] = updater(source[segment]);
    return source;
  }

  const source = isRubricJsonObject(current) ? { ...current } : {};
  source[segment] = updater(source[segment]);
  return source;
};

export const isRubricJsonObject = (value: unknown): value is RubricJsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const formatRubricJson = (value: RubricJsonObject): string => JSON.stringify(value, null, 2);

export const cloneRubricJsonValue = (value: RubricJsonValue): RubricJsonValue => {
  if (Array.isArray(value)) {
    return value.map((item) => cloneRubricJsonValue(item));
  }

  if (isRubricJsonObject(value)) {
    const next: RubricJsonObject = {};
    for (const [key, nestedValue] of Object.entries(value)) {
      if (typeof nestedValue !== "undefined") {
        next[key] = cloneRubricJsonValue(nestedValue);
      }
    }
    return next;
  }

  return value;
};

export const cloneRubricJsonObject = (value: RubricJsonObject): RubricJsonObject =>
  cloneRubricJsonValue(value) as RubricJsonObject;

export const getRubricSectionLabel = (key: string): string => FIELD_LABELS[key] || formatTitleCase(key);

export const getRubricFieldLabel = (key: string): string => FIELD_LABELS[key] || formatTitleCase(key);

export const getRubricFieldConfig = (
  path: RubricPath,
  key: string,
  value: RubricJsonPrimitive,
): RubricFieldConfig => {
  if (typeof value === "boolean") {
    return { control: "switch" };
  }
  if (typeof value === "number" || key === "points") {
    return { control: "number" };
  }

  const selectOptions = SELECT_OPTIONS[key];
  if (selectOptions) {
    const currentValue = typeof value === "string" && value.trim() ? value : null;
    return {
      control: "select",
      options: ensureSelectOptions(selectOptions, currentValue),
      clearable: value === null,
    };
  }

  const pathPattern = pathToPattern([...path, key]);
  if (LONG_TEXT_KEYS.has(key) || pathPattern.endsWith(".notes") || pathPattern.endsWith(".description")) {
    return { control: "textarea", rows: 4 };
  }

  return { control: "text" };
};

export const getRubricObjectKeys = (path: RubricPath, value: RubricJsonObject): string[] => {
  const keys = Object.keys(value);
  const preferred = PREFERRED_KEY_ORDER[pathToPattern(path)] || PREFERRED_KEY_ORDER.root;
  return sortKeysWithPreference(keys, preferred || []);
};

export const getRubricArrayItemLabel = (path: RubricPath, value: RubricJsonValue, index: number): string => {
  const pattern = pathToPattern(path);
  if (pattern === "checks" && isRubricJsonObject(value)) {
    const id = typeof value.id === "string" && value.id.trim() ? value.id.trim() : `#${index + 1}`;
    const label = typeof value.label === "string" && value.label.trim() ? value.label.trim() : null;
    return label ? `${id} - ${label}` : `Check ${id}`;
  }
  if (pattern === "canonical_targets.cardinalities" && isRubricJsonObject(value)) {
    const relationship = typeof value.relationship === "string" && value.relationship.trim()
      ? value.relationship.trim()
      : `Cardinality ${index + 1}`;
    return relationship;
  }
  if (pattern === "canonical_targets.keys_constraints" && isRubricJsonObject(value)) {
    const entity = typeof value.entity === "string" && value.entity.trim() ? value.entity.trim() : `Constraint ${index + 1}`;
    return entity;
  }
  if (pattern.endsWith(".endpoints") && isRubricJsonObject(value)) {
    const entity = typeof value.entity === "string" && value.entity.trim() ? value.entity.trim() : `Endpoint ${index + 1}`;
    return entity;
  }
  if (pattern.endsWith(".equivalence_options") && isRubricJsonObject(value)) {
    const type = typeof value.type === "string" && value.type.trim() ? value.type.trim() : `Option ${index + 1}`;
    return type;
  }
  if (pattern.endsWith(".keys_required") && isRubricJsonObject(value)) {
    const entity = typeof value.entity === "string" && value.entity.trim() ? value.entity.trim() : `Key ${index + 1}`;
    return entity;
  }

  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }

  return `Item ${index + 1}`;
};

export const updateRubricValueAtPath = (
  root: RubricJsonObject,
  path: RubricPath,
  nextValue: RubricJsonValue,
): RubricJsonObject => {
  const setValue = (current: RubricJsonValue | undefined, remainingPath: RubricPath): RubricJsonValue => {
    if (remainingPath.length === 0) {
      return nextValue;
    }

    const [head, ...rest] = remainingPath;
    return withUpdatedChild(current, head, (child) => setValue(child, rest));
  };

  const updated = setValue(root, path);
  return isRubricJsonObject(updated) ? updated : root;
};

export const removeRubricValueAtPath = (root: RubricJsonObject, path: RubricPath): RubricJsonObject => {
  if (path.length === 0) {
    return root;
  }

  const [head, ...rest] = path;

  if (typeof head === "number") {
    return root;
  }

  if (rest.length === 0) {
    const next = { ...root };
    delete next[head];
    return next;
  }

  const child = root[head];
  const next = { ...root };
  const nextSegment = rest[0];

  if (typeof nextSegment === "number") {
    if (!Array.isArray(child)) return root;
    const remainingPath = rest.slice(1);
    const nextIndex = nextSegment;
    const nextArray = [...child];

    if (remainingPath.length === 0) {
      nextArray.splice(nextIndex, 1);
    } else {
      const currentItem = nextArray[nextIndex];
      if (!isRubricJsonObject(currentItem)) return root;
      nextArray[nextIndex] = removeRubricValueAtPath(currentItem, remainingPath);
    }

    next[head] = nextArray;
    return next;
  }

  if (!isRubricJsonObject(child)) return root;
  next[head] = removeRubricValueAtPath(child, rest);
  return next;
};

export const addRubricObjectField = (
  root: RubricJsonObject,
  path: RubricPath,
  key: string,
): RubricJsonObject => {
  const trimmedKey = key.trim();
  if (!trimmedKey) return root;

  const addField = (current: RubricJsonValue | undefined, remainingPath: RubricPath): RubricJsonValue => {
    if (remainingPath.length === 0) {
      const source = isRubricJsonObject(current) ? { ...current } : {};
      if (Object.prototype.hasOwnProperty.call(source, trimmedKey)) {
        return source;
      }
      source[trimmedKey] = "";
      return source;
    }

    const [head, ...rest] = remainingPath;
    return withUpdatedChild(current, head, (child) => addField(child, rest));
  };

  const updated = addField(root, path);
  return isRubricJsonObject(updated) ? updated : root;
};

export const addRubricArrayItem = (root: RubricJsonObject, path: RubricPath): RubricJsonObject => {
  const addItem = (current: RubricJsonValue | undefined, remainingPath: RubricPath): RubricJsonValue => {
    if (remainingPath.length === 0) {
      const source = Array.isArray(current) ? [...current] : [];
      source.push(getDefaultArrayItem(path, source));
      return source;
    }

    const [head, ...rest] = remainingPath;
    return withUpdatedChild(current, head, (child) => addItem(child, rest));
  };

  const updated = addItem(root, path);
  return isRubricJsonObject(updated) ? updated : root;
};

const ensureDraftContainer = (
  parent: RubricJsonValue,
  segment: RubricPathSegment,
  nextSegment: RubricPathSegment | undefined,
): RubricJsonValue | undefined => {
  const emptyChild: RubricJsonValue = typeof nextSegment === "number" ? [] : {};

  if (typeof segment === "number") {
    if (!Array.isArray(parent)) {
      return undefined;
    }

    const existing = parent[segment];
    if (typeof existing === "undefined") {
      parent[segment] = emptyChild;
      return parent[segment];
    }

    if (typeof nextSegment === "number") {
      if (!Array.isArray(existing)) {
        parent[segment] = [];
      }
      return parent[segment];
    }

    if (!isRubricJsonObject(existing)) {
      parent[segment] = {};
    }
    return parent[segment];
  }

  if (!isRubricJsonObject(parent)) {
    return undefined;
  }

  const existing = parent[segment];
  if (typeof existing === "undefined") {
    parent[segment] = emptyChild;
    return parent[segment];
  }

  if (typeof nextSegment === "number") {
    if (!Array.isArray(existing)) {
      parent[segment] = [];
    }
    return parent[segment];
  }

  if (!isRubricJsonObject(existing)) {
    parent[segment] = {};
  }
  return parent[segment];
};

export const setRubricDraftValueAtPath = (
  root: RubricJsonObject,
  path: RubricPath,
  nextValue: RubricJsonValue,
): RubricJsonObject => {
  if (path.length === 0) {
    if (!isRubricJsonObject(nextValue)) {
      return root;
    }

    for (const key of Object.keys(root)) {
      delete root[key];
    }
    for (const [key, value] of Object.entries(nextValue)) {
      if (typeof value !== "undefined") {
        root[key] = cloneRubricJsonValue(value);
      }
    }
    return root;
  }

  let current: RubricJsonValue = root;
  for (let index = 0; index < path.length - 1; index += 1) {
    const segment = path[index];
    const nextSegment = path[index + 1];
    const ensured = ensureDraftContainer(current, segment, nextSegment);
    if (typeof ensured === "undefined") {
      return root;
    }
    current = ensured;
  }

  const tail = path[path.length - 1];
  const clonedValue = cloneRubricJsonValue(nextValue);

  if (typeof tail === "number") {
    if (!Array.isArray(current)) {
      return root;
    }
    current[tail] = clonedValue;
    return root;
  }

  if (!isRubricJsonObject(current)) {
    return root;
  }
  current[tail] = clonedValue;
  return root;
};

export const removeRubricDraftValueAtPath = (root: RubricJsonObject, path: RubricPath): RubricJsonObject => {
  if (path.length === 0) {
    return root;
  }

  if (path.length === 1) {
    const [head] = path;
    if (typeof head === "string") {
      delete root[head];
    }
    return root;
  }

  let current: RubricJsonValue = root;
  for (let index = 0; index < path.length - 1; index += 1) {
    const segment = path[index];

    if (typeof segment === "number") {
      if (!Array.isArray(current)) {
        return root;
      }
      const nextValue: RubricJsonValue | undefined = current[segment];
      if (typeof nextValue === "undefined") {
        return root;
      }
      current = nextValue;
      continue;
    }

    if (!isRubricJsonObject(current)) {
      return root;
    }
    const nextValue: RubricJsonValue | undefined = current[segment];
    if (typeof nextValue === "undefined") {
      return root;
    }
    current = nextValue;
  }

  const tail = path[path.length - 1];
  if (typeof tail === "number") {
    if (Array.isArray(current)) {
      current.splice(tail, 1);
    }
    return root;
  }

  if (isRubricJsonObject(current)) {
    delete current[tail];
  }
  return root;
};

export const addRubricDraftObjectField = (
  root: RubricJsonObject,
  path: RubricPath,
  key: string,
): RubricJsonObject => {
  const trimmedKey = key.trim();
  if (!trimmedKey) {
    return root;
  }

  let current: RubricJsonValue = root;
  for (let index = 0; index < path.length; index += 1) {
    const segment = path[index];
    const nextSegment = path[index + 1];
    const ensured = ensureDraftContainer(current, segment, nextSegment);
    if (typeof ensured === "undefined") {
      return root;
    }
    current = ensured;
  }

  if (!isRubricJsonObject(current) || Object.prototype.hasOwnProperty.call(current, trimmedKey)) {
    return root;
  }

  current[trimmedKey] = "";
  return root;
};

export const addRubricDraftArrayItem = (root: RubricJsonObject, path: RubricPath): RubricJsonObject => {
  let current: RubricJsonValue = root;
  for (let index = 0; index < path.length; index += 1) {
    const segment = path[index];
    const nextSegment = path[index + 1];
    const ensured = ensureDraftContainer(current, segment, nextSegment);
    if (typeof ensured === "undefined") {
      return root;
    }
    current = ensured;
  }

  if (!Array.isArray(current)) {
    return root;
  }

  current.push(getDefaultArrayItem(path, current));
  return root;
};
