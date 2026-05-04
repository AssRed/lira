import { addDays, format, parseISO, startOfDay } from 'date-fns';
import type { CyclePredictions } from './cycle';
import type { DayLog, Settings } from './types';

/**
 * Pure (no React Native / Expo deps) logic for building the list of
 * future-only reminders that the app should schedule. Lives in a separate
 * file from `notifications.ts` so it can be unit-tested under `tsx --test`
 * without pulling in `react-native` / `expo-notifications`.
 */

export type NotificationKey =
  | 'prePeriod'
  | 'periodStart'
  | 'ovulation'
  | 'fertileStart'
  | 'latePeriod'
  | 'dailyLog';

export interface NotificationItem {
  key: NotificationKey;
  fireAt: Date;
  titleKey: string;
  bodyKey: string;
}

const at = (iso: string, hour: number, minute: number = 0): Date => {
  const d = startOfDay(parseISO(iso));
  d.setHours(hour, minute, 0, 0);
  return d;
};

const isFuture = (when: Date, now: Date): boolean =>
  when.getTime() > now.getTime();

export const dayLogIsEmpty = (log: DayLog | undefined | null): boolean => {
  if (!log) return true;
  if (log.flow && log.flow !== 'none') return false;
  if (log.symptoms && log.symptoms.length > 0) return false;
  if (log.moods && log.moods.length > 0) return false;
  if (log.notes && log.notes.trim().length > 0) return false;
  if (log.temperature !== undefined && log.temperature !== null) return false;
  if (log.intimacy) return false;
  return true;
};

export const buildNotificationPlan = (
  predictions: CyclePredictions,
  settings: Settings,
  logs: Record<string, DayLog>,
  now: Date = new Date(),
): NotificationItem[] => {
  const items: NotificationItem[] = [];
  const period = predictions.nextPeriodStart;
  const ovulation = predictions.ovulation;
  const fertileStart = predictions.fertileStart;

  if (settings.notifyPrePeriod && period) {
    const fire = addDays(at(period, 9), -1);
    if (isFuture(fire, now)) {
      items.push({
        key: 'prePeriod',
        fireAt: fire,
        titleKey: 'notif.prePeriodTitle',
        bodyKey: 'notif.prePeriodBody',
      });
    }
  }

  if (settings.notifyPeriodStart && period) {
    const fire = at(period, 9);
    if (isFuture(fire, now)) {
      items.push({
        key: 'periodStart',
        fireAt: fire,
        titleKey: 'notif.periodStartTitle',
        bodyKey: 'notif.periodStartBody',
      });
    }
  }

  if (settings.notifyOvulationDay && ovulation) {
    const fire = at(ovulation, 9);
    if (isFuture(fire, now)) {
      items.push({
        key: 'ovulation',
        fireAt: fire,
        titleKey: 'notif.ovulationTitle',
        bodyKey: 'notif.ovulationBody',
      });
    }
  }

  if (settings.notifyFertile && fertileStart) {
    const fire = at(fertileStart, 9);
    if (isFuture(fire, now)) {
      items.push({
        key: 'fertileStart',
        fireAt: fire,
        titleKey: 'notif.fertileStartTitle',
        bodyKey: 'notif.fertileStartBody',
      });
    }
  }

  if (settings.notifyLatePeriod && period) {
    // One day after the predicted period start, at 10:00. If today is already
    // past that mark we don't try to fire in the past — the user is already
    // visibly late on the Today screen and a stale push would be redundant.
    const fire = addDays(at(period, 10), 1);
    if (isFuture(fire, now)) {
      items.push({
        key: 'latePeriod',
        fireAt: fire,
        titleKey: 'notif.latePeriodTitle',
        bodyKey: 'notif.latePeriodBody',
      });
    }
  }

  if (settings.notifyDailyLog) {
    const today = startOfDay(now);
    const at21 = new Date(today);
    at21.setHours(21, 0, 0, 0);
    const todayKey = format(today, 'yyyy-MM-dd');
    if (isFuture(at21, now) && dayLogIsEmpty(logs[todayKey])) {
      items.push({
        key: 'dailyLog',
        fireAt: at21,
        titleKey: 'notif.dailyLogTitle',
        bodyKey: 'notif.dailyLogBody',
      });
    }
  }

  return items;
};
