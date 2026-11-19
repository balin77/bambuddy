import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Palette, Play, ShieldAlert, PowerOff, Loader2, Layers } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type {
  QueueTodo,
  QueueTodoEntry,
  QueueTodoGroup,
  QueueTodoHintSlot,
  QueueTodoKind,
  QueueTodoSlotHint,
} from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { PlateClearedIcon } from './icons/PlateClearedIcon';
import { ConfirmModal } from './ConfirmModal';
import { QUEUE_TODO_KEY } from '../hooks/useQueueTodo';
import { useStartQueueItem } from '../hooks/useStartQueueItem';
import { formatSlotLabel } from '../utils/amsHelpers';
import { getColorName } from '../utils/colors';

const KIND_ICON: Record<QueueTodoKind, React.ComponentType<{ className?: string }>> = {
  plate_clear: PlateClearedIcon,
  plate_changer_empty: Layers,
  load_filament: Palette,
  start_staged: Play,
  sensor_interlock: ShieldAlert,
  power_on_failed: PowerOff,
};

const KIND_TEXT_KEY: Record<QueueTodoKind, string> = {
  plate_clear: 'queueTodo.kind.plateClear',
  plate_changer_empty: 'queueTodo.kind.plateChangerEmpty',
  load_filament: 'queueTodo.kind.loadFilament',
  start_staged: 'queueTodo.kind.startStaged',
  sensor_interlock: 'queueTodo.kind.sensorInterlock',
  power_on_failed: 'queueTodo.kind.powerOnFailed',
};

// How many printers of an "Any <model>" entry show their hint before "+N more".
const HINT_PRINTERS_SHOWN = 3;

type TFn = (key: string, options?: Record<string, unknown>) => string;

// A slot as the Printers page names it: its label, and for a loaded one the
// filament, with the colour named the way the printer card names it.
function slotText(slot: QueueTodoHintSlot): string {
  const label = formatSlotLabel(slot.ams_id, slot.tray_id, slot.is_ht, slot.is_external, slot.ams_type);
  if (!slot.type) return label;
  const color = slot.color ? getColorName(slot.color, slot.tray_sub_brands || null, slot.tray_info_idx) : '';
  return `${label} (${[slot.type, color].filter(Boolean).join(' ')})`;
}

function stateText(t: TFn, state: QueueTodoSlotHint['state'], slots: QueueTodoHintSlot[]): string {
  if (state === 'all_needed') return t('queueTodo.slotHint.allNeeded');
  return t(state === 'free' ? 'queueTodo.slotHint.free' : 'queueTodo.slotHint.replaceable', {
    slots: slots.map(slotText).join(', '),
  });
}

interface HintText {
  // Set when the printer's filaments go on nozzles: the printer name then
  // stands on a line of its own and the parts hang under it.
  nozzles: boolean;
  lines: string[];
}

// The lines one printer's hint is shown as: one per nozzle on a dual-nozzle
// printer (even when only one of its nozzles is meant), else one; then the
// jobs whose filaments are unknown.
function hintText(t: TFn, hint: QueueTodoSlotHint): HintText {
  const nozzleName = (n: 'left' | 'right') => t(n === 'left' ? 'printModal.leftNozzleTooltip' : 'printModal.rightNozzleTooltip');
  const nozzles = hint.by_nozzle.length > 0;
  const lines = nozzles
    ? hint.by_nozzle.map((part) => t('queueTodo.slotHint.labelled', { label: nozzleName(part.nozzle), text: stateText(t, part.state, part.slots) }))
    : [stateText(t, hint.state, hint.slots)];
  if (hint.unknown_jobs > 0) lines.push(t('queueTodo.slotHint.unknownJobs', { count: hint.unknown_jobs }));
  return { nozzles, lines };
}

