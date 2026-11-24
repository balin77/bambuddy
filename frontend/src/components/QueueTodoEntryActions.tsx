import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import type { PrintQueueItem, QueueTodoFilament } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useToast } from '../contexts/ToastContext';
import { QUEUE_TODO_KEY } from '../hooks/useQueueTodo';
import { useUiSettings } from '../hooks/useUiSettings';
import { getCurrencySymbol } from '../utils/currency';
import { queueItemDisplayName } from '../utils/queueItemName';
import { PrintModal } from './PrintModal';
import { SpoolFormModal } from './SpoolFormModal';

// 44 px high on a phone, as the other buttons of an entry (#3726).
const buttonClass =
  'min-h-[44px] sm:min-h-[36px] px-4 rounded-lg text-sm font-semibold break-words text-left border border-bambu-green text-bambu-green hover:bg-bambu-green/10 disabled:opacity-50 disabled:cursor-not-allowed';

// "Switch on again" for a printer whose smart plug did not switch on: the plug
// is looked up the way the printer card does, and switched with the same call
// as the plug's own controls.
export function PowerOnAgain({ printerId }: { printerId: number }) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
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
  if (!hasPermission('smart_plugs:control')) return null;
  return (
    <button type="button" onClick={() => mutation.mutate()} disabled={mutation.isPending} className={buttonClass}>
      {t('queueTodo.actions.powerOnAgain')}
    </button>
  );
}

interface JobActionsProps {
  jobs: { id: number; name: string }[];
  overlayZIndex?: string;
}

// "Edit job" and "Move to another printer" for the jobs of an entry that
// loading cannot satisfy (#3726). Both open the queue's own edit dialog, which
// holds the filament choice and the printer choice. A button is there for a
// job the user may edit, as on the Queue page: queue:update_all, or
// queue:update_own for their own jobs.
export function JobActions({ jobs, overlayZIndex }: JobActionsProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { hasAnyPermission, canModify } = useAuth();
  const mayEdit = hasAnyPermission('queue:update_all', 'queue:update_own');
  const [editing, setEditing] = useState<PrintQueueItem | null>(null);
  // Owner and file of a job are not in the To do list: read from the queue.
  const { data: queue } = useQuery({
    queryKey: ['queue', 'todo-jobs'],
    queryFn: () => api.getQueue(undefined, 'pending'),
    enabled: mayEdit,
  });
  if (!mayEdit) return null;
  const items = jobs
    .map((job) => queue?.find((item) => item.id === job.id))
    .filter((item): item is PrintQueueItem => !!item && canModify('queue', 'update', item.created_by_id));
  if (items.length === 0) return null;
  const nameOf = (item: PrintQueueItem) => queueItemDisplayName(item, (n) => t('common.plusNMore', { count: n }));
  return (
    <div data-testid="todo-job-actions" data-todo-modal-open={editing ? 'true' : undefined} className="flex flex-wrap gap-2 min-w-0">
      {items.map((item) =>
        (['edit', 'move'] as const).map((kind) => {
          const base = t(kind === 'edit' ? 'queueTodo.actions.editJob' : 'queueTodo.actions.moveJob');
          return (
            <button key={`${item.id}-${kind}`} type="button" onClick={() => setEditing(item)} className={buttonClass}>
              {items.length > 1 ? `${base}: ${nameOf(item)}` : base}
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
export function AddSpoolActions({ filaments, overlayZIndex }: { filaments: QueueTodoFilament[]; overlayZIndex?: string }) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const canCreate = hasPermission('inventory:create');
  const [adding, setAdding] = useState<QueueTodoFilament | null>(null);
  const { data: spoolman } = useQuery({
    queryKey: ['spoolman-status'],
    queryFn: api.getSpoolmanStatus,
    staleTime: 60 * 1000,
    enabled: canCreate,
  });
  const { data: settings } = useUiSettings({ enabled: adding !== null });
  const missing = filaments.filter((f) => f.no_stock && f.type);
  // Until the Spoolman status is known the inventory is not known either.
  if (!canCreate || spoolman === undefined || spoolman.enabled || missing.length === 0) return null;
  return (
    <div data-testid="todo-add-spool" data-todo-modal-open={adding ? 'true' : undefined} className="flex flex-wrap gap-2 min-w-0">
      {missing.map((f, i) => {
        const name = [f.type, f.color_name || f.color].filter(Boolean).join(' ');
        return (
          <button key={i} type="button" onClick={() => setAdding(f)} className={buttonClass}>
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
