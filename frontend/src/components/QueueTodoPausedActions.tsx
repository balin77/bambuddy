import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import { QUEUE_TODO_KEY } from '../hooks/useQueueTodo';
import { usePermissionGate } from '../hooks/usePermissionGate';
import { ConfirmModal } from './ConfirmModal';

// 44 px high on a phone, as the other buttons of an entry (#3726).
const baseClass =
  'min-h-[44px] sm:min-h-[36px] px-4 rounded-lg text-sm font-semibold break-words text-left disabled:opacity-50 disabled:cursor-not-allowed';

interface PausedActionsProps {
  printerId: number;
  printerName: string;
  overlayZIndex?: string;
}

// "Resume" and "Stop" for a paused print, in its To do entry (#3726): the
// same calls and the same stop question as the printer card. Stop always asks.
// A button the caller may not use is greyed out, or left out when their groups
// hide what they cannot use (#3639). The server checks both permissions.
export function PausedActions({ printerId, printerName, overlayZIndex }: PausedActionsProps) {
  const { t } = useTranslation();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const gate = usePermissionGate();
  const resumeGate = gate('printers:pause_resume');
  const stopGate = gate('printers:stop');
  const [confirmingStop, setConfirmingStop] = useState(false);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: QUEUE_TODO_KEY });
    queryClient.invalidateQueries({ queryKey: ['printerStatus', printerId] });
  };
  const resume = useMutation({
    mutationFn: () => api.resumePrint(printerId),
    onSuccess: () => {
      showToast(t('printers.toast.printResumed'));
      refresh();
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToResumePrint'), 'error'),
  });
  const stop = useMutation({
    mutationFn: () => api.stopPrint(printerId),
    onSuccess: () => {
      showToast(t('printers.toast.printStopped'));
      refresh();
    },
    onError: (error: Error) => showToast(error.message || t('printers.toast.failedToStopPrint'), 'error'),
  });
  if (!resumeGate.render && !stopGate.render) return null;
  const busy = resume.isPending || stop.isPending;
  return (
    <div data-testid="todo-paused-actions" data-todo-modal-open={confirmingStop ? 'true' : undefined} className="flex flex-wrap gap-2 min-w-0">
      {resumeGate.render && (
        <button
          type="button"
          onClick={() => resume.mutate()}
          disabled={!resumeGate.allowed || busy}
          title={!resumeGate.allowed ? t('printers.permission.noControl') : undefined}
          className={`${baseClass} bg-bambu-green text-black hover:bg-bambu-green/90`}
        >
          {t('queueTodo.actions.resume')}
        </button>
      )}
      {stopGate.render && (
        <button
          type="button"
          onClick={() => setConfirmingStop(true)}
          disabled={!stopGate.allowed || busy}
          title={!stopGate.allowed ? t('printers.permission.noControl') : undefined}
          className={`${baseClass} border border-red-500/60 text-red-400 hover:bg-red-500/10`}
        >
          {t('queueTodo.actions.stop')}
        </button>
      )}
      {confirmingStop && (
        <ConfirmModal
          title={t('printers.confirm.stopTitle')}
          message={t('printers.confirm.stopMessage', { name: printerName })}
          confirmText={t('printers.confirm.stopButton')}
          variant="danger"
          overlayZIndex={overlayZIndex}
          onConfirm={() => {
            stop.mutate();
            setConfirmingStop(false);
          }}
          onCancel={() => setConfirmingStop(false)}
        />
      )}
    </div>
  );
}
