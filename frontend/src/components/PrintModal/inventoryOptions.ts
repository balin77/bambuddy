import type { TFunction } from 'i18next';
import type { FilamentPolicy, InventoryFilament } from '../../api/client';
import { canonicalFilamentType, normalizeColorForCompare } from '../../utils/amsHelpers';
import { getColorName, resolveSpoolColorName } from '../../utils/colors';
import { filamentAllowed, filamentName } from '../../utils/filamentScope';
import { displayHex } from './displayHex';
import type { SlotPickerOption } from './SlotPicker';

/** A slot's override. `tray_info_idx` is set only for an inventory pick whose
 *  spool resolves to a specific Bambu variant (#3590). */
export interface FilamentOverrideEntry {
  type: string;
  color: string;
  tray_info_idx?: string;
  /** Picked from the inventory list; UI state only, never sent. An idx-less pick
   *  must not get a stored variant re-attached on save (#3590). */
  fromInventory?: boolean;
  /** The colour name saved with the override: the inventory entry's own name
   *  for an inventory pick, or what a stored override came with. Without one
   *  the dialog names the colour from its hex on save (#3590). */
  colorName?: string;
}

/** "350 g" below a kilogram, else "1.4 kg", in the UI language's number format (#3590). */
function formatStockWeight(grams: number, fmt: Intl.NumberFormat): string {
  return grams < 1000 ? `${fmt.format(Math.round(grams))} g` : `${fmt.format(grams / 1000)} kg`;
}

/** Value of an inventory row: `TYPE|COLOR|IDX`. The trailing separator is kept
 *  for an entry without a variant, so it never equals a loaded row's `TYPE|COLOR`. */
export const inventoryValue = (f: { type: string; color: string; tray_info_idx?: string }) =>
  `${f.type}|${f.color}|${f.tray_info_idx ?? ''}`;

/** The inventory entry's own colour name, when it has a readable one: what its
 *  picker row then shows, and what the override is saved with (#3590). A Bambu
 *  colour code or no name leaves the naming to the hex, as before. */
export const ownColorName = (f: InventoryFilament): string | null => resolveSpoolColorName(f.color_name, null);

/** Spools exist but none has a known weight: the grams are unknown, not zero. */
export const weightUnknown = (f: InventoryFilament) => f.spool_count >= 1 && f.remaining_grams <= 0;

/** The muted stock text after an inventory row: "· 2 spools · 1.4 kg" (#3590). */
export function inventoryStockMeta(f: InventoryFilament, t: TFunction, fmt: Intl.NumberFormat): string {
  if (f.spool_count <= 0) return ` · ${t('printModal.stockNone', 'none left in inventory')}`;
  if (weightUnknown(f)) {
    return ` · ${
      f.spool_count === 1
        ? t('printModal.stockHintCountOne', '1 spool')
        : t('printModal.stockHintCount', '{{count}} spools', { count: f.spool_count })
    }`;
  }
  const weight = formatStockWeight(f.remaining_grams, fmt);
  return ` · ${
    f.spool_count === 1
      ? t('printModal.stockHintOne', '1 spool · {{weight}}', { weight })
      : t('printModal.stockHint', '{{count}} spools · {{weight}}', { count: f.spool_count, weight })
  }`;
}

/** "PLA Matte (Lava Red)": the row's label. */
export function inventoryLabel(f: InventoryFilament): string {
  const subtype = f.subtype;
  const base = subtype && !subtype.toUpperCase().includes(f.type.toUpperCase()) ? `${subtype} ${f.type}` : subtype || f.type;
  const colour = resolveSpoolColorName(f.color_name, f.rgba ?? f.color) ?? getColorName(f.color);
  return `${base} (${colour})`;
}

/** The warning under a picked inventory entry: nothing left, or less than the job needs (#3590).
 *  `forced` is the slot's force-colour tick: only a forced colour makes the job wait for it. */
export function inventoryStockWarning(
  entry: InventoryFilament,
  required: number,
  forced: boolean,
  t: TFunction,
  fmt: Intl.NumberFormat,
): string | null {
  if (entry.spool_count <= 0) {
    let warning = t('printModal.stockNoneWarning', 'None of this filament is left in the inventory.');
    if (forced) warning += ` ${t('printModal.stockNoneWaits', 'The job will wait until it is loaded.')}`;
    return warning;
  }
  if (!weightUnknown(entry) && entry.remaining_grams < required) {
    return t('printModal.stockShortWarning', 'This job needs {{required}} g of this filament; the inventory has {{remaining}} g.', {
      required: fmt.format(Math.ceil(required)),
      remaining: fmt.format(Math.floor(entry.remaining_grams)),
    });
  }
  return null;
}

/** Inventory entries by canonical type, like the loaded list they sit next to (#3590). */
export function inventoryEntriesByType(filaments: readonly InventoryFilament[] | undefined): Record<string, InventoryFilament[]> {
  const map: Record<string, InventoryFilament[]> = {};
  for (const f of filaments ?? []) {
    const key = canonicalFilamentType(f.type);
    if (!map[key]) map[key] = [];
    map[key].push(f);
  }
  return map;
}

/** The entries of `type` that are not loaded already (type + colour; the variant is ignored for that) (#3590). */
export function notLoadedInventory(
  byType: Record<string, InventoryFilament[]>,
  type: string,
  loaded: ReadonlyArray<{ type: string; color: string }>,
): InventoryFilament[] {
  const key = (f: { type: string; color: string }) => `${canonicalFilamentType(f.type)}|${normalizeColorForCompare(f.color)}`;
  const loadedKeys = new Set(loaded.map(key));
  return (byType[canonicalFilamentType(type)] ?? []).filter((f) => !loadedKeys.has(key(f)));
}

/** The override a picker value stands for: `TYPE|COLOR[|IDX]`, the idx part optional (older values have none). */
export function overrideFromPickerValue(value: string, inventoryEntry?: InventoryFilament): FilamentOverrideEntry {
  const [type, color, idx] = value.split('|');
  const colorName = inventoryEntry ? ownColorName(inventoryEntry) : null;
  return {
    type,
    color,
    ...(idx ? { tray_info_idx: idx } : {}),
    ...(inventoryEntry ? { fromInventory: true } : {}),
    ...(colorName ? { colorName } : {}),
  };
}

/** The picker row of an inventory entry (#3590). `reqColor` marks the row that is exactly the colour the slice asked for. */
export function inventoryPickerOption(
  f: InventoryFilament,
  reqColor: string,
  group: string,
  policies: FilamentPolicy[] | null,
  t: TFunction,
  fmt: Intl.NumberFormat,
): SlotPickerOption {
  // The same rule for a spool on the shelf (#3522). Without a
  // variant only a rule on the type can decide here; the
  // scheduler checks the loaded tray again at dispatch.
  const blocked = !filamentAllowed(policies, f.type, f.tray_info_idx ?? '');
  return {
    value: inventoryValue(f),
    key: `inv-${inventoryValue(f)}`,
    label: inventoryLabel(f),
    meta: inventoryStockMeta(f, t, fmt),
    rgba: f.rgba ?? f.color.replace('#', ''),
    extraColors: f.extra_colors,
    effectType: f.effect_type,
    subtype: f.subtype,
    hex: displayHex(f.color),
    group,
    exactMatch: normalizeColorForCompare(reqColor) !== '' && normalizeColorForCompare(f.color) === normalizeColorForCompare(reqColor),
    disabled: blocked,
    disabledReason: blocked ? t('printModal.filamentBlockedSlot', { filament: filamentName(f.type, f.tray_info_idx ?? '') }) : undefined,
  };
}