function SlotHints({ entry }: { entry: QueueTodoEntry }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  if (entry.slot_hint) {
    return (
      <div data-testid="todo-slot-hint" className="space-y-0.5 text-xs text-bambu-gray-light">
        {hintText(t, entry.slot_hint).lines.map((line, i) => <div key={i} className="break-words">{line}</div>)}
      </div>
    );
  }
  const hints = entry.slot_hints ?? [];
  if (hints.length === 0) return null;
  const shown = expanded ? hints : hints.slice(0, HINT_PRINTERS_SHOWN);
  const hidden = hints.length - shown.length;
  const nameOf = (id: number) => entry.printers.find((p) => p.id === id)?.name ?? '';
  return (
    <div data-testid="todo-slot-hints" className="space-y-0.5 text-xs text-bambu-gray-light">
      {shown.map((hint) => {
        const { nozzles, lines } = hintText(t, hint);
        // One line: "X1C-2: Free: A2". With nozzles: the name alone, then the
        // lines. Whatever follows the name's line is indented under it.
        const head = nozzles ? nameOf(hint.printer_id) : t('queueTodo.slotHint.labelled', { label: nameOf(hint.printer_id), text: lines[0] });
        const rest = nozzles ? lines : lines.slice(1);
        return (
          <div key={hint.printer_id} className="break-words" data-testid="todo-slot-hint-printer">
            <div>{head}</div>
            {rest.map((line, i) => <div key={i} className="pl-3">{line}</div>)}
          </div>
        );
      })}
      {hints.length > HINT_PRINTERS_SHOWN && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded((v) => !v)}
          className="text-bambu-green hover:underline"
        >
          {expanded ? t('queueTodo.slotHint.less') : t('queueTodo.slotHint.more', { count: hidden })}
        </button>
      )}
    </div>
  );
}

