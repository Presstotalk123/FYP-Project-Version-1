import api from "./api.service";

/**
 * The current user's own UI preferences — small key/value flags the app should
 * remember across devices, such as a guide's "don't remind me again". Backed by
 * GET/PUT /users/me/preferences (backend: services/user_preferences.py, which
 * also owns the closed list of allowed keys).
 *
 * Paths live here rather than in config/api.config.ts only because nothing else
 * calls them yet; move them there if a second caller appears.
 */
const MY_PREFERENCES = "/users/me/preferences";

export type UserPreferences = Record<string, string>;

export const userPreferencesService = {
  /** Every preference this user has set. Missing keys mean "unset". */
  async getMine(): Promise<UserPreferences> {
    const res = await api.get<UserPreferences>(MY_PREFERENCES);
    return res.data;
  },

  async setMine(key: string, value: string): Promise<void> {
    await api.put(`${MY_PREFERENCES}/${encodeURIComponent(key)}`, { value });
  },
};
