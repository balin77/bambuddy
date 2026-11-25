import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { QueueTodoFilament, QueueTodoPicture, QueueTodoPictureSlot } from '../api/client';
import { QUEUE_TODO_KEY } from '../hooks/useQueueTodo';
import { usePermissionGate } from '../hooks/usePermissionGate';
import { useUiSettings } from '../hooks/useUiSettings';
import { formatSlotLabel, resolveSlotNozzleDiameter } from '../utils/amsHelpers';
import { getCurrencySymbol } from '../utils/currency';
import { mapModelCode } from '../utils/printerModel';
import { AssignSpoolPicker } from './AssignSpoolPicker';
import { ConfigureAmsSlotModal } from './ConfigureAmsSlotModal';
import type { SlotMenuActions } from './FilamentHoverCard';
import { AmsPicture } from './QueueTodoAmsPicture';
import { SpoolFormModal } from './SpoolFormModal';

const slotLabelOf = (slot: QueueTodoPictureSlot) =>
  formatSlotLabel(slot.ams_id, slot.tray_id, slot.is_ht, slot.is_external, slot.ams_type);

type SlotKey = { ams_id: number; tray_id: number };
const sameSlot = (a: SlotKey, b: SlotKey) => a.ams_id === b.ams_id && a.tray_id === b.tray_id;

interface PictureWithActionsProps {
  picture: QueueTodoPicture;
  // The entry's filaments: what an incoming card says about its filament.
  filaments: QueueTodoFilament[];
  // Stacking class for what is opened from a panel (the To do launcher).
  overlayZIndex?: string;
}