function EntryRow({ group, entry, onNavigate, onStart, startPending, overlayZIndex }: {
  group: QueueTodoGroup;
  entry: QueueTodoEntry;
  onNavigate?: () => void;
  onStart: (id: number) => void;
  startPending: boolean;
  overlayZIndex?: string;
}) {
  const { t } = useTranslation();
  const { hasPermission, hasAnyPermission } = useAuth();
  const { pathname } = useLocation();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const Icon = KIND_ICON[entry.kind];

  // Same call and permission as the Plate-is-clear button on the printer card.
  const clearPlate = useMutation({
    mutationFn: () => api.clearPlate(group.printer_id as number),
    onSuccess: () => {
      showToast(t('queue.clearPlateSuccess'));
      queryClient.invalidateQueries({ queryKey: ['printerStatus', group.printer_id] });
      queryClient.invalidateQueries({ queryKey: QUEUE_TODO_KEY });
    },
    onError: (error: unknown) =>
      showToast(error instanceof ApiError && error.message ? error.message : t('queueTodo.actionFailed'), 'error'),
  });

  // Same call, permission and confirmation as the refill control on the printer card (#3575).
  const [showRefillConfirm, setShowRefillConfirm] = useState(false);
  const refillPlates = useMutation({
    mutationFn: () => api.refillPlates(group.printer_id as number),
    onSuccess: (updated) => {
      showToast(t('printers.plateChanger.refilledToast', { capacity: updated.plate_capacity }));
      queryClient.invalidateQueries({ queryKey: ['printers'] });
      queryClient.invalidateQueries({ queryKey: QUEUE_TODO_KEY });
    },
    onError: (error: Error) => showToast(error.message || t('printers.plateChanger.refillFailed'), 'error'),
  });

  const canClearPlate = hasPermission('printers:clear_plate');
  // Per-job `can_start` comes from the backend (ownership and review rule);
  // the permissions only pick the reason shown on a disabled button.
  const awaitingReview = !hasAnyPermission('queue:update_all', 'queue:start_unreviewed');
  const startBlockedReason = awaitingReview
    ? t('queue.permissions.awaitingReview')
    : t('queue.permissions.noStartPrint');

  const jobs = entry.jobs;
  const modelPrinters = entry.kind === 'load_filament' && group.printer_id == null ? entry.printers : [];
  const jobLabel = jobs.length > 2
    ? t('queueTodo.jobCount', { count: jobs.length })
    : jobs.map((j) => j.name).join(', ');

  let action: React.ReactNode = null;
  if (entry.kind === 'plate_clear' && group.printer_id != null) {
    action = canClearPlate ? (
      <button
        type="button"
        onClick={() => clearPlate.mutate()}
        disabled={clearPlate.isPending}
        className="flex items-center gap-1.5 px-3 py-1.5 min-h-[36px] text-sm rounded-md bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30 disabled:opacity-50"
      >
        {clearPlate.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlateClearedIcon className="w-4 h-4" />}
        {t('queueTodo.plateIsClear')}
      </button>
    ) : (
      <button
        type="button"
        disabled
        title={t('printers.permission.noControl')}
        className="flex items-center gap-1.5 px-3 py-1.5 min-h-[36px] text-sm rounded-md bg-bambu-dark-tertiary text-bambu-gray opacity-50 cursor-not-allowed"
      >
        <PlateClearedIcon className="w-4 h-4" />
        {t('queueTodo.plateIsClear')}
      </button>
    );
  } else if (entry.kind === 'plate_changer_empty' && group.printer_id != null) {
    action = canClearPlate ? (
      <button
        type="button"
        onClick={() => setShowRefillConfirm(true)}
        disabled={refillPlates.isPending}
        title={t('printers.plateChanger.refillTitle', { capacity: entry.plate_capacity })}
        className="flex items-center gap-1.5 px-3 py-1.5 min-h-[36px] text-sm rounded-md bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30 disabled:opacity-50"
      >
        {refillPlates.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Layers className="w-4 h-4" />}
        {t('printers.plateChanger.refill')}
      </button>
    ) : (
      <button
        type="button"
        disabled
        title={t('printers.permission.noControl')}
        className="flex items-center gap-1.5 px-3 py-1.5 min-h-[36px] text-sm rounded-md bg-bambu-dark-tertiary text-bambu-gray opacity-50 cursor-not-allowed"
      >
        <Layers className="w-4 h-4" />
        {t('printers.plateChanger.refill')}
      </button>
    );
  } else if (entry.kind === 'start_staged') {
    action = (
      <div className="flex flex-wrap gap-2 min-w-0">
        {jobs.map((job) => {
          const label = jobs.length > 1 ? `${t('queue.actions.startPrint')}: ${job.name}` : t('queue.actions.startPrint');
          return (
            <button
              key={job.id}
              type="button"
              onClick={() => onStart(job.id)}
              disabled={!job.can_start || startPending}
              title={!job.can_start ? startBlockedReason : label}
              aria-label={label}
              className="flex items-center gap-1.5 min-w-0 max-w-full px-3 py-1.5 min-h-[36px] text-sm rounded-md bg-bambu-green/20 text-bambu-green hover:bg-bambu-green/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Play className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{label}</span>
            </button>
          );
        })}
      </div>
    );
  } else if (group.printer_id != null) {
    action = (
      <Link
        to={`/printers#printer-card-${group.printer_id}`}
        onClick={onNavigate}
        className="text-sm text-bambu-green hover:underline"
      >
        {t('queueTodo.openPrinter')}
      </Link>
    );
  } else if (pathname !== '/queue') {
    action = (
      <Link to="/queue" onClick={onNavigate} className="text-sm text-bambu-green hover:underline">
        {t('queueTodo.openQueue')}
      </Link>
    );
  }

  return (
    <li data-testid={`todo-entry-${entry.kind}`} className="flex items-start gap-3 py-2">
      <Icon className="w-5 h-5 mt-0.5 flex-shrink-0 text-yellow-500" />
      <div className="flex-1 min-w-0 space-y-1">
        <div className="text-sm text-white break-words">
          {modelPrinters.length > 0 ? (
            <>
              {t('queueTodo.kind.loadFilamentOn')}{' '}
              {modelPrinters.map((p, i) => (
                <span key={p.id}>
                  {i > 0 && ` ${t('queueTodo.or')} `}
                  <Link to={`/printers#printer-card-${p.id}`} onClick={onNavigate} className="text-bambu-green hover:underline">
                    {p.name}
                  </Link>
                </span>
              ))}
            </>
          ) : (
            t(KIND_TEXT_KEY[entry.kind])
          )}
        </div>
        {entry.kind === 'sensor_interlock' && entry.detail && (
          <div className="text-xs text-bambu-gray-light">{entry.detail}</div>
        )}
        {entry.kind === 'load_filament' && entry.priority && (
          <div data-testid="todo-priority" className="text-xs text-bambu-gray-light">
            {entry.priority === 'has_priority'
              ? t('queue.waiting.hasPriority')
              : t('queue.waiting.priorityIn', { hours: entry.priority_hours ?? 0 })}
          </div>
        )}
        {entry.kind === 'load_filament' && (
          <ul className="flex flex-wrap gap-x-3 gap-y-1">
            {entry.filaments.map((f, i) => (
              <li key={i} className="flex items-center gap-1.5 text-xs text-bambu-gray-light">
                {f.color && (
                  <span
                    data-testid="todo-swatch"
                    role="img"
                    title={f.color_name || f.color}
                    aria-label={f.color_name || f.color}
                    className="inline-block flex-shrink-0 w-3.5 h-3.5 rounded-full border border-white/30"
                    style={{ backgroundColor: f.color }}
                  />
                )}
                <span>{[f.type, f.color_name].filter(Boolean).join(' ')}</span>
                {(f.nozzle === 0 || f.nozzle === 1) && (
                  <span data-testid="todo-nozzle">
                    ({t(f.nozzle === 1 ? 'printModal.leftNozzleTooltip' : 'printModal.rightNozzleTooltip')})
                  </span>
                )}
                {f.no_stock && (
                  <span className="text-red-400">({t('queueTodo.noStock')})</span>
                )}
              </li>
            ))}
          </ul>
        )}
        {entry.kind === 'load_filament' && <SlotHints entry={entry} />}
        <div className="text-xs text-bambu-gray truncate max-w-full" title={jobs.map((j) => j.name).join(', ')}>
          {jobLabel}
        </div>
        {action}
      </div>
      {showRefillConfirm && entry.plate_capacity != null && (
        <ConfirmModal
          title={t('printers.plateChanger.refillConfirmTitle')}
          message={t('printers.plateChanger.refillConfirmMessage', { capacity: entry.plate_capacity })}
          confirmText={t('printers.plateChanger.refill')}
          variant="warning"
          overlayZIndex={overlayZIndex}
          onConfirm={() => {
            refillPlates.mutate();
            setShowRefillConfirm(false);
          }}
          onCancel={() => setShowRefillConfirm(false)}
        />
      )}
    </li>
  );
}

