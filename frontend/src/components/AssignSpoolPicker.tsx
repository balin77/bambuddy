import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Loader2, Package, Search, QrCode, ArrowLeft } from 'lucide-react';
import { api } from '../api/client';
import type { InventorySpool, SpoolAssignment } from '../api/client';
import { Button } from './Button';
import { MaterialMismatchConfirm } from './MaterialMismatchConfirm';
import { QrSpoolScanner } from './QrSpoolScanner';
import { useToast } from '../contexts/ToastContext';
import { findMaterialMismatch, normalizeValue, stripProfileQualifier, type MaterialMismatch } from '../utils/assignMismatch';
import { exactSpoolIdQuery, filterSpoolsByQuery } from '../utils/inventorySearch';
import { colorsAreSimilar } from '../utils/amsHelpers';
import { FilamentSwatch } from './FilamentSwatch';
import { getSwatchStyle, resolveSpoolColorName } from '../utils/colors';
import { parseSpoolQr, scannedSpoolId } from '../utils/qrAssignTarget';
import { useUiSettings } from '../hooks/useUiSettings';

export interface AssignSpoolTrayInfo {
  type: string;
  material?: string;
  profile?: string;
  color: string;
  location: string;
  /**
   * For a slot reporting no filament: getEmptySlotKind's answer. Only
   * 'physical' (the firmware says no spool) reads as an empty slot; anything
   * else may be a spool it can't identify (#2527).
   */
  emptyKind?: 'physical' | 'reset' | null;
}

/** The filament a waiting job wants in the slot (#3726): spools that cover it come first. */
export interface AssignSpoolWanted {
  type: string;
  color: string;
  color_name: string;
  required_g: number | null;
}

interface AssignSpoolPickerProps {
  /** `modal`: the dialog's body and footer. `inline`: a list with one tap per spool, inside a To do entry. */
  layout: 'modal' | 'inline';
  /** An assignment went through. */
  onDone: () => void;
  /** Cancel (modal) / Back (inline). */
  onCancel: () => void;
  /** The scanner replaced the list (the modal's title follows it). */
  onScanningChange?: (scanning: boolean) => void;
  wanted?: AssignSpoolWanted;
  /** Inline only: opens the new-spool form; the button is absent without it. */
  onNewSpool?: () => void;
  /** Inline only: the new-spool button is drawn but the caller may not use it. */
  newSpoolDisabled?: boolean;
  newSpoolDisabledTitle?: string;
  /** Inline only: the slot's name ("A3") in the heading. */
  slotLabel?: string;
  printerId: number;
  amsId: number;
  trayId: number;
  trayInfo?: AssignSpoolTrayInfo;
  spoolmanEnabled?: boolean;
}

function spoolSummary(spool: InventorySpool): string {
  return [spool.brand, spool.material, spool.subtype].filter(Boolean).join(' ');
}

