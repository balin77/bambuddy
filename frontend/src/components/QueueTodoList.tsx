import { useId, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import i18n from 'i18next';
import { Palette, Pause, Play, ShieldAlert, PowerOff, Loader2, Layers } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type {
  QueueTodo,
  QueueTodoEntry,
  QueueTodoFilament,
  QueueTodoGroup,
  QueueTodoHintSlot,
  QueueTodoKind,
  QueueTodoPaused,
  QueueTodoPausedSlot,
  QueueTodoPrepare,
  QueueTodoSlotHint,
} from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { PlateClearedIcon } from './icons/PlateClearedIcon';
import { ConfirmModal } from './ConfirmModal';
import { QUEUE_TODO_KEY } from '../hooks/useQueueTodo';
import { useStartQueueItem } from '../hooks/useStartQueueItem';
import { AmsPicture, AmsPictures } from './QueueTodoAmsPicture';
import { PictureWithActions } from './QueueTodoSlotActions';
import { AddSpoolActions, JobActions, PowerOnAgain } from './QueueTodoEntryActions';
import { PausedActions } from './QueueTodoPausedActions';
import { formatAssignmentSlotLabel, formatSlotLabel, onePerPrinter } from '../utils/amsHelpers';
import { getColorName } from '../utils/colors';
import { formatDuration } from '../utils/date';

const KIND_ICON: Record<QueueTodoKind, React.ComponentType<{ className?: string }>> = {
  print_paused: Pause,
  plate_clear: PlateClearedIcon,
  plate_changer_empty: Layers,
  load_filament: Palette,
  start_staged: Play,
  sensor_interlock: ShieldAlert,
  power_on_failed: PowerOff,
};

const KIND_TEXT_KEY: Record<QueueTodoKind, string> = {
  print_paused: 'queueTodo.kind.printPaused',
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
function slotText(t: TFn, slot: QueueTodoHintSlot): string {
  const label = formatSlotLabel(slot.ams_id, slot.tray_id, slot.is_ht, slot.is_external, slot.ams_type);
  if (!slot.type) return label;
  const color = slot.color ? getColorName(slot.color, slot.tray_sub_brands || null, slot.tray_info_idx) : '';
  const filament = [slot.type, color].filter(Boolean).join(' ');
  // A spool to replace says what it has left.
  if (typeof slot.remaining_grams === 'number') {
    return t('queueTodo.slotHint.withGrams', { label, filament, remaining: formatGrams(slot.remaining_grams) });
  }
  return `${label} (${filament})`;
}

// The number in the interface language. The unit is part of the translated
// strings, behind a non-breaking space, so "30 g" never wraps between the two.
function formatGrams(grams: number): string {
  return Math.round(grams).toLocaleString(i18n.language);
}

// The label of a tray of a short filament. The tray's own slot in the entry's
// hint knows if it is an AMS-HT or an AMS 3H; without it the ids and the
// printer's model say, as the printer card names the slot, the external
// inputs of a rack printer included.
function trayLabel(tray: { ams_id: number; tray_id: number }, slots: QueueTodoHintSlot[], printerModel?: string | null): string {
  const slot = slots.find((s) => s.ams_id === tray.ams_id && s.tray_id === tray.tray_id);
  if (slot && !slot.is_external) return formatSlotLabel(slot.ams_id, slot.tray_id, slot.is_ht, slot.is_external, slot.ams_type);
  return formatAssignmentSlotLabel({ ams_id: tray.ams_id, tray_id: tray.tray_id, printer_model: printerModel });
}

// "Not enough PLA Lava Red: A2 has 12 g, the job needs 30 g". A pooled amount
// (AMS Filament Backup counts every spool of the filament together) is the sum;
// an amount that is not known for every tray is left out, and so is a job
// amount that is not known.
function shortText(t: TFn, f: QueueTodoFilament, slots: QueueTodoHintSlot[], printerModel?: string | null): string {
  const filament = [f.type, f.color_name].filter(Boolean).join(' ');
  const trays = f.short_trays ?? [];
  if (trays.length === 0) return t('queueTodo.short.plain', { filament });
  const where = trays.map((tray) => trayLabel(tray, slots, printerModel)).join(' + ');
  const amounts = trays.map((tray) => tray.remaining_grams);
  if (amounts.some((g) => typeof g !== 'number')) return t('queueTodo.short.in', { filament, slots: where });
  const remaining = formatGrams((amounts as number[]).reduce((a, b) => a + b, 0));
  const pooled = trays.length > 1;
  const needs = typeof f.required_grams === 'number';
  const key = `queueTodo.short.${pooled ? 'have' : 'has'}Grams${needs ? 'Needs' : ''}`;
  return t(key, { filament, slots: where, remaining, required: needs ? formatGrams(f.required_grams as number) : '' });
}

function stateText(t: TFn, state: QueueTodoSlotHint['state'], slots: QueueTodoHintSlot[]): string {
  if (state === 'all_needed') return t('queueTodo.slotHint.allNeeded');
  const key = { free: 'free', replaceable: 'replaceable', replace: 'replace' }[state];
  return t(`queueTodo.slotHint.${key}`, { slots: slots.map((s) => slotText(t, s)).join(', ') });
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

// The name of a filament: its type and colour name, the colour code when it
// has no name. Empty when the filament says nothing.
function filamentName(f: QueueTodoFilament): string {
  return [f.type, f.color_name || f.color].filter(Boolean).join(' ');
}

// "PETG Black (left nozzle) (no stock)", as the filament list of an entry names it.
function filamentText(t: TFn, f: QueueTodoFilament): string {
  let text = filamentName(f);
  if (f.nozzle === 0 || f.nozzle === 1) {
    text += ` (${t(f.nozzle === 1 ? 'printModal.leftNozzleTooltip' : 'printModal.rightNozzleTooltip')})`;
  }
  return f.no_stock ? `${text} (${t('queueTodo.noStock')})` : text;
}

// The lines of a group that have something to say: one that lists no filament
// is left out, so "needs" never stands alone.
function prepareLines(group: QueueTodoGroup): QueueTodoPrepare[] {
  return (group.prepare ?? []).filter((line) => line.filaments.some((f) => filamentName(f) !== ''));
}

// What to prepare for a printer's next jobs: quiet rows under its entries (#3640).
// ``first`` when the group has no entries above them: no rule and no gap then.
function PrepareRows({ lines, first }: { lines: QueueTodoPrepare[]; first: boolean }) {
  const { t } = useTranslation();
  const titleId = useId();
  return (
    <div data-testid="todo-prepare" className={first ? 'space-y-1' : 'mt-1 border-t border-bambu-dark-tertiary pt-2 space-y-1'}>
      <h4 id={titleId} className="text-[11px] font-medium uppercase tracking-wide text-bambu-gray">{t('queueTodo.prepare.title')}</h4>
      <ul aria-labelledby={titleId} className="space-y-1.5">
        {lines.map((line, i) => (
          <li key={line.job.id} data-testid="todo-prepare-row" className="min-w-0 text-xs text-bambu-gray">
            <div className="break-words">
              {t(i === 0 ? 'queueTodo.prepare.next' : 'queueTodo.prepare.then', {
                job: line.job.name,
                filaments: line.filaments.filter((f) => filamentName(f) !== '').map((f) => filamentText(t, f)).join(', '),
              })}
            </div>
            {line.ams_picture && (
              <div className="mt-1.5">
                <AmsPicture picture={line.ams_picture} filaments={line.filaments} />
              </div>
            )}
            {!line.ams_picture && line.slot_hint && (
              <div data-testid="todo-prepare-hint" className="space-y-0.5 text-bambu-gray">
                {hintText(t, line.slot_hint).lines.map((text, i) => <div key={i} className="break-words">{text}</div>)}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
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

const slotLabel = (slot: QueueTodoPausedSlot) =>
  formatSlotLabel(slot.ams_id, slot.tray_id, slot.is_ht, slot.is_external, slot.ams_type);

// "PLA Lava Red" for what a slot's tray reports; null for an empty slot.
const slotFilament = (slot: QueueTodoPausedSlot | null) =>
  slot?.type
    ? [slot.type, slot.color ? getColorName(slot.color, slot.tray_sub_brands || null, slot.tray_info_idx) : ''].filter(Boolean).join(' ')
    : null;

// The file, how far it got and how long it still has; parts the printer did not report are left out.
function pausedProgressLine(paused: QueueTodoPaused, t: (key: string, options?: Record<string, unknown>) => string): string {
  return [
    paused.job_name,
    paused.progress != null ? `${Math.round(paused.progress)}%` : null,
    paused.remaining_minutes != null ? t('queueTodo.printPaused.remaining', { time: formatDuration(paused.remaining_minutes * 60) }) : null,
  ].filter(Boolean).join(' \u00b7 ');
}

// What the paused print waits for, in a sentence; null when the printer gave no reason.
function pausedCauseText(paused: QueueTodoPaused, t: (key: string, options?: Record<string, unknown>) => string): string | null {
  switch (paused.cause) {
    case 'runout_ams': {
      const { ran_out: ranOut, expected } = paused;
      // What to load is what ran out. A slot that reports no type says nothing about it, and the
      // expected slot's own filament is not what ran out, so that case reads as "matching filament".
      const filament = slotFilament(ranOut) ?? t('queueTodo.printPaused.anyFilament');
      if (ranOut && expected) {
        return t('queueTodo.printPaused.runoutBoth', { ranOut: slotLabel(ranOut), filament, expected: slotLabel(expected) });
      }
      if (expected) return t('queueTodo.printPaused.runoutExpected', { filament, expected: slotLabel(expected) });
      if (ranOut) return t('queueTodo.printPaused.runoutRanOut', { ranOut: slotLabel(ranOut) });
      return t('queueTodo.printPaused.runoutUnknown');
    }
    case 'runout_external':
      return t('queueTodo.printPaused.runoutExternal');
    case 'error': {
      const base = paused.error?.description || t('queueTodo.printPaused.errorCode', { code: paused.error?.code ?? '' });
      return paused.more_errors > 0 ? `${base} ${t('queueTodo.printPaused.moreErrors', { count: paused.more_errors })}` : base;
    }
    default:
      return null;
  }
}

// What a load entry with a picture is called: a short spool is replaced,
// several filaments are counted, one is loaded.
function loadTitle(t: TFn, filaments: QueueTodoFilament[]): string {
  if (filaments.length > 0 && filaments.every((f) => f.short)) return t('queueTodo.picture.titleReplace');
  if (filaments.length > 1) return t('queueTodo.picture.titleSeveral', { count: filaments.length });
  return t(KIND_TEXT_KEY.load_filament);
}

function EntryRow({ group, entry, onNavigate, onOpenQueue, onStart, startPending, overlayZIndex }: {
  group: QueueTodoGroup;
  entry: QueueTodoEntry;
  onNavigate?: () => void;
  onOpenQueue?: () => void;
  // `printerId`: the printer an "Any <model>" job is started on.
  onStart: (id: number, printerId?: number) => void;
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
  // The AMS picture stands in for the slot sentence (#3726).
  const picture = entry.kind === 'load_filament' ? entry.ams_picture ?? null : null;
  const pictures = entry.kind === 'load_filament' ? onePerPrinter(entry.ams_pictures ?? []) : [];
  const hasPicture = picture !== null || pictures.length > 0;
  // The printer of an "Any <model>" entry whose picture is shown: the first
  // one until another is picked. Its picture brings the filaments it misses,
  // which can differ from the entry's (#3726).
  const [pickedPrinter, setPickedPrinter] = useState<number | null>(null);
  const shownPicture = pictures.find((p) => p.printer_id === pickedPrinter) ?? pictures[0] ?? null;
  const filaments = shownPicture?.filaments ?? entry.filaments;
  const listedPrinters = entry.kind === 'load_filament' && group.printer_id == null ? entry.printers : [];
  // The title names the printers the entry lists, or the other candidate when that one is shown.
  const modelPrinters = shownPicture && listedPrinters.length > 0 && !listedPrinters.some((p) => p.id === shownPicture.printer_id)
    ? [{ id: shownPicture.printer_id, name: shownPicture.printer_name }]
    : listedPrinters;

  // "Print anyway" (#3659) is offered per printer: for the jobs that are held
  // on that printer only because spools are short, and that the caller may
  // start. A job without a printer (`printerId` null) is judged over all of
  // them, and a job of a printer's own group stays on its printer. The start
  // asks the same "Insufficient filament" question as the queue row.
  const printAnyway = (printerId: number | null, printerName?: string) => {
    const offered = jobs.filter((j) => j.can_start && (
      printerId == null
        ? !!j.short_only
        : (j.short_only_printer_ids ?? []).includes(printerId) || (printerId === group.printer_id && !!j.short_only)
    ));
    if (entry.kind !== 'load_filament' || offered.length === 0) return null;
    // An "Any <model>" job is started on the printer the button is for.
    const startOn = printerId != null && group.printer_id == null ? printerId : undefined;
    return (
      <div key={printerId ?? 'any'} className="flex flex-wrap gap-2 min-w-0">
        {offered.map((job) => {
          const what = [offered.length > 1 ? job.name : '', printerName ?? ''].filter(Boolean).join(' \u00b7 ');
          const label = what
            ? `${t('queue.filamentShort.printAnyway')}: ${what}`
            : t('queue.filamentShort.printAnyway');
          return (
            <button
              key={job.id}
              type="button"
              data-testid="todo-print-anyway"
              onClick={() => onStart(job.id, startOn)}
              disabled={startPending}
              title={label}
              aria-label={label}
              className="flex items-center gap-1.5 min-w-0 max-w-full px-3 py-1.5 min-h-[36px] text-sm rounded-md bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Play className="w-4 h-4 flex-shrink-0" />
              <span className="truncate">{label}</span>
            </button>
          );
        })}
      </div>
    );
  };
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
  } else if (onOpenQueue) {
    action = (
      <button type="button" onClick={onOpenQueue} className="text-sm text-bambu-green hover:underline">
        {t('queueTodo.openQueue')}
      </button>
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
          ) : hasPicture ? (
            loadTitle(t, filaments)
          ) : (
            t(KIND_TEXT_KEY[entry.kind])
          )}
        </div>
        {entry.kind === 'print_paused' && entry.paused && (
          <>
            {pausedProgressLine(entry.paused, t) && (
              <div data-testid="todo-paused-progress" className="text-xs text-bambu-gray-light break-words">
                {pausedProgressLine(entry.paused, t)}
              </div>
            )}
            {pausedCauseText(entry.paused, t) && (
              <div data-testid="todo-paused-cause" className="text-xs text-bambu-gray-light break-words">
                {pausedCauseText(entry.paused, t)}
              </div>
            )}
          </>
        )}
        {entry.kind === 'print_paused' && group.printer_id != null && (
          <PausedActions printerId={group.printer_id} printerName={group.printer_name} overlayZIndex={overlayZIndex} />
        )}
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
            {filaments.map((f, i) => (
              <li key={i} data-testid="todo-filament" className="flex items-center gap-1.5 min-w-0 max-w-full text-xs text-bambu-gray-light">
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
                {f.short ? (
                  <span data-testid="todo-short" className="min-w-0 break-words">
                    {shortText(t, f, entry.slot_hint?.state === 'replace' ? entry.slot_hint.slots : [], group.printer_model)}
                  </span>
                ) : (
                  <span>{[f.type, f.color_name].filter(Boolean).join(' ')}</span>
                )}
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
        {picture && <PictureWithActions picture={picture} filaments={entry.filaments} overlayZIndex={overlayZIndex} />}
        {pictures.length > 0 && (
          <AmsPictures
            pictures={pictures}
            filaments={entry.filaments}
            selected={shownPicture?.printer_id ?? null}
            onSelect={setPickedPrinter}
            // The title already names the one printer there is.
            nameSingle={!(modelPrinters.length === 1 && modelPrinters[0].id === pictures[0].printer_id)}
            renderPicture={(p, shown) => (
              <PictureWithActions picture={p} filaments={shown} overlayZIndex={overlayZIndex} />
            )}
            // For the printer shown: none on a printer that lacks a filament.
            renderActions={(p) => printAnyway(p.printer_id)}
          />
        )}
        {entry.kind === 'load_filament' && !hasPicture && <SlotHints entry={entry} />}
        {entry.kind !== 'print_paused' && (
          <div className="text-xs text-bambu-gray truncate max-w-full" title={jobs.map((j) => j.name).join(', ')}>
            {jobLabel}
          </div>
        )}
        {/* A missing filament (not a short spool): add a spool, or change the job (#3726). */}
        {entry.kind === 'load_filament' && filaments.some((f) => !f.short) && (
          <>
            <AddSpoolActions filaments={filaments} main={!hasPicture} overlayZIndex={overlayZIndex} />
            <JobActions jobs={jobs} canMove={group.printer_id != null} overlayZIndex={overlayZIndex} />
          </>
        )}
        {entry.kind === 'power_on_failed' && group.printer_id != null ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <PowerOnAgain printerId={group.printer_id} />
            {action}
          </div>
        ) : (
          action
        )}
        {/* A job that waits only for a short spool has no Start (#3659). A
            printer's own entry has one button per job; an "Any <model>" entry
            has them under the picture of the printer shown, or, without
            pictures, one per listed printer, named when there are several. */}
        {group.printer_id != null
          ? printAnyway(group.printer_id)
          : pictures.length > 0
            ? null
            : modelPrinters.length > 0
              ? modelPrinters.map((p) => printAnyway(p.id, modelPrinters.length > 1 ? p.name : undefined))
              : printAnyway(null)}
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
  // Queue page: shows the Queue tab. "Open queue" is then a button instead of a link.
  onOpenQueue?: () => void;
  // Lifts the filament confirmations above a surrounding panel.
  overlayZIndex?: string;
}

// Everything the queue waits on, grouped by printer. Renders nothing when empty (#3615).
export function QueueTodoList({ todo, onNavigate, onOpenQueue, overlayZIndex }: QueueTodoListProps) {
  const { t } = useTranslation();
  const { startMutation, modals } = useStartQueueItem(overlayZIndex);
  // A group with nothing to show (a printer whose jobs wait on nothing) is
  // left out; the list is empty when no group has an entry or a prepare line.
  const groups = (todo?.groups ?? []).filter((g) => g.entries.length > 0 || prepareLines(g).length > 0);
  if (!todo || groups.length === 0) return null;
  return (
    <div className="space-y-3 min-w-0" data-testid="queue-todo-list">
      {modals}
      {groups.map((group) => (
        <section
          key={group.printer_id ?? `model-${group.target_model}`}
          className="rounded-lg border border-bambu-dark-tertiary bg-bambu-dark-secondary p-3"
        >
          <h3 className="text-sm font-semibold text-white mb-1 truncate">
            {group.printer_id == null
              ? t('queueTodo.anyModel', { model: group.target_model ?? group.printer_name })
              : group.printer_name}
          </h3>
          {group.entries.length > 0 && (
            <ul className="divide-y divide-bambu-dark-tertiary">
              {group.entries.map((entry, i) => (
                <EntryRow
                  key={`${entry.kind}-${i}`}
                  group={group}
                  entry={entry}
                  onNavigate={onNavigate}
                  onOpenQueue={onOpenQueue}
                  onStart={(id, printerId) => startMutation.mutate({ id, printerId })}
                  startPending={startMutation.isPending}
                  overlayZIndex={overlayZIndex}
                />
              ))}
            </ul>
          )}
          {prepareLines(group).length > 0 && <PrepareRows lines={prepareLines(group)} first={group.entries.length === 0} />}
        </section>
      ))}
    </div>
  );
}
