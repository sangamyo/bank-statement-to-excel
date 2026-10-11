/**
 * Per-browser preferences and identity, persisted in localStorage.
 * Every access is wrapped in try/catch so the app still works when storage
 * is unavailable (private mode, blocked site data, ...).
 */

const CLIENT_ID_KEY = 'bse.clientId';
const PREFS_KEY = 'bse.preferences';

export interface Preferences {
  /** Download the Excel file automatically when a conversion succeeds. */
  autoDownload: boolean;
  /** Ask for confirmation before deleting a conversion. */
  confirmDelete: boolean;
}

export const DEFAULT_PREFERENCES: Preferences = {
  autoDownload: false,
  confirmDelete: true,
};

let memoryClientId: string | null = null;

function randomId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

/** Random, anonymous id that scopes this browser's history on the server. */
export function getClientId(): string {
  try {
    const existing = localStorage.getItem(CLIENT_ID_KEY);
    if (existing) return existing;
    const id = randomId();
    localStorage.setItem(CLIENT_ID_KEY, id);
    return id;
  } catch {
    if (!memoryClientId) memoryClientId = randomId();
    return memoryClientId;
  }
}

/** Forget the current id; this browser starts with an empty history. */
export function resetClientId(): string {
  const id = randomId();
  memoryClientId = id;
  try {
    localStorage.setItem(CLIENT_ID_KEY, id);
  } catch {
    /* ignore */
  }
  return id;
}

export function getPreferences(): Preferences {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return { ...DEFAULT_PREFERENCES };
    return { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

export function savePreferences(prefs: Preferences): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}
