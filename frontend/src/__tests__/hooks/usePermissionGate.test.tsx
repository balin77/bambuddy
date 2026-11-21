import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { usePermissionGate } from '../../hooks/usePermissionGate';

const auth = vi.hoisted(() => ({
  held: new Set<string>(),
  hideUnpermitted: false,
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    hasPermission: (p: string) => auth.held.has(p),
    hideUnpermitted: auth.hideUnpermitted,
  }),
}));

function gate(permission: Parameters<ReturnType<typeof usePermissionGate>>[0]) {
  const { result } = renderHook(() => usePermissionGate());
  return result.current(permission);
}

describe('usePermissionGate (#3639)', () => {
  it('draws and allows a control the user may use', () => {
    auth.held = new Set(['printers:control']);
    auth.hideUnpermitted = true;
    expect(gate('printers:control')).toEqual({ allowed: true, render: true });
  });

  it('greys out a control the user may not use when nothing is hidden', () => {
    auth.held = new Set();
    auth.hideUnpermitted = false;
    expect(gate('printers:control')).toEqual({ allowed: false, render: true });
  });

  it('leaves out a control the user may not use when the groups hide them', () => {
    auth.held = new Set();
    auth.hideUnpermitted = true;
    expect(gate('printers:control')).toEqual({ allowed: false, render: false });
  });

  it('allows a list of permissions when any one is held', () => {
    auth.held = new Set(['printers:update']);
    auth.hideUnpermitted = true;
    expect(gate(['printers:control', 'printers:update'])).toEqual({ allowed: true, render: true });
    expect(gate(['printers:control', 'printers:delete'])).toEqual({ allowed: false, render: false });
  });
});
