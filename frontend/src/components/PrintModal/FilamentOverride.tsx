import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Circle, RotateCcw, Palette, AlertTriangle } from 'lucide-react';
import type { InventoryFilament } from '../../api/client';
import { getColorName } from '../../utils/colors';
import { canonicalFilamentType, normalizeColorForCompare } from '../../utils/amsHelpers';
import { SlotPicker } from './SlotPicker';
import { displayHex } from './displayHex';
import { findStoredMatch } from './inventoryMatch';
import {
  inventoryEntriesByType,
  inventoryPickerOption,
  inventoryStockWarning,
  inventoryValue,
  notLoadedInventory,
  overrideFromPickerValue,
  type FilamentOverrideEntry,
} from './inventoryOptions';
import { useFilamentLabels } from './useFilamentLabels';
import { useFilamentPolicies } from '../../hooks/useFilamentPolicies';
import { filamentAllowed, filamentName } from '../../utils/filamentScope';
import type { FilamentReqsData } from './types';

export type { FilamentOverrideEntry };

interface FilamentOverrideProps {
  filamentReqs: FilamentReqsData | undefined;
  availableFilaments: Array<{ type: string; color: string; tray_info_idx: string; tray_sub_brands: string; extruder_id: number | null }>;
  overrides: Record<number, FilamentOverrideEntry>;
  onChange: (overrides: Record<number, FilamentOverrideEntry>) => void;
  /** Built-in inventory entries (#3590). Omitted/empty (e.g. Spoolman mode) = only "Loaded now". */
  inventoryFilaments?: InventoryFilament[];
  /** Number of copies, for the "not enough in stock" warning. Defaults to 1. */
  quantity?: number;
  /** Total grams the whole job needs per inventory entry (`inventoryValue` key),
   *  over all plates, copies and slots that picked it. Falls back to this
   *  panel's own slot x quantity when absent (#3590). */
  inventoryDemand?: Record<string, number>;
  /** The "Show inventory colours" setting is on. Off = the picker is exactly as before
   *  #3590: loaded rows only, no group headers (a stored inventory override still shows
   *  as "Saved with this job"). */
  inventoryEnabled?: boolean;
  /** The "Show inventory colours" checkbox. Omitted (Spoolman mode) = not shown. Drawn once,
   *  above the first panel (`showHint`) (#3590). */
  inventoryOption?: { checked: boolean; disabled: boolean; title?: string; onChange: (value: boolean) => void };

  /** Per-slot force color match flags. Defaults to false (opt-in) when not provided. */
  forceColorMatch?: Record<number, boolean>;
  /** Called when a slot's force color match checkbox is toggled. `auto` marks a
   *  tick set by an inventory pick rather than by the user (#3590). */
  onForceColorMatchChange?: (slotId: number, value: boolean, auto?: boolean) => void;
  /** Undo an automatic tick (reset, or a switch to a loaded row), unless the
   *  user changed the box themselves since (#3590). */
  onAutoForceColorRelease?: (slotId: number) => void;
  /** Names the plate these requirements belong to, when one panel is rendered per
   *  selected plate. Each plate prints its own subset of the file's slots (#2552). */
  plateLabel?: string;
  /** Whether to print the explanatory hint. A stack of per-plate panels only needs
   *  it once, above the first one. Defaults to true. */
  showHint?: boolean;
}

/**
 * Filament override UI for model-based queue assignment.
 * Allows users to override the 3MF's original filament choices with
 * filaments available across printers of the selected model.
 */