export function AssignSpoolPicker({
  layout,
  onDone,
  onCancel,
  onScanningChange,
  wanted,
  onNewSpool,
  newSpoolDisabled,
  newSpoolDisabledTitle,
  slotLabel,
  printerId,
  amsId,
  trayId,
  trayInfo,
  spoolmanEnabled,
}: AssignSpoolPickerProps) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [disableFiltering, setDisableFiltering] = useState(false);
  const [selectedSpoolId, setSelectedSpoolId] = useState<number | null>(null);
  const [selectedSpoolmanSpoolId, setSelectedSpoolmanSpoolId] = useState<number | null>(null);
  useEffect(() => {
    setSelectedSpoolId(null);
    setSelectedSpoolmanSpoolId(null);
  }, [disableFiltering]);
  const [searchFilter, setSearchFilter] = useState('');
  // A pick waiting on the material-mismatch confirm, with what
  // findMaterialMismatch found. `move` for a scanned spool (#1574): the one in
  // the user's hand leaves any other slot it is in.
  const [mismatch, setMismatch] = useState<{ spoolId: number; move: boolean; details: MaterialMismatch } | null>(null);
  // Scanning a spool's QR instead of picking it (#1574), into this same slot.
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  // Synchronous in-flight guard: a mutation's isPending only updates next render.
  const scanInFlightRef = useRef(false);

  // The picker is mounted when it is shown, so its state starts clean each time.
  useEffect(() => {
    onScanningChange?.(scanning);
  }, [scanning, onScanningChange]);

  // Unique cache key — different consumers of `['inventory-spools']` call
  // `getSpools()` with different `includeArchived` arguments (InventoryPage:
  // true, SpoolBuddyDashboard / SpoolBuddyInventoryPage: false), but they
  // all share the same key. React Query treats them as one query and
  // serves whichever response landed first, so a SpoolBuddy component
  // priming the cache with the archived-excluded payload makes the picker
  // miss spools that *are* archived OR (more subtly) miss any spool that
  // wasn't yet present when SpoolBuddy ran its initial fetch. The picker
  // gets its own key + a fetch-everything call so this consumer is never
  // at the mercy of someone else's cache state. Archived spools are then
  // explicitly excluded client-side because the backend rejects archived
  // assignments with HTTP 400 anyway, so listing them would only let the
  // user click a button that fails.
  const { data: spools, isLoading, isFetching: spoolsFetching } = useQuery({
    queryKey: ['inventory-spools', 'assign-modal'],
    queryFn: () => api.getSpools(true),
    enabled: !spoolmanEnabled,
  });

  const { data: assignments } = useQuery({
    queryKey: ['spool-assignments'],
    queryFn: () => api.getAssignments(),
  });

  const { data: settings } = useUiSettings();

  const { data: spoolmanSpools, isLoading: spoolmanLoading } = useQuery({
    queryKey: ['spoolman-inventory-spools', 'assign-modal'],
    queryFn: () => api.getSpoolmanInventorySpools(false),
    enabled: !!spoolmanEnabled,
  });

  // Spoolman SlotAssignments across all printers — used to filter out spools
  // already bound to another slot. Without this filter the modal offers spools
  // that are already in use elsewhere (e.g. an h2d-1 slot's spool appearing
  // in the x1c-2 assign list), and assigning would silently steal it from
  // the other printer's slot.
  const { data: allSpoolmanAssignments } = useQuery({
    // Under the per-slot key, so every slot invalidation refreshes it too.
    queryKey: ['spoolman-slot-assignments', 'all'],
    queryFn: () => api.getSpoolmanSlotAssignments(),
    enabled: !!spoolmanEnabled,
  });

  // ids of spools already in some Spoolman slot — excluding the current slot
  // (so a user could in theory re-pick the same spool, though the modal is
  // typically only opened from empty slots).
  const assignedSpoolmanSpoolIds = useMemo(() => {
    if (!allSpoolmanAssignments) return new Set<number>();
    return new Set(
      allSpoolmanAssignments
        .filter(a => !(a.printer_id === printerId && a.ams_id === amsId && a.tray_id === trayId))
        .map(a => a.spoolman_spool_id),
    );
  }, [allSpoolmanAssignments, printerId, amsId, trayId]);

  // #1414: nudge the printer to republish its state after we assign a
  // spool. The backend assign-spool path already issues an MQTT command,
  // but firmware (especially A1 mini external slots and any non-RFID
  // assignment) doesn't always echo the new tray state back on its own,
  // so the printer card sits on stale data and the user has to press
  // Force-refresh to see the assignment. Calling /refresh-status forces
  // a pushall the way the Force-refresh button does. Failures are
  // intentionally swallowed — the assignment itself succeeded; if the
  // refresh is offline the next poll / websocket update will catch up.
  const nudgePrinterRepublish = () => {
    api.refreshPrinterStatus(printerId).catch(() => {});
    queryClient.invalidateQueries({ queryKey: ['printerStatus', printerId] });
  };

  const assignMutation = useMutation({
    mutationFn: ({ spoolId, move }: { spoolId: number; move?: boolean }) =>
      api.assignSpool({ spool_id: spoolId, printer_id: printerId, ams_id: amsId, tray_id: trayId, ...(move && { move }) }),
    onSuccess: (newAssignment, { move }) => {
      // Immediately update cache so UI reflects the new assignment without waiting for refetch
      queryClient.setQueryData<SpoolAssignment[]>(['spool-assignments'], (old) => {
        const filtered = (old || []).filter(a =>
          !(a.printer_id === printerId && a.ams_id === amsId && a.tray_id === trayId) &&
          // A move took the spool out of its other slots as well.
          !(move && a.spool_id === newAssignment.spool_id)
        );
        filtered.push(newAssignment);
        return filtered;
      });
      queryClient.invalidateQueries({ queryKey: ['spool-assignments'] });
      nudgePrinterRepublish();
      // When the AMS slot was empty at assign time (tray_state ∈ {9, 10}), the
      // backend persists the assignment but deliberately skips the MQTT
      // `ams_filament_setting` push because Bambu firmware drops it silently
      // for empty slots. `on_ams_change` re-fires the configuration once a
      // spool is detected in the slot (#1680). The success-but-pending case
      // gets a distinct toast so the user understands the slot hasn't been
      // configured on the printer yet — saying "AMS slot configured" reads
      // as a lie in that state. Mirror of `spoolbuddy/AssignToAmsModal.tsx`,
      // which has handled this since the SpoolBuddy assign flow shipped.
      const toastKey = newAssignment.pending_config
        ? 'inventory.assignPendingInsert'
        : 'inventory.assignSuccess';
      showToast(t(toastKey), 'success');
      setMismatch(null);
      onDone();
    },
    onError: (error: Error) => {
      showToast(`${t('inventory.assignFailed')}: ${error.message}`, 'error');
      scanInFlightRef.current = false; // a scan can try again
    },
  });

  const assignSpoolmanMutation = useMutation({
    mutationFn: ({ spoolmanSpoolId, move }: { spoolmanSpoolId: number; move?: boolean }) =>
      api.assignSpoolmanSlot({
        spoolman_spool_id: spoolmanSpoolId,
        printer_id: printerId,
        ams_id: amsId,
        tray_id: trayId,
        ...(move && { move }),
      }),
    onSuccess: (_data, { move }) => {
      queryClient.invalidateQueries({ queryKey: ['spoolman-inventory-spools'] });
      // Prefix match: also the all-printers list this dialog filters
      // "assigned elsewhere" by.
      queryClient.invalidateQueries({ queryKey: ['spoolman-slot-assignments'] });
      // A move clears the fallback tag linking the spool to its old slot.
      if (move) queryClient.invalidateQueries({ queryKey: ['linked-spools'] });
      nudgePrinterRepublish();
      showToast(t('inventory.assignSuccess'), 'success');
      onDone();
    },
    onError: (error: Error) => {
      const message = `${t('inventory.assignFailed')}: ${error.message}`;
      // A scan says why in the scanner: a toast sits under this dialog's
      // backdrop, the SpoolBuddy kiosk shows none, and the scanner doesn't send
      // a label again while it stays in view. (A built-in assign's error shows
      // below the dialog's buttons.)
      if (scanInFlightRef.current) setScanError(message);
      else showToast(message, 'error');
      scanInFlightRef.current = false; // a scan can try again
    },
  });

  // Filter out spools already assigned to other slots
  const assignedSpoolIds = new Set(
    (assignments || [])
      .filter(a => !(a.printer_id === printerId && a.ams_id === amsId && a.tray_id === trayId))
      .map(a => a.spool_id)
  );
  // Show every spool that isn't already taken by another slot — including
  // RFID-tagged Bambu Lab spools (#1133). The earlier "manual spools only"
  // gate (tag_uid && tray_uuid both null) blocked the workflow where a
  // user has a Bambu Lab spool in inventory but doesn't want to scan it
  // via SpoolBuddy NFC every time and just wants to pick it from the list.
  // External slots (amsId 254/255) have always been allowed to pick from
  // any spool because the slot itself has no RFID reader; that
  // distinction collapses now that AMS slots also accept any spool.
  //
  // The "Show all spools" toggle (disableFiltering) bypasses BOTH this
  // gate and the material/profile filter below, making it a real escape
  // hatch for cases where MQTT has auto-reassigned a spool to another
  // slot a fraction of a second after a manual unassign — without this,
  // the toggle's label is a lie ("Show all" but actually filters by
  // assignment). The backend's assign_spool route is upsert-per-
  // (printer, ams, tray), so picking a spool that's currently taken by
  // a different slot creates a second assignment row; that's a foot-gun
  // for normal flows but exactly the recovery path the toggle is for.
  const availableSpools = spools?.filter((spool: InventorySpool) =>
    !spool.archived_at &&
    (disableFiltering || !assignedSpoolIds.has(spool.id))
  );

  // Filtering logic with toggle: search filter always applies, AMS tray profile filter is optional.
  // Show a spool if EITHER the slicer profile matches exactly OR the material overlaps with the
  // tray's material (partial-match both directions — "PLA" spool accepts a "PLA Basic" slot and
  // vice versa). Manually-added inventory spools typically have no slicer_filament_name; gating
  // on strict profile equality alone hid them even when the material matched (#1047).
  //
  // A "#123" search skips the tray match: typing a spool's number is choosing
  // that spool, and the material-mismatch warning still asks on assign
  // (#3301). Before, a spool of another material came up empty for its own
  // number, as if it had been deleted.
  const exactSpoolId = exactSpoolIdQuery(searchFilter);
  let filteredSpools = availableSpools;
  if (!disableFiltering && exactSpoolId === null) {
    const trayProfile = stripProfileQualifier(normalizeValue(trayInfo?.profile));
    const trayMaterial = normalizeValue(trayInfo?.material || trayInfo?.type);
    if (trayProfile || trayMaterial) {
      filteredSpools = filteredSpools?.filter((spool: InventorySpool) => {
        const spoolProfile = stripProfileQualifier(normalizeValue(spool.slicer_filament_name || spool.slicer_filament));
        const spoolMaterial = normalizeValue(spool.material);
        if (trayProfile && spoolProfile && spoolProfile === trayProfile) return true;
        if (trayMaterial && spoolMaterial) {
          return (
            spoolMaterial === trayMaterial ||
            trayMaterial.includes(spoolMaterial) ||
            spoolMaterial.includes(trayMaterial)
          );
        }
        // Neither side has filterable info on whatever dimension remains — show it.
        return !spoolProfile && !spoolMaterial;
      });
    }
  }
  if (searchFilter && filteredSpools) {
    filteredSpools = filterSpoolsByQuery(filteredSpools, searchFilter);
  }
  // Why a "#123" search found nothing, when it did -- the spool is not gone
  // just because it is not offered here.
  let exactSpoolMissReason: string | null = null;
  if (exactSpoolId !== null && spools && filteredSpools?.length === 0) {
    const wanted = spools.find((spool: InventorySpool) => spool.id === exactSpoolId);
    exactSpoolMissReason = !wanted
      ? t('inventory.spoolIdNotFound', { id: exactSpoolId })
      : wanted.archived_at
        ? t('inventory.spoolIdArchived', { id: exactSpoolId })
        : t('inventory.spoolIdInOtherSlot', { id: exactSpoolId });
  }

  // Assign a built-in spool, asking first when its material doesn't match the
  // slot's. Shared by the picker and the QR scan.
  const requestAssign = (spool: InventorySpool, move: boolean) => {
    const details = !settings?.disable_filament_warnings && trayInfo ? findMaterialMismatch(spool, trayInfo) : null;
    if (details) {
      setMismatch({ spoolId: spool.id, move, details });
      return;
    }
    assignMutation.mutate({ spoolId: spool.id, move });
  };

  const handleAssign = () => {
    if (selectedSpoolmanSpoolId !== null) {
      assignSpoolmanMutation.mutate({ spoolmanSpoolId: selectedSpoolmanSpoolId });
      return;
    }
    if (!selectedSpoolId) return;
    const selectedSpool = spools?.find((spool: InventorySpool) => spool.id === selectedSpoolId);
    if (!selectedSpool) {
      showToast(t('inventory.assignFailed'), 'error');
      return;
    }
    requestAssign(selectedSpool, false);
  };

  const handleConfirmMismatch = () => {
    if (!mismatch) return;
    assignMutation.mutate({ spoolId: mismatch.spoolId, move: mismatch.move });
    setMismatch(null);
  };

  const cancelMismatch = () => {
    setMismatch(null);
    scanInFlightRef.current = false; // back to scanning, if that's where it came from
  };

  // A scanned label (#1574) goes to this slot — the one the dialog was opened
  // for, so there is no target to pick. The spool is the one in the user's
  // hand, so it moves here from any other slot; the picker's "assigned
  // elsewhere" filter doesn't apply. The dialog closes when the assign succeeds.
  const handleScan = (text: string) => {
    if (scanInFlightRef.current || assignMutation.isPending || assignSpoolmanMutation.isPending) return;
    const scanned = parseSpoolQr(text);
    if (!scanned) {
      setScanError(t('inventory.qrAssign.invalidQr'));
      return;
    }
    const id = scannedSpoolId(scanned, !!spoolmanEnabled);
    if (id === null) {
      setScanError(t('inventory.qrAssign.spoolmanLabel'));
      return;
    }
    if (spoolmanEnabled) {
      // Spoolman's spool list here leaves archived spools out, so the backend,
      // which looks the spool up itself, is the one to refuse a missing or
      // archived spool.
      setScanError(null);
      scanInFlightRef.current = true;
      assignSpoolmanMutation.mutate({ spoolmanSpoolId: id, move: true });
      return;
    }
    const spool = spools?.find((s: InventorySpool) => s.id === id);
    if (!spool) {
      setScanError(t('inventory.spoolIdNotFound', { id }));
      return;
    }
    if (spool.archived_at) {
      setScanError(t('inventory.spoolIdArchived', { id }));
      return;
    }
    setScanError(null);
    scanInFlightRef.current = true;
    requestAssign(spool, true);
  };

  const stopScanning = () => {
    setScanning(false);
    setScanError(null);
    scanInFlightRef.current = false;
  };

  const isAssigning = assignMutation.isPending || assignSpoolmanMutation.isPending;

  // What the slot holds now, for the context box: the spool assigned to it,
  // else what the printer reports there.
  const currentSpool: { id: number; spool?: InventorySpool } | null = (() => {
    if (spoolmanEnabled) {
      const row = allSpoolmanAssignments?.find(a => a.printer_id === printerId && a.ams_id === amsId && a.tray_id === trayId);
      return row ? { id: row.spoolman_spool_id, spool: spoolmanSpools?.find(s => s.id === row.spoolman_spool_id) } : null;
    }
    const row = assignments?.find(a => a.printer_id === printerId && a.ams_id === amsId && a.tray_id === trayId);
    return row ? { id: row.spool_id, spool: row.spool ?? spools?.find(s => s.id === row.spool_id) } : null;
  })();
  // No filament reported is an empty slot only when the firmware says so; a
  // spool it can't identify reports none too (#2527).
  const physicalLabel = trayInfo?.type || (trayInfo?.emptyKind === 'physical' ? t('ams.emptySlot') : t('ams.emptySlotReset'));

  if (layout === 'inline') {
    // What a spool has left, and whether it covers the job.
    const remainingOf = (spool: InventorySpool) => Math.max(0, (spool.label_weight ?? 0) - (spool.weight_used ?? 0));
    const required = wanted?.required_g ?? null;
    const covers = (spool: InventorySpool) => required === null || !spool.label_weight || remainingOf(spool) >= required;
    // Spools of the wanted colour (unless every spool is asked for), those
    // that cover the job first, then by what is left; a spool that does not
    // cover it stays in the list, dimmed, with the reason.
    const shown = (list: InventorySpool[] | undefined) => {
      let rows = list ?? [];
      if (wanted?.color && !disableFiltering && exactSpoolId === null) {
        rows = rows.filter((spool) => !spool.rgba || colorsAreSimilar(`#${spool.rgba.slice(0, 6)}`, wanted.color));
      }
      return [...rows].sort((a, b) => Number(covers(b)) - Number(covers(a)) || remainingOf(b) - remainingOf(a));
    };
    const builtIn = spoolmanEnabled ? [] : shown(filteredSpools);
    const spoolman = spoolmanEnabled
      ? shown(
          filterSpoolsByQuery(
            (spoolmanSpools ?? []).filter((s) => !s.archived_at && !assignedSpoolmanSpoolIds.has(s.id)),
            searchFilter,
          ),
        )
      : [];
    const rows = spoolmanEnabled ? spoolman : builtIn;
    const loading = spoolmanEnabled ? spoolmanLoading : isLoading;
    const firstCovering = rows.findIndex(covers);
    const filament = wanted ? [wanted.type, wanted.color_name].filter(Boolean).join(' ') : '';
    const grams = required === null ? '' : new Intl.NumberFormat(i18n.language, { style: 'unit', unit: 'gram', unitDisplay: 'short', maximumFractionDigits: 0 }).format(required);
    const gramsOf = (spool: InventorySpool) => new Intl.NumberFormat(i18n.language, { style: 'unit', unit: 'gram', unitDisplay: 'short', maximumFractionDigits: 0 }).format(remainingOf(spool));
    const assignOf = (spool: InventorySpool) => {
      if (spoolmanEnabled) assignSpoolmanMutation.mutate({ spoolmanSpoolId: spool.id });
      else requestAssign(spool, false);
    };
    const buttonBase = 'min-h-[44px] sm:min-h-[36px] px-4 rounded-lg text-sm font-semibold disabled:opacity-50';
    return (
      <div data-testid="todo-assign-picker" className="min-w-0 space-y-3">
        <div className="space-y-1">
          <h4 className="text-[15px] font-semibold text-white">{t('queueTodo.assign.title', { slot: slotLabel ?? '' })}</h4>
          {filament && (
            <p className="text-[13px] text-bambu-gray-light break-words">
              {grams ? t('queueTodo.assign.subtitleNeeds', { filament, grams }) : t('queueTodo.assign.subtitle', { filament })}
            </p>
          )}
        </div>
        {scanning ? (
          <QrSpoolScanner onDecode={handleScan} busy={isAssigning || mismatch !== null || spoolsFetching} error={scanError} />
        ) : (
          <>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bambu-gray" />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                aria-label={t('inventory.searchSpools')}
                placeholder={t('inventory.searchSpools')}
                className="w-full pl-9 pr-3 min-h-[44px] sm:min-h-[36px] bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm placeholder:text-bambu-gray focus:outline-none focus:border-bambu-green"
              />
            </div>
            {loading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="w-5 h-5 text-bambu-green animate-spin" />
              </div>
            ) : rows.length > 0 ? (
              <ul className="space-y-2" data-testid="todo-assign-list">
                {rows.map((spool, i) => {
                  const enough = covers(spool);
                  const primary = i === firstCovering;
                  const name = [spool.brand, spool.material, spool.subtype].filter(Boolean).join(' ');
                  const state = spool.weight_used > 0 ? t('queueTodo.assign.opened') : t('queueTodo.assign.fresh');
                  return (
                    <li
                      key={`${spoolmanEnabled ? 'spoolman' : 'spool'}-${spool.id}`}
                      data-testid="todo-assign-spool"
                      data-enough={enough ? 'true' : 'false'}
                      className={`flex items-center gap-3 rounded-[10px] px-3 py-2.5 border ${
                        primary ? 'border-bambu-green bg-bambu-green/10' : 'border-bambu-dark-tertiary bg-bambu-dark-secondary'
                      } ${enough ? '' : 'opacity-60'}`}
                    >
                      <FilamentSwatch
                        rgba={spool.rgba}
                        extraColors={spool.extra_colors}
                        effectType={spool.effect_type}
                        subtype={spool.subtype}
                        effectSize="card"
                        className="w-7 h-7 flex-shrink-0 border-2 border-bambu-gray/70"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold text-white break-words">
                          {name} · {spool.label_weight ? gramsOf(spool) : '—'}
                        </div>
                        <div className={`text-xs break-words ${enough ? 'text-bambu-gray-light' : 'text-amber-400'}`}>
                          {[
                            enough ? state : t('queueTodo.assign.notEnough'),
                            spool.storage_location || null,
                            t('queueTodo.assign.spoolNumber', { id: spool.id }),
                          ].filter(Boolean).join(' · ')}
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => assignOf(spool)}
                        disabled={isAssigning}
                        aria-label={t('queueTodo.assign.assignSpool', { spool: `${name} #${spool.id}` })}
                        className={`${buttonBase} flex-shrink-0 ${
                          primary ? 'bg-bambu-green text-black hover:bg-bambu-green/90' : 'border border-bambu-dark-tertiary text-white hover:border-bambu-gray'
                        }`}
                      >
                        {isAssigning ? <Loader2 className="w-4 h-4 animate-spin" /> : t('queueTodo.assign.assign')}
                      </button>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p data-testid="todo-assign-none" className="text-sm text-bambu-gray break-words">
                {exactSpoolMissReason ?? t('queueTodo.assign.none')}
              </p>
            )}
            <div className="flex items-center gap-2">
              <input
                id="todo-assign-all"
                type="checkbox"
                checked={disableFiltering}
                onChange={() => setDisableFiltering((v) => !v)}
                className="accent-bambu-green w-4 h-4"
              />
              <label htmlFor="todo-assign-all" className="text-xs text-bambu-gray select-none cursor-pointer">
                {t('inventory.showAllSpools')}
              </label>
            </div>
          </>
        )}
        <div className="flex flex-wrap gap-2">
          {!scanning && (
            <button
              type="button"
              onClick={() => {
                setScanError(null);
                setScanning(true);
              }}
              className={`${buttonBase} flex items-center gap-2 border border-bambu-dark-tertiary text-white hover:border-bambu-gray font-medium`}
            >
              <QrCode className="w-4 h-4" />
              {t('queueTodo.assign.scanLabel')}
            </button>
          )}
          {!scanning && onNewSpool && (
            <button
              type="button"
              onClick={onNewSpool}
              disabled={newSpoolDisabled}
              title={newSpoolDisabled ? newSpoolDisabledTitle : undefined}
              className={`${buttonBase} border border-bambu-dark-tertiary text-white hover:border-bambu-gray font-medium disabled:opacity-50 disabled:cursor-not-allowed`}
            >
              {t('queueTodo.assign.newSpool')}
            </button>
          )}
          <button
            type="button"
            onClick={scanning ? stopScanning : onCancel}
            disabled={isAssigning}
            className={`${buttonBase} border border-bambu-dark-tertiary text-bambu-gray-light hover:text-white font-medium`}
          >
            {t('inventory.qrAssign.back')}
          </button>
        </div>
        {mismatch && trayInfo && (
          <MaterialMismatchConfirm
            mismatch={mismatch.details}
            location={trayInfo.location}
            isLoading={assignMutation.isPending}
            onConfirm={handleConfirmMismatch}
            onCancel={() => {
              if (!assignMutation.isPending) cancelMismatch();
            }}
          />
        )}
      </div>
    );
  }

  return (
    <>
        {/* Content */}
        <div className="p-4 space-y-4 overflow-y-auto">
          {/* Tray info: the slot being filled, what the printer reports in it,
              and the spool assigned to it now. */}
          {trayInfo && (
            <div className="p-3 bg-bambu-dark rounded-lg border border-bambu-dark-tertiary">
              <p className="text-xs text-bambu-gray mb-1">{t('inventory.selectSpool')}:</p>
              <div className="flex items-center gap-2">
                {trayInfo.color && (
                  <span
                    className="w-4 h-4 rounded-full border border-black/20"
                    style={getSwatchStyle(trayInfo.color)}
                  />
                )}
                <span className="text-white font-medium">{physicalLabel}</span>
                <span className="text-bambu-gray">({trayInfo.location})</span>
              </div>
              {currentSpool && (
                <p className="mt-1 text-xs text-bambu-gray truncate">
                  {t('inventory.assigned')}:{' '}
                  <span className="text-white">
                    #{currentSpool.id}
                    {currentSpool.spool ? ` ${spoolSummary(currentSpool.spool)}` : ''}
                  </span>
                </p>
              )}
            </div>
          )}

          {scanning ? (
            <QrSpoolScanner
              onDecode={handleScan}
              // A built-in scan is looked up in the spool list, so it waits
              // while the list loads or refreshes: a spool missing from an old
              // list would be turned down, and the scanner doesn't send a label
              // again while it stays in view.
              busy={isAssigning || mismatch !== null || spoolsFetching}
              error={scanError}
            />
          ) : (
          <>
          {/* Search filter, and scanning the spool's QR instead (#1574) */}
          <div className="flex flex-wrap gap-2">
            <div className="relative flex-1 min-w-[12rem]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-bambu-gray" />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder={t('inventory.searchSpools')}
                className="w-full pl-9 pr-3 py-2 bg-bambu-dark border border-bambu-dark-tertiary rounded-lg text-white text-sm placeholder:text-bambu-gray focus:outline-none focus:border-bambu-green"
              />
            </div>
            <Button
              variant="secondary"
              onClick={() => {
                setScanError(null);
                setScanning(true);
              }}
            >
              <QrCode className="w-4 h-4" />
              <span className="whitespace-nowrap">{t('inventory.qrAssign.scanTitle')}</span>
            </Button>
          </div>

          {/* Spool list */}
          <div className="space-y-3">
            {!spoolmanEnabled && (isLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="w-6 h-6 text-bambu-green animate-spin" />
              </div>
            ) : filteredSpools && filteredSpools.length > 0 ? (
              <div className="max-h-96 overflow-y-auto grid grid-cols-2 sm:grid-cols-3 gap-2">
                {filteredSpools.map((spool: InventorySpool) => (
                  <button
                    key={spool.id}
                    onClick={() => { setSelectedSpoolId(spool.id); setSelectedSpoolmanSpoolId(null); }}
                    title={spool.note || undefined}
                    className={`p-2.5 rounded-lg border text-left transition-colors ${
                      selectedSpoolId === spool.id
                        ? 'bg-bambu-green/20 border-bambu-green'
                        : 'bg-bambu-dark border-bambu-dark-tertiary hover:border-bambu-gray'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-white text-sm font-medium truncate">
                        {spool.brand ? `${spool.brand} ` : ''}{spool.material}{spool.subtype ? ` ${spool.subtype}` : ''}
                      </p>
                      <span className="text-[10px] font-mono text-bambu-gray shrink-0">#{spool.id}</span>
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      {spool.rgba && (
                        <span
                          className="w-3 h-3 rounded-full border border-black/20 flex-shrink-0"
                          style={getSwatchStyle(spool.rgba)}
                        />
                      )}
                      <span className="text-xs text-bambu-gray truncate">
                        {resolveSpoolColorName(spool.color_name, spool.rgba, spool.color_name_is_synthesized) || ''}
                      </span>
                    </div>
                    {spool.label_weight && (
                      <p className="text-xs text-bambu-gray mt-1">
                        {Math.max(0, Math.round(spool.label_weight - spool.weight_used))} / {spool.label_weight}g
                      </p>
                    )}
                    {spool.note && (
                      <p className="text-[10px] text-bambu-gray/70 mt-1 truncate" title={spool.note}>
                        {spool.note}
                      </p>
                    )}
                  </button>
                ))}
              </div>
            ) : exactSpoolMissReason ? (
              <div className="text-center py-8 text-bambu-gray">
                <p>{exactSpoolMissReason}</p>
              </div>
            ) : availableSpools && availableSpools.length === 0 ? (
              <div className="text-center py-8 text-bambu-gray">
                <p>{t('inventory.noAvailableSpools')}</p>
                {/* Diagnostic counter — when the picker is empty, having
                    the raw fetch / filter counts visible makes a
                    "spool I expected to see is missing" report
                    immediately answerable: if `total fetched` is 0 the
                    backend / cache returned nothing; if it's > 0 then
                    the archived / assigned-elsewhere filter ate the
                    spool and the toggle is the right escape hatch. */}
                {spools && (
                  <p className="text-[10px] mt-2 opacity-60">
                    {spools.length} fetched · {spools.filter(s => s.archived_at).length} archived ·{' '}
                    {spools.filter(s => assignedSpoolIds.has(s.id)).length} assigned to other slots
                  </p>
                )}
              </div>
            ) : (
              <div className="text-center py-8 text-bambu-gray">
                <p>{t('inventory.noSpoolsMatch')}</p>
                {availableSpools && (
                  <p className="text-[10px] mt-2 opacity-60">
                    {availableSpools.length} unassigned spools — {(availableSpools.length) - (filteredSpools?.length ?? 0)} filtered by tray match. Try "Show all spools".
                  </p>
                )}
              </div>
            ))}

            {spoolmanEnabled && (
              <>
                {spoolmanLoading ? (
                  <div className="flex justify-center py-4">
                    <Loader2 className="w-5 h-5 text-bambu-green animate-spin" />
                  </div>
                ) : spoolmanSpools && spoolmanSpools.filter(s => !s.archived_at && !assignedSpoolmanSpoolIds.has(s.id)).length > 0 ? (
                  <>
                    <p className="text-xs font-medium text-bambu-gray uppercase tracking-wide pt-1">
                      {t('inventory.spoolmanSpools')}
                    </p>
                    <div className="max-h-64 overflow-y-auto grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {filterSpoolsByQuery(spoolmanSpools.filter(s => !s.archived_at && !assignedSpoolmanSpoolIds.has(s.id)), searchFilter)
                        .map((spool: InventorySpool) => (
                          <button
                            key={`spoolman-${spool.id}`}
                            onClick={() => {
                              setSelectedSpoolmanSpoolId(spool.id);
                              setSelectedSpoolId(null);
                            }}
                            title={spool.note || undefined}
                            className={`p-2.5 rounded-lg border text-left transition-colors ${
                              selectedSpoolmanSpoolId === spool.id
                                ? 'bg-bambu-green/20 border-bambu-green'
                                : 'bg-bambu-dark border-bambu-dark-tertiary hover:border-bambu-gray'
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <p className="text-white text-sm font-medium truncate">
                                {spool.brand ? `${spool.brand} ` : ''}{spool.material}{spool.subtype ? ` ${spool.subtype}` : ''}
                              </p>
                              <span className="text-[10px] font-mono text-bambu-gray shrink-0">#{spool.id}</span>
                            </div>
                            <div className="flex items-center gap-1.5 mt-1">
                              {spool.rgba && (
                                <span
                                  className="w-3 h-3 rounded-full border border-black/20 flex-shrink-0"
                                  style={getSwatchStyle(spool.rgba)}
                                />
                              )}
                              <span className="text-xs text-bambu-gray truncate">
                                {resolveSpoolColorName(spool.color_name, spool.rgba, spool.color_name_is_synthesized) || ''}
                              </span>
                            </div>
                            {spool.label_weight && (
                              <p className="text-xs text-bambu-gray mt-1">
                                {Math.max(0, Math.round(spool.label_weight - spool.weight_used))} / {spool.label_weight}g
                              </p>
                            )}
                            {spool.note && (
                              <p className="text-[10px] text-bambu-gray/70 mt-1 truncate" title={spool.note}>
                                {spool.note}
                              </p>
                            )}
                          </button>
                        ))}
                    </div>
                  </>
                ) : null}
              </>
            )}
          </div>
          </>
          )}
        </div>

        {/* Footer: Back returns from the scan to the picker; the dialog itself
            closes once an assign succeeds. */}
        {scanning ? (
          <div className="flex justify-start p-4 border-t border-bambu-dark-tertiary">
            <Button variant="secondary" onClick={stopScanning} disabled={isAssigning}>
              <ArrowLeft className="w-4 h-4" />
              {t('inventory.qrAssign.back')}
            </Button>
          </div>
        ) : (
        /* Footer with filtering toggle */
        <div className="flex justify-between items-center p-4 border-t border-bambu-dark-tertiary">
          <div className="flex items-center gap-2">
            <input
              id="disable-filtering-toggle"
              type="checkbox"
              checked={disableFiltering}
              onChange={() => setDisableFiltering(v => !v)}
              className="accent-bambu-green w-4 h-4 rounded focus:ring-0 border-bambu-dark-tertiary"
            />
            <label htmlFor="disable-filtering-toggle" className="text-xs text-bambu-gray select-none cursor-pointer">
              {t('inventory.showAllSpools')}
            </label>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onCancel}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleAssign}
              disabled={(!selectedSpoolId && selectedSpoolmanSpoolId === null) || assignMutation.isPending || assignSpoolmanMutation.isPending}
            >
              {(assignMutation.isPending || assignSpoolmanMutation.isPending) ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {t('inventory.assigning')}
                </>
              ) : (
                <>
                  <Package className="w-4 h-4" />
                  {t('inventory.assignSpool')}
                </>
              )}
            </Button>
          </div>
        </div>
        )}


        {assignMutation.isError && (
          <div className="mx-4 mb-4 p-2 bg-red-100 dark:bg-red-500/20 border border-red-300 dark:border-red-500/50 rounded text-sm text-red-700 dark:text-red-400">
            {(assignMutation.error as Error).message}
          </div>
        )}

      {mismatch && trayInfo && (
        <MaterialMismatchConfirm
          mismatch={mismatch.details}
          location={trayInfo.location}
          isLoading={assignMutation.isPending}
          onConfirm={handleConfirmMismatch}
          onCancel={() => {
            if (!assignMutation.isPending) cancelMismatch();
          }}
        />
      )}
    </>
  );
}
