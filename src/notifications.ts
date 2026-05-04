import { Platform } from 'react-native';
import type { CyclePredictions } from './cycle';
import type { DayLog, Settings } from './types';
import { buildNotificationPlan, NotificationItem } from './notificationPlan';

// expo-notifications imports must be wrapped because the package is unavailable
// in pure web SSR contexts; we lazy-load it.
const isNative = Platform.OS === 'ios' || Platform.OS === 'android';

let cachedNotif: typeof import('expo-notifications') | null = null;
const loadNotif = async (): Promise<typeof import('expo-notifications') | null> => {
  if (!isNative) return null;
  if (cachedNotif) return cachedNotif;
  try {
    cachedNotif = await import('expo-notifications');
    return cachedNotif;
  } catch {
    return null;
  }
};

const TAG = 'cycletracker.scheduled';

export type { NotificationItem, NotificationKey } from './notificationPlan';
export { buildNotificationPlan } from './notificationPlan';

export const isNotificationsSupported = (): boolean => isNative;

export interface ScheduleResult {
  ok: boolean;
  reason?: 'unsupported' | 'denied' | 'error';
  scheduledCount?: number;
}

/** Cancel any of our previous reminders and schedule the new ones based on
 *  the latest predictions. Safe to call from a useEffect on every change. */
export const rescheduleNotifications = async (
  predictions: CyclePredictions,
  settings: Settings,
  logs: Record<string, DayLog>,
  t: (key: string) => string,
): Promise<ScheduleResult> => {
  const Notif = await loadNotif();
  if (!Notif) return { ok: false, reason: 'unsupported' };

  const plan: NotificationItem[] = buildNotificationPlan(
    predictions,
    settings,
    logs,
  );

  // Cancel any of our previous reminders.
  try {
    const existing = await Notif.getAllScheduledNotificationsAsync();
    for (const n of existing) {
      const data = n.content.data as { tag?: string } | undefined;
      if (data && data.tag === TAG) {
        await Notif.cancelScheduledNotificationAsync(n.identifier);
      }
    }
  } catch {
    // ignore
  }

  if (plan.length === 0) return { ok: true, scheduledCount: 0 };

  const perm = await Notif.getPermissionsAsync();
  let granted = perm.granted;
  if (!granted) {
    const req = await Notif.requestPermissionsAsync();
    granted = req.granted;
  }
  if (!granted) return { ok: false, reason: 'denied' };

  let scheduled = 0;
  for (const item of plan) {
    try {
      await Notif.scheduleNotificationAsync({
        content: {
          title: t(item.titleKey),
          body: t(item.bodyKey),
          data: { tag: TAG, key: item.key },
        },
        trigger: {
          type: Notif.SchedulableTriggerInputTypes.DATE,
          date: item.fireAt,
        },
      });
      scheduled += 1;
    } catch {
      // continue scheduling others
    }
  }
  return { ok: true, scheduledCount: scheduled };
};