export function FilamentOverride({
  filamentReqs,
  availableFilaments,
  overrides,
  onChange,
  inventoryFilaments,
  quantity = 1,
  inventoryDemand,
  inventoryEnabled = false,
  inventoryOption,
  forceColorMatch,
  onForceColorMatchChange,
  onAutoForceColorRelease,
  plateLabel,
  showHint = true,
}: FilamentOverrideProps) {
  const { t, i18n } = useTranslation();
  const numberFormat = useMemo(
    () => new Intl.NumberFormat(i18n.language, { maximumFractionDigits: 1 }),
    [i18n.language],
  );

  // Per-slot sub-brand + material-disambiguated colour labels (#1718). The
  // shared hook fronts the three queries that power the resolution so this
  // component and ``FilamentMapping`` cannot drift apart on label content.
  const labels = useFilamentLabels(filamentReqs?.filaments);
  const filamentPolicies = useFilamentPolicies();

  // Index available filaments by canonical type for per-slot filtering.
  // Types in the same equivalence group (e.g. PA-CF / PA12-CF / PAHT-CF) share one bucket.
  const filamentsByType = useMemo(() => {
    const map: Record<string, Array<{ type: string; color: string; tray_info_idx: string; tray_sub_brands: string; extruder_id: number | null }>> = {};
    for (const f of availableFilaments) {
      const key = canonicalFilamentType(f.type);
      if (!map[key]) map[key] = [];
      map[key].push(f);
    }
    return map;
  }, [availableFilaments]);

  // Inventory entries by canonical type, like the loaded list above (#3590).
  const inventoryByType = useMemo(() => inventoryEntriesByType(inventoryFilaments), [inventoryFilaments]);

  const filaments = filamentReqs?.filaments;
  const hasInventory = (inventoryFilaments?.length ?? 0) > 0;
  if (!filaments || filaments.length === 0 || (availableFilaments.length === 0 && !hasInventory)) {
    return null;
  }

  const handleChange = (slotId: number, value: string, inventoryEntry?: InventoryFilament) => {
    if (value === '') {
      // Reset to original
      const next = { ...overrides };
      delete next[slotId];
      onChange(next);
      onAutoForceColorRelease?.(slotId);
    } else {
      onChange({ ...overrides, [slotId]: overrideFromPickerValue(value, inventoryEntry) });
      // Stock is about a colour, so an inventory pick forces it by default; the box can be unticked (#3590).
      // Only when the box is not ticked already: a manual tick must survive a later reset.
      if (inventoryEntry && inventoryEnabled) {
        if (!forceColorMatch?.[slotId]) onForceColorMatchChange?.(slotId, true, true);
      } else {
        onAutoForceColorRelease?.(slotId);
      }
    }
  };

  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 text-sm text-bambu-gray mb-2">
        <span>
          {plateLabel
            ? `${t('printModal.filamentOverride')} — ${plateLabel}`
            : t('printModal.filamentOverride')}
        </span>
      </div>
      {showHint && <p className="text-xs text-bambu-gray mb-2">{t('printModal.filamentOverrideHint')}</p>}
      {/* Asked for in #3590; the Settings card (Queue & Dispatch) is the other way to
          switch it, so this checkbox can be removed without losing the setting. */}
      {showHint && inventoryOption && (
        <label
          className={`inline-flex items-center gap-1.5 text-xs text-bambu-gray mb-2 select-none ${inventoryOption.disabled ? 'opacity-60 cursor-not-allowed' : 'cursor-pointer'}`}
          title={inventoryOption.title}
        >
          <input
            type="checkbox"
            checked={inventoryOption.checked}
            disabled={inventoryOption.disabled}
            onChange={(e) => inventoryOption.onChange(e.target.checked)}
            className="accent-bambu-green w-3 h-3"
          />
          {t('printModal.showInventoryColours', 'Show inventory colours')}
        </label>
      )}
      <div className="bg-bambu-dark rounded-lg p-3 space-y-2">
        {filaments.map((req, slotIdx) => {
          const override = overrides[req.slot_id];
          const isOverridden = !!override;
          // Only show filaments of the same type AND compatible nozzle/extruder
          const sameType = filamentsByType[canonicalFilamentType(req.type)] || [];
          // On dual-nozzle printers (H2D), filter to filaments on the correct extruder.
          // nozzle_id from 3MF maps to extruder_id from AMS. If nozzle_id is undefined
          // (single-nozzle) or extruder_id is null, no nozzle filtering is needed.
          const compatible = req.nozzle_id != null
            ? sameType.filter((f) => f.extruder_id == null || f.extruder_id === req.nozzle_id)
            : sameType;

          // #1718: sub-brand resolved from the 3MF's tray_info_idx via the
          // builtin / cloud-id maps, plus the material-disambiguated catalogue
          // colour for the hex. Both fall back gracefully (resolvedName →
          // req.type when the SKU is unknown; colorLabel → getColorName(hex)
          // when the by-material lookup hasn't resolved yet, returned null,
          // or errored) so a slow query never blanks out the row.
          const { resolvedName, colorLabel } = labels[slotIdx] ?? { resolvedName: req.type, colorLabel: getColorName(req.color) };

          // Inventory group (#3590): entries of this slot's type that are not
          // already loaded (type + colour; the variant is ignored for that).
          const inventoryRows = inventoryEnabled ? notLoadedInventory(inventoryByType, req.type, compatible) : [];
          const inventoryGroup = t('printModal.overrideGroupInventory', 'In inventory, not loaded');

          // Which row the stored override is. A loaded row wins (exact value, else
          // same canonical type and colour, so an 8-digit #RRGGBBAA or another
          // spelling still lands on it); otherwise an inventory entry; an entry
          // that no longer exists keeps its stored value as a synthetic row
          // instead of falling back to the placeholder.
          let pickerValue = '';
          let selectedInventory: InventoryFilament | undefined;
          let syntheticRow: { value: string; label: string; rgba: string } | undefined;
          if (isOverridden) {
            // A stored variant (idx) is matched exactly; without one the match stays loose (#3590).
            const loadedMatch = override.tray_info_idx
              ? findStoredMatch(compatible, override)
              : compatible.find((f) => `${f.type}|${f.color}` === `${override.type}|${override.color}`) ??
                findStoredMatch(compatible, override);
            if (loadedMatch) {
              pickerValue = `${loadedMatch.type}|${loadedMatch.color}`;
            } else {
              selectedInventory = findStoredMatch(inventoryRows, override);
              pickerValue = selectedInventory ? inventoryValue(selectedInventory) : inventoryValue(override);
              if (!selectedInventory) {
                syntheticRow = {
                  value: pickerValue,
                  label: `${override.type} (${override.colorName || getColorName(override.color)})`,
                  rgba: override.color.replace('#', ''),
                };
              }
            }
          }
          // Group headers only while inventory colours are offered; a stored colour that is
          // no longer in the list keeps its "Saved with this job" header either way.
          const grouped = inventoryEnabled && (inventoryRows.length > 0 || !!syntheticRow);
          const loadedGroup = grouped ? t('printModal.overrideGroupLoaded', 'Loaded now') : undefined;
          const savedGroup = t('printModal.overrideGroupSaved', 'Saved with this job');
          const required = selectedInventory
            ? inventoryDemand?.[inventoryValue(selectedInventory)] ?? req.used_grams * quantity
            : 0;
          const stockWarning = selectedInventory
            ? inventoryStockWarning(selectedInventory, required, !!forceColorMatch?.[req.slot_id], t, numberFormat)
            : null;

          return (
            <div key={req.slot_id} className="space-y-1">
              {/* Below `sm` the picker gets a line of its own, as on the
                  mapping row (#3294). */}
              <div className="grid items-center gap-2 text-xs grid-cols-[16px_minmax(0,1fr)_20px] sm:grid-cols-[16px_minmax(70px,1fr)_auto_2fr_20px]">
                {/* Original color swatch */}
                <span title={`${t('printModal.originalFilament')}: ${resolvedName} - ${colorLabel}`}>
                  <Circle className="w-3 h-3" fill={req.color} stroke={req.color} />
                </span>
                {/* Original type + grams */}
                <span className="text-white truncate col-span-2 sm:col-span-1">
                  {resolvedName} <span className="text-bambu-gray">({req.used_grams}g)</span>
                </span>
                {/* Arrow */}
                <span className="text-bambu-gray">→</span>
                {/* Override picker — only compatible (same-type) filaments.
                    Carries a swatch for the same reason the mapping row does
                    (#3159): this is the model-mode half of the same choice,
                    and leaving it text-only would make the two paths read
                    differently for one decision. Model mode pools filaments
                    across every printer of the model, so there is no slot
                    binding behind an entry and the swatch is the plain tray
                    colour -- solid, with no multi-colour stops to draw. */}
                <SlotPicker
                  value={pickerValue}
                  onChange={(next) =>
                    handleChange(
                      req.slot_id,
                      next,
                      inventoryRows.find((f) => inventoryValue(f) === next),
                    )
                  }
                  placeholder={`${t('printModal.originalFilament')}: ${resolvedName} (${colorLabel})`}
                  placeholderOption={{ rgba: req.color, hex: displayHex(req.color) }}
                  disabled={compatible.length === 0 && !grouped}
                  ariaLabel={t('printModal.overrideForFilament', { name: resolvedName })}
                  exactMatchLabel={t('printModal.exactColorMatch')}
                  className={
                    isOverridden
                      ? 'border-blue-500/50 dark:border-blue-400/50 text-blue-700 dark:text-blue-400'
                      : 'border-bambu-gray/30 text-bambu-gray'
                  }
                  options={[
                    ...compatible.map((f, idx) => {
                      // Listed but not selectable: the group may not use it (#3522).
                      const blocked = !filamentAllowed(filamentPolicies, f.type, f.tray_info_idx);
                      return {
                        // The value stays `TYPE|COLOR` for loaded rows -- `handleChange`
                        // parses it -- but two spools of the same type and colour
                        // on different printers collapse to one value, so the key
                        // keeps the sub-brand and the index as it did before.
                        value: `${f.type}|${f.color}`,
                        key: `${f.type}-${f.color}-${f.tray_sub_brands}-${idx}`,
                        label: `${f.tray_sub_brands || f.type} (${getColorName(f.color, f.tray_sub_brands, f.tray_info_idx)})`,
                        rgba: f.color,
                        hex: displayHex(f.color),
                        group: loadedGroup,
                        exactMatch:
                          normalizeColorForCompare(req.color) !== '' &&
                          normalizeColorForCompare(f.color) === normalizeColorForCompare(req.color),
                        disabled: blocked,
                        disabledReason: blocked
                          ? t('printModal.filamentBlockedSlot', { filament: filamentName(f.type, f.tray_info_idx) })
                          : undefined,
                      };
                    }),
                    ...inventoryRows.map((f) =>
                      inventoryPickerOption(f, req.color, inventoryGroup, filamentPolicies, t, numberFormat),
                    ),
                    ...(syntheticRow
                      ? [{ ...syntheticRow, key: `stored-${syntheticRow.value}`, hex: displayHex(override.color), group: savedGroup }]
                      : []),
                  ]}
                />
                {/* Reset button */}
                {isOverridden ? (
                  <button
                    type="button"
                    onClick={() => handleChange(req.slot_id, '')}
                    className="text-bambu-gray hover:text-white transition-colors"
                    title={t('printModal.resetToOriginal')}
                  >
                    <RotateCcw className="w-3 h-3" />
                  </button>
                ) : (
                  <span className="w-3" />
                )}
              </div>
              {/* Force Color Match checkbox — shown below each filament row */}
              <label className="inline-flex items-center gap-1.5 text-xs text-bambu-gray cursor-pointer select-none pl-5">
                <input
                  type="checkbox"
                  checked={forceColorMatch?.[req.slot_id] ?? false}
                  onChange={(e) => onForceColorMatchChange?.(req.slot_id, e.target.checked)}
                  className="accent-bambu-green w-3 h-3"
                />
                <Palette className="w-3 h-3" />
                {t('printModal.forceColorMatch')}
              </label>
              {stockWarning && (
                <p className="flex items-start gap-1.5 text-xs text-yellow-600 dark:text-yellow-400 pl-5" role="alert">
                  <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
                  {stockWarning}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