interface QueueTodoListProps {
  todo: QueueTodo | undefined;
  // Closes a surrounding panel when a link is followed.
  onNavigate?: () => void;
  // Small "To do" heading above the list (queue page).
  heading?: boolean;
  // Lifts the filament confirmations above a surrounding panel.
  overlayZIndex?: string;
}

// Everything the queue waits on, grouped by printer. Renders nothing when empty (#3615).
export function QueueTodoList({ todo, onNavigate, heading = false, overlayZIndex }: QueueTodoListProps) {
  const { t } = useTranslation();
  const { startMutation, modals } = useStartQueueItem(overlayZIndex);
  if (!todo || todo.count === 0 || todo.groups.length === 0) return null;
  return (
    <div className={`space-y-3 min-w-0 ${heading ? 'mb-4' : ''}`} data-testid="queue-todo-list">
      {modals}
      {heading && <h2 className="text-sm font-semibold text-bambu-gray-light">{t('queueTodo.title')}</h2>}
      {todo.groups.map((group) => (
        <section
          key={group.printer_id ?? `model-${group.target_model}`}
          className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-3"
        >
          <h3 className="text-sm font-semibold text-white mb-1 truncate">
            {group.printer_id == null
              ? t('queueTodo.anyModel', { model: group.target_model ?? group.printer_name })
              : group.printer_name}
          </h3>
          <ul className="divide-y divide-bambu-dark-tertiary">
            {group.entries.map((entry, i) => (
              <EntryRow
                key={`${entry.kind}-${i}`}
                group={group}
                entry={entry}
                onNavigate={onNavigate}
                onStart={(id) => startMutation.mutate({ id })}
                startPending={startMutation.isPending}
                overlayZIndex={overlayZIndex}
              />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
