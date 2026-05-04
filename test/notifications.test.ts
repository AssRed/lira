import { strict as assert } from 'node:assert';
import test from 'node:test';
import {
  buildNotificationPlan,
  dayLogIsEmpty,
  NotificationItem,
} from '../src/notificationPlan';
import type { CyclePredictions } from '../src/cycle';
import type { DayLog, Settings } from '../src/types';
import { DEFAULT_SETTINGS } from '../src/types';

const ALL_OFF: Settings = {
  ...DEFAULT_SETTINGS,
  notifyPrePeriod: false,
  notifyPeriodStart: false,
  notifyOvulationDay: false,
  notifyFertile: false,
  notifyLatePeriod: false,
  notifyDailyLog: false,
};

const ALL_ON: Settings = {
  ...DEFAULT_SETTINGS,
  notifyPrePeriod: true,
  notifyPeriodStart: true,
  notifyOvulationDay: true,
  notifyFertile: true,
  notifyLatePeriod: true,
  notifyDailyLog: true,
};

const PREDICTIONS: CyclePredictions = {
  lastPeriodStart: '2026-01-01',
  nextPeriodStart: '2026-02-01',
  nextPeriodEnd: '2026-02-05',
  ovulation: '2026-01-18',
  fertileStart: '2026-01-13',
  fertileEnd: '2026-01-19',
  cycleDay: 10,
  daysUntilNextPeriod: 22,
  effectiveCycleLength: 31,
  effectivePeriodLength: 5,
  irregular: false,
  averageSource: 'settings',
};

const EMPTY_PREDICTIONS: CyclePredictions = {
  lastPeriodStart: null,
  nextPeriodStart: null,
  nextPeriodEnd: null,
  ovulation: null,
  fertileStart: null,
  fertileEnd: null,
  cycleDay: null,
  daysUntilNextPeriod: null,
  effectiveCycleLength: 28,
  effectivePeriodLength: 5,
  irregular: false,
  averageSource: 'settings',
};

const NOW = new Date('2026-01-10T08:00:00.000Z');

const findItem = (
  plan: NotificationItem[],
  key: NotificationItem['key'],
): NotificationItem | undefined => plan.find((p) => p.key === key);

test('returns empty plan when all toggles are off', () => {
  const plan = buildNotificationPlan(PREDICTIONS, ALL_OFF, {}, NOW);
  assert.equal(plan.length, 0);
});

test('drops every cycle-tied reminder when no predictions are available', () => {
  // The daily-log reminder does not depend on predictions, so it remains —
  // every other key requires nextPeriodStart / ovulation / fertileStart.
  const plan = buildNotificationPlan(EMPTY_PREDICTIONS, ALL_ON, {}, NOW);
  assert.deepEqual(
    plan.map((p) => p.key),
    ['dailyLog'],
  );
});

test('schedules pre-period the day before period at 09:00 local', () => {
  const plan = buildNotificationPlan(
    PREDICTIONS,
    { ...ALL_OFF, notifyPrePeriod: true },
    {},
    NOW,
  );
  assert.equal(plan.length, 1);
  const item = plan[0];
  assert.equal(item.key, 'prePeriod');
  assert.equal(item.titleKey, 'notif.prePeriodTitle');
  assert.equal(item.bodyKey, 'notif.prePeriodBody');
  // Period start is Feb 1 → fire at Jan 31 09:00 local.
  assert.equal(item.fireAt.getDate(), 31);
  assert.equal(item.fireAt.getMonth(), 0); // January (0-indexed)
  assert.equal(item.fireAt.getHours(), 9);
  assert.equal(item.fireAt.getMinutes(), 0);
});

test('schedules period-start on the predicted period day at 09:00 local', () => {
  const plan = buildNotificationPlan(
    PREDICTIONS,
    { ...ALL_OFF, notifyPeriodStart: true },
    {},
    NOW,
  );
  assert.equal(plan.length, 1);
  const item = plan[0];
  assert.equal(item.key, 'periodStart');
  assert.equal(item.fireAt.getDate(), 1);
  assert.equal(item.fireAt.getMonth(), 1); // February
  assert.equal(item.fireAt.getHours(), 9);
});

test('schedules ovulation peak at 09:00 local on ovulation day', () => {
  const plan = buildNotificationPlan(
    PREDICTIONS,
    { ...ALL_OFF, notifyOvulationDay: true },
    {},
    NOW,
  );
  assert.equal(plan.length, 1);
  const item = plan[0];
  assert.equal(item.key, 'ovulation');
  assert.equal(item.fireAt.getDate(), 18);
  assert.equal(item.fireAt.getHours(), 9);
});

