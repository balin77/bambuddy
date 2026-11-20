/**
 * A slot that waits for a colour from the inventory takes no tray (#3649).
 */

import { describe, it, expect } from 'vitest';
import { buildAmsMapping, buildFilamentComparison, buildLoadedFilaments } from '../../hooks/useFilamentMapping';
import type { PrinterStatus } from '../../api/client';

const status = {
  ams: [
    {
      id: 0,
      tray: [
        { id: 0, tray_type: 'PLA', tray_color: 'FFFFFFFF', tray_info_idx: 'GFA00' },
        { id: 1, tray_type: 'PLA', tray_color: '00FF00FF', tray_info_idx: 'GFA00' },
        { id: 2, tray_type: 'PLA', tray_color: 'FF0000FF', tray_info_idx: 'GFA00' },
      ],
    },
  ],
  vt_tray: [],
} as unknown as PrinterStatus;

const reqs = {
  filaments: [
    { slot_id: 1, type: 'PLA', color: '#FFFFFF', used_grams: 10 },
    { slot_id: 2, type: 'PLA', color: '#C0392B', used_grams: 10 },
    { slot_id: 3, type: 'PLA', color: '#00FF00', used_grams: 10 },
  ],
};

describe('buildFilamentComparison with inventory slots', () => {
  const loaded = buildLoadedFilaments(status);

  it('without the set, a missing colour is stood in for by a loaded tray of the type', () => {
    expect(buildAmsMapping(buildFilamentComparison(reqs, loaded, {}))![1]).toBeGreaterThanOrEqual(0);
  });

  it('gives the slot no tray and status inventory, and keeps the other slots on their trays', () => {
    const comparison = buildFilamentComparison(reqs, loaded, {}, false, undefined, false, new Set([2]));

    expect(comparison[1]).toMatchObject({ slot_id: 2, loaded: undefined, hasFilament: false, status: 'inventory' });
    expect(buildAmsMapping(comparison)).toEqual([0, -1, 1]);
  });

  it('does not hold a tray back for the other slots', () => {
    // Slot 2 would auto-match tray 2 (red, similar), which slot 3 does not want; but a
    // tray picked by hand for the waiting slot must be free again.
    const comparison = buildFilamentComparison(reqs, loaded, { 2: 1 }, false, undefined, false, new Set([2]));

    expect(buildAmsMapping(comparison)).toEqual([0, -1, 1]);
  });

  it('is not a mismatch of any kind', () => {
    const comparison = buildFilamentComparison(reqs, loaded, {}, false, undefined, false, new Set([1, 2, 3]));

    expect(comparison.every((c) => c.status === 'inventory' && !c.typeMatch)).toBe(true);
    expect(buildAmsMapping(comparison)).toEqual([-1, -1, -1]);
  });

  it('changes nothing without the set', () => {
    expect(buildFilamentComparison(reqs, loaded, {}, false, undefined, false, new Set())).toEqual(
      buildFilamentComparison(reqs, loaded, {}),
    );
  });
});
