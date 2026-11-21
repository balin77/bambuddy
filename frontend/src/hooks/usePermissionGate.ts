import { useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';
import type { Permission } from '../api/client';

export interface PermissionGate {
  /** The user holds the permission (any of them, when several are given) */
  allowed: boolean;
  /** Draw the control: it is allowed, or the user's groups do not hide what they cannot use (#3639) */
  render: boolean;
}

/**
 * Decides how a permission-gated control is drawn.
 *
 *     const g = gate('printers:control');
 *     {g.render && <button disabled={!g.allowed || offline}>...</button>}
 *
 * Without the group option a control the user may not use is greyed out, as
 * always. With it, it is left out. A control that is disabled for another
 * reason (offline, busy) stays drawn: put that reason in `disabled`, not in
 * `render`. Display only; the server checks every permission.
 */
export function usePermissionGate(): (permission: Permission | Permission[]) => PermissionGate {
  const { hasPermission, hideUnpermitted } = useAuth();
  return useCallback(
    (permission) => {
      const wanted = Array.isArray(permission) ? permission : [permission];
      const allowed = wanted.some((p) => hasPermission(p));
      return { allowed, render: allowed || !hideUnpermitted };
    },
    [hasPermission, hideUnpermitted],
  );
}
