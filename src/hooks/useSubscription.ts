import { differenceInCalendarDays, isBefore, parseISO } from 'date-fns';
import { useCallback, useEffect, useRef } from 'react';
import { AppState, AppStateStatus } from 'react-native';
import { useApp } from '../AppContext';
import { DEFAULT_SUBSCRIPTION, Subscription, SubscriptionTier } from '../types';
import {
  activateCode,
  fetchSubscriptionByDevice,
} from '../utils/activation';
import { getOrCreateDeviceId } from '../utils/deviceId';
import { isNewerSubscription } from '../utils/subscriptionDiff';

export type SubscriptionType = 'premium' | 'basic_box' | 'vip_box' | 'none';

export type RefreshOutcome =
  | { ok: true; updated: boolean }
  | { ok: false; reason: 'not_bound' | 'no_subscription' | 'invalid_device' | 'network' };

export interface UseSubscriptionApi {
  subscription: Subscription;
  tier: SubscriptionTier;
  /** Friendlier alias used by gates / settings: which kind of plan is active. */
  subscriptionType: SubscriptionType;
  isActive: boolean;
  isBasic: boolean;
  isVip: boolean;
  /** True when any active plan unlocks Premium features (premium / basic / vip). */
  isPremium: boolean;
  /** True when an active plan ships physical boxes (basic / vip). */
  isBoxActive: boolean;
  daysLeft: number;
  /**
   * Send the user-entered activation code to the FlowCare API. On success
   * persists tier + renewsAt locally and returns the resolved tier.
   */
  activate: (code: string) => Promise<
    | { ok: true; tier: SubscriptionTier; expires: string }
    | { ok: false; reason: 'empty' | 'invalid' | 'network' }
  >;
  /** Auto-sync: poll the FlowCare API for the latest subscription bound
   * to this device's id and mirror it locally. Returns whether anything
   * actually changed. Safe to call repeatedly. */
  refreshFromBackend: () => Promise<RefreshOutcome>;
}

const isActiveNow = (sub: Subscription, now = new Date()): boolean => {
  if (sub.tier === 'free' || !sub.renewsAt) return false;
  try {
    return !isBefore(parseISO(sub.renewsAt), now);
  } catch {
    return false;
  }
};

const computeDaysLeft = (sub: Subscription, now = new Date()): number => {
  if (!sub.renewsAt) return 0;
  try {
    const days = differenceInCalendarDays(parseISO(sub.renewsAt), now);
    return Math.max(0, days);
  } catch {
    return 0;
  }
};

const productIdFor = (tariff: SubscriptionTier): string =>
  tariff === 'vip'
    ? 'vip_monthly'
    : tariff === 'premium'
      ? 'premium_monthly'
      : tariff === 'basic'
        ? 'basic_monthly'
        : 'free';

/** Polling interval for the auto-sync refresh while the app is foregrounded. */
const REFRESH_INTERVAL_MS = 5 * 60 * 1000;

/**
 * Subscription state hook.
 *
 * Source of truth: the FlowCare backend (`./api/`) which is fed by the
 * Telegram bot (`./bot/`). The user can either paste the bot-issued
 * 8-char activation code (manual) or link their device once via
 * `/start link_<device_id>` and let the app pull subscription state
 * automatically (auto-sync). Both paths converge on the same local
 * Subscription object.
 */
export const useSubscription = (): UseSubscriptionApi => {
  const { data, updateSubscription } = useApp();
  const sub = data.subscription;
  const subRef = useRef(sub);
  subRef.current = sub;

  useEffect(() => {
    if (sub.tier !== 'free' && sub.renewsAt && !isActiveNow(sub)) {
      void updateSubscription({ ...DEFAULT_SUBSCRIPTION });
    }
  }, [sub, updateSubscription]);

  const refreshFromBackend = useCallback<UseSubscriptionApi['refreshFromBackend']>(
    async () => {
      const deviceId = await getOrCreateDeviceId();
      const result = await fetchSubscriptionByDevice(deviceId);
      if (!result.ok) return { ok: false, reason: result.reason };
      const remote = result.data;
      const current = subRef.current;
      if (!isNewerSubscription(current, remote)) {
        return { ok: true, updated: false };
      }
      const renewsAtIso = `${remote.expires}T00:00:00.000Z`;
      const startedIso = `${remote.started_at}T00:00:00.000Z`;
      const nowIso = new Date().toISOString();
      await updateSubscription({
        tier: remote.tier,
        productId: productIdFor(remote.tier),
        startedAt: startedIso,
        renewsAt: renewsAtIso,
        cancelled: false,
        lastSyncedAt: nowIso,
        activationCode: remote.activation_code ?? current.activationCode,
      });
      return { ok: true, updated: true };
    },
    [updateSubscription],
  );

  // Auto-sync: refresh on mount, on foreground, and every 5 min while
  // foregrounded. Errors (network / not_bound) are swallowed — the UI
  // should never block on this.
  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      void refreshFromBackend();
    };
    tick();
    const interval = setInterval(tick, REFRESH_INTERVAL_MS);
    const onChange = (next: AppStateStatus) => {
      if (next === 'active') tick();
    };
    const sub = AppState.addEventListener('change', onChange);
    return () => {
      cancelled = true;
      clearInterval(interval);
      sub.remove();
    };
  }, [refreshFromBackend]);

  const activate = useCallback<UseSubscriptionApi['activate']>(
    async (code) => {
      const trimmed = code.trim();
      if (!trimmed) return { ok: false, reason: 'empty' };
      const deviceId = await getOrCreateDeviceId();
      const res = await activateCode(trimmed, deviceId);
      if (!res.valid || !res.tariff || !res.expires) {
        return { ok: false, reason: 'invalid' };
      }
      const renewsAtIso = `${res.expires}T00:00:00.000Z`;
      const nowIso = new Date().toISOString();
      await updateSubscription({
        tier: res.tariff,
        productId: productIdFor(res.tariff),
        startedAt: nowIso,
        renewsAt: renewsAtIso,
        cancelled: false,
        lastSyncedAt: nowIso,
        activationCode: trimmed,
      });
      return { ok: true, tier: res.tariff, expires: res.expires };
    },
    [updateSubscription],
  );

  const active = isActiveNow(sub);
  const isBasic = active && sub.tier === 'basic';
  const isVip = active && sub.tier === 'vip';
  const isBoxActive = isBasic || isVip;
  const isPremiumOnly = active && sub.tier === 'premium';
  const isPremium = isPremiumOnly || isBoxActive;
  const subscriptionType: SubscriptionType = !active
    ? 'none'
    : sub.tier === 'vip'
      ? 'vip_box'
      : sub.tier === 'basic'
        ? 'basic_box'
        : sub.tier === 'premium'
          ? 'premium'
          : 'none';

  return {
    subscription: sub,
    tier: sub.tier,
    subscriptionType,
    isActive: active,
    isBasic,
    isVip,
    isPremium,
    isBoxActive,
    daysLeft: computeDaysLeft(sub),
    activate,
    refreshFromBackend,
  };
};