test('schedules fertile-start at 09:00 local on the fertile window start', () => {
  const plan = buildNotificationPlan(
    PREDICTIONS,
    { ...ALL_OFF, notifyFertile: true },
    {},
    NOW,
  );
  assert.equal(plan.length, 1);
  const item = plan[0];
  assert.equal(item.key, 'fertileStart');
  assert.equal(item.fireAt.getDate(), 13);
  assert.equal(item.fireAt.getHours(), 9);
});

test('schedules late-period one day after period start at 10:00 local', () => {
  const plan = buildNotificationPlan(
    PREDICTIONS,
    { ...ALL_OFF, notifyLatePeriod: true },
    {},
    NOW,
  );
  assert.equal(plan.length, 1);
  const item = plan[0];
  assert.equal(item.key, 'latePeriod');
  assert.equal(item.fireAt.getDate(), 2);
  assert.equal(item.fireAt.getMonth(), 1); // February
  assert.equal(item.fireAt.getHours(), 10);
});

test('drops items whose fire time is in the past', () => {
  // Period was yesterday (2026-01-09) — pre-period & period-start are now in
  // the past relative to NOW (2026-01-10 08:00). Late-period (Jan 10 10:00)
  // is still in the future and should remain.
  const stalePred: CyclePredictions = {
    ...PREDICTIONS,
    nextPeriodStart: '2026-01-09',
    ovulation: '2025-12-26',
    fertileStart: '2025-12-21',
    fertileEnd: '2025-12-27',
  };
  const plan = buildNotificationPlan(stalePred, ALL_ON, {}, NOW);
  assert.equal(findItem(plan, 'prePeriod'), undefined);
  assert.equal(findItem(plan, 'periodStart'), undefined);
  assert.equal(findItem(plan, 'ovulation'), undefined);
  assert.equal(findItem(plan, 'fertileStart'), undefined);
  const late = findItem(plan, 'latePeriod');
  assert.ok(late, 'latePeriod should still be scheduled when its fire time is in the future');
  assert.equal(late!.fireAt.getDate(), 10);
  assert.equal(late!.fireAt.getHours(), 10);
});

test('schedules daily-log at 21:00 today when today is unlogged and 21:00 is still in the future', () => {
  const morning = new Date('2026-01-10T08:00:00.000Z');
  const plan = buildNotificationPlan(
    EMPTY_PREDICTIONS,
    { ...ALL_OFF, notifyDailyLog: true },
    {},
    morning,
  );
  const dailyLog = findItem(plan, 'dailyLog');
  assert.ok(dailyLog, 'dailyLog reminder should be scheduled when toggle is on and today is unlogged');
  assert.equal(dailyLog!.fireAt.getHours(), 21);
});

test('skips daily-log when today already has a meaningful log', () => {
  const morning = new Date('2026-01-10T08:00:00.000Z');
  // Use the local-date key the plan-builder would compute for `morning`.
  const todayKey = `${morning.getFullYear()}-${String(
    morning.getMonth() + 1,
  ).padStart(2, '0')}-${String(morning.getDate()).padStart(2, '0')}`;
  const logs: Record<string, DayLog> = {
    [todayKey]: { date: todayKey, flow: 'medium' },
  };
  const plan = buildNotificationPlan(
    EMPTY_PREDICTIONS,
    { ...ALL_OFF, notifyDailyLog: true },
    logs,
    morning,
  );
  assert.equal(findItem(plan, 'dailyLog'), undefined);
});

test('treats logs with only flow=none / empty arrays / blank notes as empty', () => {
  assert.equal(dayLogIsEmpty(undefined), true);
  assert.equal(dayLogIsEmpty(null), true);
  assert.equal(dayLogIsEmpty({ date: '2026-01-10' }), true);
  assert.equal(
    dayLogIsEmpty({ date: '2026-01-10', flow: 'none', symptoms: [], moods: [], notes: '   ' }),
    true,
  );
  assert.equal(dayLogIsEmpty({ date: '2026-01-10', flow: 'light' }), false);
  assert.equal(dayLogIsEmpty({ date: '2026-01-10', symptoms: ['cramps'] }), false);
  assert.equal(dayLogIsEmpty({ date: '2026-01-10', moods: ['happy'] }), false);
  assert.equal(dayLogIsEmpty({ date: '2026-01-10', notes: 'felt great' }), false);
  assert.equal(dayLogIsEmpty({ date: '2026-01-10', temperature: 36.7 }), false);
  assert.equal(dayLogIsEmpty({ date: '2026-01-10', intimacy: true }), false);
});

test('all-on plan is ordered: prePeriod, periodStart, ovulation, fertileStart, latePeriod, dailyLog', () => {
  const plan = buildNotificationPlan(PREDICTIONS, ALL_ON, {}, NOW);
  const keys = plan.map((p) => p.key);
  assert.deepEqual(keys, [
    'prePeriod',
    'periodStart',
    'ovulation',
    'fertileStart',
    'latePeriod',
    'dailyLog',
  ]);
});
