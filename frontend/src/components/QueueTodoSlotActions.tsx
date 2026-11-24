import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { QueueTodoPicture, QueueTodoPictureSlot } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { QUEUE_TODO_KEY } from '../hooks/useQueueTodo';
import { useUiSettings } from '../hooks/useUiSettings';
import { formatSlotLabel, resolveSlotNozzleDiameter } from '../utils/amsHelpers';
import { getCurrencySymbol } from '../utils/currency';
import { mapModelCode } from '../utils/printerModel';
import { AssignSpoolPicker } from './AssignSpoolPicker';
import { ConfigureAmsSlotModal } from './ConfigureAmsSlotModal';
import { SpoolFormModal } from './SpoolFormModal';

const slotLabelOf = (slot: QueueTodoPictureSlot) =>
  formatSlotLabel(slot.ams_id, slot.tray_id, slot.is_ht, slot.is_external, slot.ams_type);

interface SlotActionsProps {
  picture: QueueTodoPicture;
  // Stacking class for the dialogs opened from a panel (the To do launcher).
  overlayZIndex?: string;
}

// What to do about the slots a filament is going into, in the entry itself
// (#3726): assign a spool from the inventory, scan its label, add a new one,
// set the slot up when it has no RFID. A button is there only for who may use
// it, and the picture is drawn as before without any.
export function PictureActions({ picture, overlayZIndex }: SlotActionsProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { hasPermission } = useAuth();
  const canAssign = hasPermission('inventory:update');
  const canCreate = hasPermission('inventory:create');
  const canConfigure = hasPermission('printers:control');
  const [target, setTarget] = useState<QueueTodoPictureSlot | null>(null);
  const [creating, setCreating] = useState(false);
  const [configuring, setConfiguring] = useState<QueueTodoPictureSlot | null>(null);

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

  const slots = picture.units.flatMap((u) => u.slots.map((slot) => ({ slot, unit: u }))).filter(({ slot }) => slot.incoming);
  if (slots.length === 0 || (!canAssign && !canConfigure)) return null;
  const mayAssign = canAssign && !spoolmanDown;
  const nozzleOf = (unit: { nozzle: 'left' | 'right' | null }) => (unit.nozzle === 'left' ? 1 : unit.nozzle === 'right' ? 0 : undefined);
  const buttonClass =
    'min-h-[44px] sm:min-h-[36px] px-4 rounded-lg text-sm font-semibold break-words text-left';

  const picking = target !== null ? slots.find(({ slot }) => slot === target) : undefined;
  const incoming = picking?.slot.incoming;
  const model = printers?.find((p) => p.id === picture.printer_id)?.model ?? null;
  const configureUnit = configuring ? slots.find(({ slot }) => slot === configuring)?.unit : undefined;

  return (
    <div data-testid="todo-slot-actions" className="min-w-0 space-y-3">
      {picking && incoming ? (
        <AssignSpoolPicker
          layout="inline"
          printerId={picture.printer_id}
          amsId={picking.slot.ams_id}
          trayId={picking.slot.tray_id}
          slotLabel={slotLabelOf(picking.slot)}
          trayInfo={{
            type: incoming.type,
            material: incoming.type,
            color: incoming.color,
            location: `${picture.printer_name} ${slotLabelOf(picking.slot)}`,
          }}
          wanted={{ type: incoming.type, color: incoming.color, color_name: incoming.color_name, required_g: incoming.required_g }}
          spoolmanEnabled={spoolmanOn}
          onNewSpool={canCreate && !spoolmanOn ? () => setCreating(true) : undefined}
          onDone={() => {
            setTarget(null);
            queryClient.invalidateQueries({ queryKey: QUEUE_TODO_KEY });
          }}
          onCancel={() => setTarget(null)}
        />
      ) : (
        <div className="flex flex-wrap gap-2">
          {slots.map(({ slot }, i) => {
            const label = slotLabelOf(slot);
            return (
              <div key={`${slot.ams_id}-${slot.tray_id}`} className="contents">
                {mayAssign && (
                  <button
                    type="button"
                    onClick={() => setTarget(slot)}
                    className={`${buttonClass} ${i === 0 ? 'bg-bambu-green text-black hover:bg-bambu-green/90' : 'border border-bambu-dark-tertiary text-white hover:border-bambu-gray'}`}
                  >
                    {t('queueTodo.assign.assignFor', { slot: label })}
                  </button>
                )}
                {canConfigure && !slot.rfid && (
                  <button
                    type="button"
                    onClick={() => setConfiguring(slot)}
                    className={`${buttonClass} border border-bambu-dark-tertiary text-white hover:border-bambu-gray font-medium`}
                  >
                    {t('queueTodo.assign.configureFor', { slot: label })}
                  </button>
                )}
              </div>
            );
          })}
        </div>
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
      {configuring && printers && (
        <ConfigureAmsSlotModal
          isOpen
          onClose={() => setConfiguring(null)}
          printerId={picture.printer_id}
          slotInfo={{
            amsId: configuring.ams_id,
            trayId: configuring.tray_id,
            trayType: configuring.type || undefined,
            trayColor: configuring.color ? `${configuring.color.replace('#', '')}FF` : undefined,
            traySubBrands: configuring.tray_sub_brands || undefined,
            trayInfoIdx: configuring.tray_info_idx || undefined,
            extruderId: configureUnit ? nozzleOf(configureUnit) : undefined,
          }}
          printerModel={mapModelCode(model) || undefined}
          nozzleDiameter={resolveSlotNozzleDiameter(status, configuring.ams_id)}
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
  );
}
