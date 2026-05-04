import { isBefore, parseISO } from 'date-fns';
import type { Subscription } from '../types';

export interface RemoteSubscriptionSnapshot {
  tier: Subscription['tier'];
  /** ISO `YYYY-MM-DD` from the FlowCare API. */
  expires: string;
}

/**
 * Pure (no React Native deps) decision helper for the auto-sync hook:
 * "should I overwrite my local subscription with what the backend just
 * told me?". Returns true when the remote snapshot is strictly fresher
 * than the local one — different tier, missing local renewsAt, or a
 * later expiration date.
 *
 * Lives in its own file so tests can exercise it under tsx --test.
 */
export const isNewerSubscription = (
  current: Pick<Subscription, 'tier' | 'renewsAt'>,
  remote: RemoteSubscriptionSnapshot,
): boolean => {
  if (current.tier !== remote.tier) return true;
  if (!current.renewsAt) return true;
  try {
    const localDate = parseISO(current.renewsAt);
    const remoteDate = parseISO(`${remote.expires}T00:00:00.000Z`);
    if (Number.isNaN(localDate.getTime())) return true;
    if (Number.isNaN(remoteDate.getTime())) return false;
    return isBefore(localDate, remoteDate);
  } catch {
    return true;
  }
};
