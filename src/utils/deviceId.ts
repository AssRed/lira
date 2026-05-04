import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * Stable per-install identifier. Generated on first read, persisted to
 * AsyncStorage, and reused forever after. The bot binds it to a Telegram
 * user via the `/start link_<id>` deep link so that the FlowCare API can
 * push subscription state back to this app without the user pasting the
 * 8-char activation code.
 */

const STORAGE_KEY = '@cycle-tracker/device-id/v1';

const HEX_ALPHABET = '0123456789abcdef';

/** Generate a 32-char lowercase hex token. We keep this dependency-free
 * so it works under tsx/node tests too — no Expo / RN crypto modules. */
const randomHex = (length = 32): string => {
  let out = '';
  for (let i = 0; i < length; i += 1) {
    out += HEX_ALPHABET[Math.floor(Math.random() * HEX_ALPHABET.length)];
  }
  return out;
};

const isWellFormed = (raw: unknown): raw is string =>
  typeof raw === 'string' && /^[a-z0-9]{16,64}$/.test(raw);

let cached: string | null = null;
let pending: Promise<string> | null = null;

/** Returns a cached device id, generating + persisting one on the first call. */
export const getOrCreateDeviceId = async (): Promise<string> => {
  if (cached) return cached;
  if (pending) return pending;
  pending = (async () => {
    try {
      const stored = await AsyncStorage.getItem(STORAGE_KEY);
      if (isWellFormed(stored)) {
        cached = stored;
        return stored;
      }
    } catch {
      // fall through and regenerate
    }
    const fresh = randomHex(32);
    try {
      await AsyncStorage.setItem(STORAGE_KEY, fresh);
    } catch {
      // best effort — even if storage fails we still want a usable id this
      // session so the app can talk to the API.
    }
    cached = fresh;
    return fresh;
  })();
  try {
    return await pending;
  } finally {
    pending = null;
  }
};

/** Test-only hook for resetting the in-memory cache between cases. */
export const __resetDeviceIdCacheForTests = (): void => {
  cached = null;
  pending = null;
};

/** Read-only snapshot of the cached id without triggering generation. */
export const peekCachedDeviceId = (): string | null => cached;
