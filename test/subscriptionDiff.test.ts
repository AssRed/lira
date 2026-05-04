import { strict as assert } from 'node:assert';
import test from 'node:test';

import { isNewerSubscription } from '../src/utils/subscriptionDiff';
import type { Subscription } from '../src/types';

const baseLocal = (overrides: Partial<Subscription> = {}): Subscription => ({
  tier: 'premium',
  productId: 'premium_monthly',
  startedAt: '2026-01-01T00:00:00.000Z',
  renewsAt: '2026-01-31T00:00:00.000Z',
  cancelled: false,
  lastSyncedAt: '2026-01-01T00:00:00.000Z',
  activationCode: null,
  ...overrides,
});

test('treats a different remote tier as newer', () => {
  assert.equal(
    isNewerSubscription(baseLocal({ tier: 'free' }), { tier: 'premium', expires: '2026-01-31' }),
    true,
  );
  assert.equal(
    isNewerSubscription(baseLocal({ tier: 'premium' }), { tier: 'vip', expires: '2026-01-31' }),
    true,
  );
});

test('treats missing local renewsAt as newer', () => {
  assert.equal(
    isNewerSubscription(baseLocal({ renewsAt: null }), { tier: 'premium', expires: '2026-01-31' }),
    true,
  );
});

test('returns true when remote expires later than local renewsAt', () => {
  const local = baseLocal({ renewsAt: '2026-01-15T00:00:00.000Z' });
  assert.equal(
    isNewerSubscription(local, { tier: 'premium', expires: '2026-02-01' }),
    true,
  );
});

test('returns false when remote expires equal to local renewsAt', () => {
  const local = baseLocal({ renewsAt: '2026-01-31T00:00:00.000Z' });
  assert.equal(
    isNewerSubscription(local, { tier: 'premium', expires: '2026-01-31' }),
    false,
  );
});

test('returns false when remote expires earlier than local renewsAt', () => {
  const local = baseLocal({ renewsAt: '2026-02-15T00:00:00.000Z' });
  assert.equal(
    isNewerSubscription(local, { tier: 'premium', expires: '2026-01-31' }),
    false,
  );
});

test('treats a malformed local renewsAt as newer (defensive fallback)', () => {
  const local = baseLocal({ renewsAt: 'not-an-iso-date' });
  assert.equal(
    isNewerSubscription(local, { tier: 'premium', expires: '2026-01-31' }),
    true,
  );
});
