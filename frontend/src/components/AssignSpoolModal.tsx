import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Package, QrCode } from 'lucide-react';
import { AssignSpoolPicker, type AssignSpoolTrayInfo } from './AssignSpoolPicker';

interface AssignSpoolModalProps {
  isOpen: boolean;
  onClose: () => void;
  printerId: number;
  amsId: number;
  trayId: number;
  trayInfo?: AssignSpoolTrayInfo;
  spoolmanEnabled?: boolean;
}

// The dialog around the shared picker (AssignSpoolPicker): its frame and
// title. The picker is mounted while the dialog is open, so it starts clean.
export function AssignSpoolModal({ isOpen, onClose, printerId, amsId, trayId, trayInfo, spoolmanEnabled }: AssignSpoolModalProps) {
  const { t } = useTranslation();
  const [scanning, setScanning] = useState(false);
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start sm:items-center justify-center p-4 overflow-y-auto">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      <div className="relative w-full max-w-2xl bg-bambu-dark-secondary border border-bambu-dark-tertiary rounded-xl shadow-2xl max-h-[90vh] overflow-hidden flex flex-col my-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-bambu-dark-tertiary">
          <div className="flex items-center gap-2">
            {scanning ? <QrCode className="w-5 h-5 text-bambu-green" /> : <Package className="w-5 h-5 text-bambu-green" />}
            <h2 className="text-lg font-semibold text-white">
              {scanning ? t('inventory.qrAssign.scanTitle') : t('inventory.assignSpool')}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-bambu-gray hover:text-white rounded transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <AssignSpoolPicker
          layout="modal"
          printerId={printerId}
          amsId={amsId}
          trayId={trayId}
          trayInfo={trayInfo}
          spoolmanEnabled={spoolmanEnabled}
          onDone={onClose}
          onCancel={onClose}
          onScanningChange={setScanning}
        />
      </div>
    </div>
  );
}
