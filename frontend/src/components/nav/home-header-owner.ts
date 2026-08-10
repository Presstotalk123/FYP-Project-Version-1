/**
 * Which component renders the header on `/`.
 *
 * Two components can put a header on the home route: the marketing one inside
 * the page, and the global HeaderNav. They must never both render, and must
 * never both stand down, so the decision lives here and both read it rather
 * than each carrying its own copy of the condition.
 *
 * - "loading"   — auth is still resolving. The page shows the bar with only the
 *                 wordmark, so nothing wrong is displayed and the height is
 *                 already reserved.
 * - "marketing" — a visitor. The page shows the pitch header.
 * - "app"       — a known user. The page stands down and HeaderNav renders the
 *                 same header it renders everywhere else.
 */
export type HomeHeaderOwner = "loading" | "marketing" | "app";

export function homeHeaderOwner(
  loading: boolean,
  isAuthenticated: boolean,
): HomeHeaderOwner {
  if (loading) return "loading";
  return isAuthenticated ? "app" : "marketing";
}