// The AMS picture of an entry and what to do about its slots, in the entry
// itself (#3726). A slot opens the menu the printer card's slots open: assign
// a spool from the inventory (with scanning its label and adding a new one),
// set the slot up when it has no RFID. An entry of the menu is there only for
// who may use it: one the caller may not use is greyed out, or left out when
// their groups hide what they cannot use (#3639); a slot with nothing in its
// menu is no button. The picture is drawn either way.
export function PictureWithActions({ picture, filaments, overlayZIndex }: PictureWithActionsProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const gate = usePermissionGate();
  const assignGate = gate('inventory:update');
  const createGate = gate('inventory:create');
  const configureGate = gate('printers:filament');
  const canAssign = assignGate.allowed;
  // Slots are kept by key: the list refetches and hands over new objects.
  const [target, setTarget] = useState<SlotKey | null>(null);
  const [creating, setCreating] = useState(false);
  const [configuring, setConfiguring] = useState<SlotKey | null>(null);

  // Same reading as the printer card: Spoolman on and reachable assigns from
  // Spoolman; on and down, nothing is assigned (the built-in table is the
  // other mode's); off, the built-in inventory.
  const { data: spoolman } = useQuery({
    queryKey: ['spoolman-status'],
    queryFn: api.getSpoolmanStatus,
    staleTime: 60 * 1000,
    enabled: canAssign,
  });
  const spoolmanOn = !!(spoolman?.enabled && spoolman?.connected);
  const spoolmanDown = !!(spoolman?.enabled && !spoolman?.connected);

  const { data: settings } = useUiSettings({ enabled: creating });
  const { data: printers } = useQuery({ queryKey: ['printers'], queryFn: api.getPrinters, enabled: configuring !== null });
  const { data: status } = useQuery({
    queryKey: ['printerStatus', picture.printer_id],
    queryFn: () => api.getPrinterStatus(picture.printer_id),
    enabled: configuring !== null,
  });

  const slots = picture.units.flatMap((u) => u.slots.map((slot) => ({ slot, unit: u })));
  // Until the Spoolman status is known nothing is assigned: which inventory it is is not known.
  const mayAssign = assignGate.render && (!canAssign || (spoolman !== undefined && !spoolmanDown));
  const nozzleOf = (unit: { nozzle: 'left' | 'right' | null }) => (unit.nozzle === 'left' ? 1 : unit.nozzle === 'right' ? 0 : undefined);

  // The menu of a slot, or null for a slot that is no button. The slot the
  // running print uses takes nothing. A slot nothing goes into follows the
  // printer card: no spool is assigned over one the printer read itself.
  const slotMenu = (slot: QueueTodoPictureSlot): SlotMenuActions | null => {
    if (slot.state === 'locked') return null;
    const key = { ams_id: slot.ams_id, tray_id: slot.tray_id };
    const menu: SlotMenuActions = {};
    if (mayAssign && (slot.incoming || !slot.rfid)) {
      menu.assign = {
        onSelect: () => setTarget(key),
        disabled: !canAssign,
        disabledReason: t('queueTodo.assign.noPermissionAssign'),
      };
    }
    if (configureGate.render && !slot.rfid) {
      menu.configure = {
        onSelect: () => setConfiguring(key),
        disabled: !configureGate.allowed,
        disabledReason: t('queueTodo.assign.noPermissionConfigure'),
      };
    }
    return menu.assign || menu.configure ? menu : null;
  };

  // Spoolman going down with the picker open ends the picking: the picker would otherwise fall back to the built-in inventory, the other mode's.
  const picking = target !== null && mayAssign ? slots.find(({ slot }) => sameSlot(slot, target)) : undefined;
  const incoming = picking?.slot.incoming;
  // What the picker lists first: the filament going into the slot, or, for a slot nothing goes into, the one it holds.
  const wanted = incoming
    ? { type: incoming.type, color: incoming.color, color_name: incoming.color_name, required_g: incoming.required_g }
    : picking?.slot.type
      ? { type: picking.slot.type, color: picking.slot.color, color_name: picking.slot.color_name, required_g: null }
      : undefined;
  const model = printers?.find((p) => p.id === picture.printer_id)?.model ?? null;
  const configuringEntry = configuring ? slots.find(({ slot }) => sameSlot(slot, configuring)) : undefined;
  const configureSlot = configuringEntry?.slot;
  const configureUnit = configuringEntry?.unit;

  // What a first-time user is told: the slots are the buttons. Only when one can be used.
  const menus = picking ? [] : slots.map(({ slot }) => slotMenu(slot));
  const hint = menus.some((m) => m?.assign && !m.assign.disabled)
    ? t('queueTodo.assign.slotHint')
    : menus.some((m) => m?.configure && !m.configure.disabled)
      ? t('queueTodo.assign.slotHintSetUp')
      : null;
  const configureOpen = !!(configureSlot && printers);

  return (
    <>
      <AmsPicture picture={picture} filaments={filaments} slotMenu={slotMenu} menuZIndex={overlayZIndex} />
      {(hint || picking || creating || configureOpen) && (
        <div data-testid="todo-slot-actions" data-todo-modal-open={creating || configuring ? 'true' : undefined} className="min-w-0 space-y-3">
          {hint && (
            <p data-testid="todo-slot-menu-hint" className="text-xs text-bambu-gray-light break-words">
              {hint}
            </p>
          )}
          {picking && incoming && (picking.slot.state === 'out' || (picking.slot.type && picking.slot.rfid)) && (
            <p data-testid="todo-put-in-first" role="note" className="text-sm text-amber-400 break-words">
              {t('queueTodo.assign.putInFirst')}
            </p>
          )}
          {picking && (
            <AssignSpoolPicker
              // Another slot's menu can ask while this one is open: a picker of its own.
              key={`${picking.slot.ams_id}-${picking.slot.tray_id}`}
              layout="inline"
              printerId={picture.printer_id}
              amsId={picking.slot.ams_id}
              trayId={picking.slot.tray_id}
              slotLabel={slotLabelOf(picking.slot)}
              trayInfo={{
                type: wanted?.type ?? '',
                material: wanted?.type,
                color: wanted?.color ?? '',
                location: `${picture.printer_name} ${slotLabelOf(picking.slot)}`,
              }}
              wanted={wanted}
              spoolmanEnabled={spoolmanOn}
              onNewSpool={createGate.render && !spoolmanOn ? () => setCreating(true) : undefined}
              newSpoolDisabled={!createGate.allowed}
              newSpoolDisabledTitle={t('queueTodo.assign.noPermissionCreate')}
              onDone={() => {
                setTarget(null);
                queryClient.invalidateQueries({ queryKey: QUEUE_TODO_KEY });
              }}
              onCancel={() => setTarget(null)}
            />
          )}
          {creating && (
            <SpoolFormModal
              isOpen
              mode="create"
              onClose={() => setCreating(false)}
              currencySymbol={getCurrencySymbol(settings?.currency || 'USD')}
              overlayZIndex={overlayZIndex ?? 'z-50'}
            />
          )}
          {configureSlot && printers && (
            <ConfigureAmsSlotModal
              isOpen
              onClose={() => setConfiguring(null)}
              printerId={picture.printer_id}
              slotInfo={{
                amsId: configureSlot.ams_id,
                trayId: configureSlot.tray_id,
                trayType: configureSlot.type || undefined,
                trayColor: configureSlot.color ? `${configureSlot.color.replace('#', '')}FF` : undefined,
                traySubBrands: configureSlot.tray_sub_brands || undefined,
                trayInfoIdx: configureSlot.tray_info_idx || undefined,
                extruderId: configureUnit ? nozzleOf(configureUnit) : undefined,
              }}
              printerModel={mapModelCode(model) || undefined}
              nozzleDiameter={resolveSlotNozzleDiameter(status, configureSlot.ams_id)}
              printerState={status?.state}
              overlayZIndex={overlayZIndex ?? 'z-50'}
              onSuccess={() => {
                queryClient.invalidateQueries({ queryKey: ['slotPresets', picture.printer_id] });
                queryClient.invalidateQueries({ queryKey: ['printerStatus', picture.printer_id] });
                queryClient.invalidateQueries({ queryKey: QUEUE_TODO_KEY });
              }}
            />
          )}
        </div>
      )}
    </>
  );
}
