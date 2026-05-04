/**
 * Activation API client.
 *
 * The Telegram bot at ./bot/ issues activation codes after a paid
 * subscription. The Lira app POSTs the user-entered code here and gets
 * back the canonical tariff + expiry, which it then writes into the
 * local subscription state.
 */
import Constants from 'expo-constants';

import { SubscriptionTier } from '../types';

export interface ActivateResponse {
  valid: boolean;
  tariff?: SubscriptionTier;
  expires?: string;
  redeemed_at?: string;
}

const fallbackBase = 'https://flowcare-api.example.com';

const baseUrl = (): string => {
  const fromExtra =
    (Constants?.expoConfig?.extra as Record<string, unknown> | undefined)?.[
      'activationApiUrl'
    ] ??
    (Constants?.manifest2?.extra as Record<string, unknown> | undefined)?.[
      'activationApiUrl'
    ];
  if (typeof fromExtra === 'string' && fromExtra.length > 0) return fromExtra;
  return fallbackBase;
};

export const activateCode = async (
  code: string,
  deviceId?: string,
): Promise<ActivateResponse> => {
  const url = `${baseUrl().replace(/\/$/, '')}/v1/activate`;
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code.trim().toUpperCase(), device_id: deviceId ?? null }),
    });
    if (!res.ok) {
      return { valid: false };
    }
    const json = (await res.json()) as ActivateResponse;
    return json;
  } catch {
    return { valid: false };
  }
};

export interface SubscriptionByDeviceResponse {
  tier: SubscriptionTier;
  expires: string;
  started_at: string;
  activation_code: string | null;
  redeemed_at: string | null;
}

export type FetchSubscriptionByDeviceResult =
  | { ok: true; data: SubscriptionByDeviceResponse }
  | { ok: false; reason: 'not_bound' | 'no_subscription' | 'invalid_device' | 'network' };

/** Look up the subscription that the bot has bound to this device.
 *
 * The bot stamps `users.device_id` when the user completes the
 * `/start link_<id>` (or `/start premium_<id>`) deep link, so this
 * endpoint becomes the auto-sync replacement for the manual 8-char
 * activation code paste. Cleanly distinguishes 404 / 400 / network
 * errors so the UI can decide whether to keep polling or surface the
 * "no link yet" hint.
 */
export const fetchSubscriptionByDevice = async (
  deviceId: string,
): Promise<FetchSubscriptionByDeviceResult> => {
  const trimmed = deviceId.trim();
  if (!trimmed) return { ok: false, reason: 'invalid_device' };
  const url = `${baseUrl().replace(/\/$/, '')}/v1/subscription/by-device/${encodeURIComponent(trimmed)}`;
  try {
    const res = await fetch(url, { method: 'GET' });
    if (res.status === 404) {
      // Backend returns the same status for "device never bound" and
      // "no active subscription" — peek at the JSON body to distinguish.
      let detail: string | undefined;
      try {
        const body = (await res.json()) as { detail?: string };
        detail = body.detail;
      } catch {
        // ignore — fall through with `not_bound` as a safe default
      }
      if (detail === 'no_active_subscription') {
        return { ok: false, reason: 'no_subscription' };
      }
      return { ok: false, reason: 'not_bound' };
    }
    if (res.status === 400) return { ok: false, reason: 'invalid_device' };
    if (!res.ok) return { ok: false, reason: 'network' };
    const json = (await res.json()) as SubscriptionByDeviceResponse;
    return { ok: true, data: json };
  } catch {
    return { ok: false, reason: 'network' };
  }
};

export const isLikelyCode = (input: string): boolean => /^[A-Z0-9]{6,12}$/i.test(input.trim());
