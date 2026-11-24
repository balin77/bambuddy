import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { PrintQueueItem, QueueTodoFilament } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { QUEUE_TODO_KEY } from '../hooks/useQueueTodo';
import { usePermissionGate } from '../hooks/usePermissionGate';
import { useUiSettings } from '../hooks/useUiSettings';
import { getCurrencySymbol } from '../utils/currency';
import { queueItemDisplayName } from '../utils/queueItemName';
import { PrintModal } from './PrintModal';
import { SpoolFormModal } from './SpoolFormModal';

// 44 px high on a phone, as the other buttons of an entry (#3726).
const baseClass =
  'min-h-[44px] sm:min-h-[36px] px-4 rounded-lg text-sm font-semibold break-words text-left disabled:opacity-50 disabled:cursor-not-allowed';
// Filled: the main action of an entry. Outlined: a further one (mockup 4).
const buttonClass = `${baseClass} border border-bambu-green text-bambu-green hover:bg-bambu-green/10`;
const mainClass = `${baseClass} bg-bambu-green text-black hover:bg-bambu-green/90`;

// "Switch on again" for a printer whose smart plug did not switch on: the plug
// is looked up the way the printer card does, and switched with the same call
// as the plug's own controls.
export function PowerOnAgain({ printerId }: { printerId: number }) {
  const { t } = useTranslation();
  const plugGate = usePermissionGate()('smart_plugs:control');
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      const plug = await api.getSmartPlugByPrinter(printerId);
      if (!plug) throw new Error(t('queueTodo.actions.noPlug'));
      return api.controlSmartPlug(plug.id, 'on');
    },
    onSuccess: () => {
      showToast(t('queueTodo.actions.powerOnSent'));
      queryClient.invalidateQueries({ queryKey: QUEUE_TODO_KEY });
    },
    onError: (error: unknown) =>
      showToast(error instanceof Error && error.message ? error.message : t('queueTodo.actionFailed'), 'error'),
  });
  if (!plugGate.render) return null;
  return (
    <button
      type="button"
      onClick={() => mutation.mutate()}
      disabled={!plugGate.allowed || mutation.isPending}
      title={!plugGate.allowed ? t('queueTodo.actions.noPermissionPlug') : undefined}
      className={mainClass}
    >
      {t('queueTodo.actions.powerOnAgain')}
    </button>
  );
}

interface JobActionsProps {
  jobs: { id: number; name: string }[];
  // Moving is for jobs pinned to a printer; an "Any <model>" job already goes to any of them.
  canMove: boolean;
  overlayZIndex?: string;
}

