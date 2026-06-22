export type JsonParseResult<T> =
  | { ok: true; value: T }
  | { ok: false; message: string };

const extractErrorPosition = (message: string): number | null => {
  const match = message.match(/position\s+(\d+)/i);
  if (!match) {
    return null;
  }

  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
};

const getLineColumnFromOffset = (source: string, offset: number): { line: number; column: number } => {
  let line = 1;
  let column = 1;

  for (let index = 0; index < source.length && index < offset; index += 1) {
    if (source[index] === "\n") {
      line += 1;
      column = 1;
      continue;
    }
    column += 1;
  }

  return { line, column };
};

export const parseJsonObjectWithLocation = <T>(
  source: string,
  isObject: (value: unknown) => value is T,
  fieldName = "JSON",
): JsonParseResult<T> => {
  try {
    const parsed = JSON.parse(source) as unknown;
    if (!isObject(parsed)) {
      return {
        ok: false,
        message: `${fieldName} must be a JSON object`,
      };
    }

    return {
      ok: true,
      value: parsed,
    };
  } catch (error) {
    const rawMessage = error instanceof Error ? error.message : "Invalid JSON";
    const position = extractErrorPosition(rawMessage);
    if (position === null) {
      return {
        ok: false,
        message: `Invalid JSON. ${rawMessage}`,
      };
    }

    const { line, column } = getLineColumnFromOffset(source, position);
    return {
      ok: false,
      message: `Invalid JSON at line ${line}, column ${column}. ${rawMessage}`,
    };
  }
};