// "Edit job" and "Move to another printer" for the jobs of an entry that
// waits for a missing filament (#3726). Both open the queue's own edit dialog, which
// holds the filament choice and the printer choice. A button is there for a
// job the user may edit, as on the Queue page: queue:update_all, or
// queue:update_own for their own jobs.
export function JobActions({ jobs, canMove, overlayZIndex }: JobActionsProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { canModify } = useAuth();
  const editGate = usePermissionGate()(['queue:update_all', 'queue:update_own']);
  const mayEdit = editGate.allowed;
  const [editing, setEditing] = useState<PrintQueueItem | null>(null);
  // Owner and file of a job are not in the To do list: read from the queue.
  const { data: queue } = useQuery({
    queryKey: ['queue', 'todo-jobs'],
    queryFn: () => api.getQueue(undefined, 'pending'),
    enabled: mayEdit,
  });
  if (!editGate.render) return null;
  // Without the permission the buttons are drawn greyed out from the entry's own jobs.
  const items: { id: number; name: string; item: PrintQueueItem | null }[] = mayEdit
    ? jobs
        .map((job) => queue?.find((q) => q.id === job.id))
        .filter((q): q is PrintQueueItem => !!q && canModify('queue', 'update', q.created_by_id))
        .map((q) => ({ id: q.id, name: queueItemDisplayName(q, (n) => t('common.plusNMore', { count: n })), item: q }))
    : jobs.map((job) => ({ id: job.id, name: job.name, item: null }));
  if (items.length === 0) return null;
  const nameOf = (item: PrintQueueItem) => queueItemDisplayName(item, (n) => t('common.plusNMore', { count: n }));
  return (
    <div data-testid="todo-job-actions" data-todo-modal-open={editing ? 'true' : undefined} className="flex flex-wrap gap-2 min-w-0">
      {items.map((entry) =>
        (canMove ? (['edit', 'move'] as const) : (['edit'] as const)).map((kind) => {
          const base = t(kind === 'edit' ? 'queueTodo.actions.editJob' : 'queueTodo.actions.moveJob');
          return (
            <button
              key={`${entry.id}-${kind}`}
              type="button"
              onClick={() => entry.item && setEditing(entry.item)}
              disabled={!mayEdit}
              title={!mayEdit ? t('queueTodo.actions.noPermissionEdit') : undefined}
              className={buttonClass}
            >
              {items.length > 1 ? `${base}: ${entry.name}` : base}
            </button>
          );
        }),
      )}
      {editing && (
        <PrintModal
          mode="edit-queue-item"
          archiveId={editing.archive_id ?? undefined}
          libraryFileId={editing.library_file_id ?? undefined}
          archiveName={nameOf(editing)}
          queueItem={editing}
          overlayZIndex={overlayZIndex}
          onClose={() => setEditing(null)}
          onSuccess={() => queryClient.invalidateQueries({ queryKey: QUEUE_TODO_KEY })}
        />
      )}
    </div>
  );
}

const rgbaOf = (color: string) => (/^#[0-9a-f]{6}$/i.test(color) ? `${color.slice(1).toUpperCase()}FF` : undefined);

// "Add spool" for a filament with none left in the inventory (#3726): the
// new-spool form, started with the filament's type and colour. Built-in
// inventory only: with Spoolman the spools are made there.
export function AddSpoolActions({ filaments, main, overlayZIndex }: { filaments: QueueTodoFilament[]; main: boolean; overlayZIndex?: string }) {
  const { t } = useTranslation();
  const createGate = usePermissionGate()('inventory:create');
  const [adding, setAdding] = useState<QueueTodoFilament | null>(null);
  const { data: spoolman } = useQuery({
    queryKey: ['spoolman-status'],
    queryFn: api.getSpoolmanStatus,
    staleTime: 60 * 1000,
  });
  const { data: settings } = useUiSettings({ enabled: adding !== null });
  const missing = filaments.filter((f) => f.no_stock && f.type);
  // Until the Spoolman status is known the inventory is not known either.
  if (!createGate.render || spoolman === undefined || spoolman.enabled || missing.length === 0) return null;
  return (
    <div data-testid="todo-add-spool" data-todo-modal-open={adding ? 'true' : undefined} className="flex flex-wrap gap-2 min-w-0">
      {missing.map((f, i) => {
        const name = [f.type, f.color_name || f.color].filter(Boolean).join(' ');
        return (
          <button
            key={i}
            type="button"
            onClick={() => setAdding(f)}
            disabled={!createGate.allowed}
            title={!createGate.allowed ? t('queueTodo.assign.noPermissionCreate') : undefined}
            className={main ? mainClass : buttonClass}
          >
            {missing.length > 1 ? t('queueTodo.actions.addSpoolFor', { filament: name }) : t('queueTodo.actions.addSpool')}
          </button>
        );
      })}
      {adding && (
        <SpoolFormModal
          isOpen
          mode="create"
          onClose={() => setAdding(null)}
          currencySymbol={getCurrencySymbol(settings?.currency || 'USD')}
          overlayZIndex={overlayZIndex ?? 'z-50'}
          initialValues={{ material: adding.type, color_name: adding.color_name, ...(rgbaOf(adding.color) ? { rgba: rgbaOf(adding.color) } : {}) }}
        />
      )}
    </div>
  );
}
