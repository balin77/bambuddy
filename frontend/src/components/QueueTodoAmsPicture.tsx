import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Lock } from 'lucide-react';
import type {
  QueueTodoFilament,
  QueueTodoPicture,
  QueueTodoPictureSlot,
  QueueTodoPictureUnit,
} from '../api/client';
import { FilamentSlotCircle } from './FilamentSlotCircle';
import { formatSlotLabel, getAmsLabel } from '../utils/amsHelpers';
import { getColorName } from '../utils/colors';

// How many slots one row of a unit holds: the AMS 3H has nine, shown as
// rows of at most five so the cards keep their width.
const MAX_COLUMNS = 5;

type TFn = (key: string, options?: Record<string, unknown>) => string;

// RRGGBBAA of a colour: one that carries its alpha (a translucent or clear spool) keeps it.
const rgbaOf = (color: string) => {
  const hex = color.replace('#', '');
  if (!hex) return '808080FF';
  return hex.length === 8 ? hex : `${hex.slice(0, 6)}FF`;
};

function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

function pictureSlotLabel(slot: QueueTodoPictureSlot): string {
  return formatSlotLabel(slot.ams_id, slot.tray_id, slot.is_ht, slot.is_external, slot.ams_type);
}

// The units shown in one block: AMS-HT units sit side by side in one row, as
// on the printer card, when they feed the same nozzle.
function joinHtUnits(units: QueueTodoPictureUnit[]): QueueTodoPictureUnit[] {
  const out: QueueTodoPictureUnit[] = [];
  for (const unit of units) {
    const last = out[out.length - 1];
    if (unit.kind === 'ht' && last && last.kind === 'ht' && last.nozzle === unit.nozzle) {
      out[out.length - 1] = { ...last, slots: [...last.slots, ...unit.slots] };
    } else {
      out.push(unit);
    }
  }
  return out;
}

function unitLabel(t: TFn, unit: QueueTodoPictureUnit): string {
  const base = unit.kind === 'external'
    ? t('queueTodo.picture.external')
    : unit.kind === 'ht' && unit.slots.length > 1
      ? unit.slots.map((s) => pictureSlotLabel(s)).join(', ')
      : getAmsLabel(unit.ams_id, unit.ams_type);
  if (!unit.nozzle) return base;
  return `${base} · ${t(unit.nozzle === 'left' ? 'printModal.leftNozzleTooltip' : 'printModal.rightNozzleTooltip')}`;
}

function Arrow({ label }: { label: string }) {
  return (
    <svg role="img" aria-label={label} width="24" height="30" viewBox="0 0 24 30" fill="none" className="text-bambu-green" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2v24" />
      <path d="M5 19l7 8 7-8" />
    </svg>
  );
}

// "227 g" and "80 %" in the interface language.
// The unit never wraps away from its number.
const gramsText = (grams: number, language: string) =>
  new Intl.NumberFormat(language, { style: 'unit', unit: 'gram', unitDisplay: 'short', maximumFractionDigits: 0 }).format(grams).replace(/\s/g, '\u00a0');
const percentText = (percent: number, language: string) =>
  new Intl.NumberFormat(language, { style: 'percent', maximumFractionDigits: 0 }).format(percent / 100);

function amountText(language: string, slot: QueueTodoPictureSlot): string {
  if (typeof slot.remaining_g === 'number') return gramsText(slot.remaining_g, language);
  if (typeof slot.remain_percent === 'number') return percentText(slot.remain_percent, language);
  return '—';
}

// The text under a slot's filament: its state, never colour alone.
function stateLine(t: TFn, language: string, slot: QueueTodoPictureSlot, compact: boolean): { text: string; className: string } {
  // A compact card has no name line: an amount that is not known says nothing, not a lone dash.
  const known = typeof slot.remaining_g === 'number' || typeof slot.remain_percent === 'number';
  const amount = slot.type && (known || !compact) ? amountText(language, slot) : '';
  switch (slot.state) {
    case 'out':
      return { text: amount ? t('queueTodo.picture.outWith', { amount }) : t('queueTodo.picture.out'), className: 'font-semibold text-amber-400' };
    case 'fits':
      return { text: amount ? t('queueTodo.picture.fitsWith', { amount }) : t('queueTodo.picture.fits'), className: 'text-bambu-green' };
    case 'locked':
      return { text: t('queueTodo.picture.locked'), className: 'text-bambu-gray' };
    case 'empty':
      return { text: t('queueTodo.picture.empty'), className: 'text-bambu-gray' };
    case 'unknown':
      return { text: t('queueTodo.picture.unknown'), className: 'text-bambu-gray' };
    default:
      return { text: amount, className: 'text-bambu-gray' };
  }
}

const CARD_STATE_CLASS: Record<QueueTodoPictureSlot['state'], string> = {
  keep: 'border border-bambu-dark-tertiary bg-bambu-dark-secondary',
  locked: 'border border-bambu-dark-tertiary bg-bambu-dark-secondary',
  out: 'border-2 border-amber-400 bg-amber-500/10',
  fits: 'border border-bambu-green/60 bg-bambu-green/10',
  empty: 'border border-dashed border-bambu-gray/60 bg-bambu-dark',
  unknown: 'border border-dashed border-amber-400/70 bg-bambu-dark',
};

function SlotCard({ slot, compact, row, column }: { slot: QueueTodoPictureSlot; compact: boolean; row: number; column: number }) {
  const { t, i18n } = useTranslation();
  const line = stateLine(t, i18n.language, slot, compact);
  const loaded = !!slot.type;
  const colorName = slot.color_name || (slot.color ? getColorName(slot.color, slot.tray_sub_brands || null, slot.tray_info_idx) : '');
  const filament = [slot.type, colorName].filter(Boolean).join(' ');
  const swatch = compact ? 'w-[22px] h-[22px]' : 'w-[30px] h-[30px]';
  return (
    <div
      data-testid="todo-ams-slot"
      data-state={slot.state}
      style={{ gridRow: row, gridColumn: column }}
      className={`min-w-0 rounded-[10px] px-1 sm:px-1.5 ${compact ? 'py-1.5' : 'py-2.5'} flex flex-col items-center gap-1 text-center ${CARD_STATE_CLASS[slot.state]}`}
    >
      <div className="flex items-center gap-1 text-xs font-bold text-white">
        {pictureSlotLabel(slot)}
        {slot.state === 'locked' && <Lock role="img" aria-label={t('queueTodo.picture.lockedLabel')} className="w-3 h-3 text-bambu-gray" />}
      </div>
      <FilamentSlotCircle
        isEmpty={!loaded}
        trayType={slot.type}
        // No number: the card's own label above says which slot it is.
        slotNumber=""
        rgba={loaded ? (slot.rgba || rgbaOf(slot.color)) : null}
        extraColors={slot.extra_colors || null}
        effectType={slot.effect_type || null}
        subtype={slot.subtype || null}
        testId="todo-ams-circle"
        sizeClass={swatch}
        numberClass={compact ? 'text-[10px]' : 'text-xs'}
        borderColor="rgba(156,163,175,0.7)"
        className={`flex-shrink-0 ${slot.state === 'out' ? 'opacity-[0.55]' : ''}`.trim()}
      />
      {!compact && loaded && (
        <div className="w-full min-w-0 text-[10px] sm:text-[11px] leading-tight text-white line-clamp-2 break-words" title={filament}>
          {filament}
        </div>
      )}
      <div className={`w-full min-w-0 text-[10px] sm:text-[11px] leading-tight break-words ${line.className}`}>{line.text || ' '}</div>
    </div>
  );
}

function IncomingCard({
  slot,
  filament,
  compact,
  row,
  column,
}: {
  slot: QueueTodoPictureSlot;
  filament: QueueTodoFilament | undefined;
  compact: boolean;
  row: number;
  column: number;
}) {
  const { t, i18n } = useTranslation();
  const incoming = slot.incoming;
  if (!incoming) return null;
  const grams = typeof incoming.required_g === 'number' ? gramsText(incoming.required_g, i18n.language) : null;
  let sub = '';
  if (filament?.short) {
    sub = grams ? t('queueTodo.picture.newMin', { grams }) : t('queueTodo.picture.new');
  } else if (typeof incoming.stock_count === 'number' && !compact) {
    sub = incoming.stock_count > 0 ? t('queueTodo.picture.inStock', { count: incoming.stock_count }) : t('queueTodo.picture.notInStock');
  } else if (grams) {
    sub = t('queueTodo.picture.minGrams', { grams });
  }
  const name = [incoming.type, incoming.color_name].filter(Boolean).join(' ') || incoming.color;
  return (
    <div
      data-testid="todo-ams-incoming"
      style={{ gridRow: row, gridColumn: column }}
      className="min-w-0 rounded-[10px] border border-bambu-green bg-bambu-green/10 px-1 sm:px-1.5 py-2 flex flex-col items-center gap-1 text-center"
    >
      <FilamentSlotCircle
        isEmpty={false}
        trayType={incoming.type}
        slotNumber=""
        rgba={rgbaOf(incoming.color)}
        testId="todo-ams-incoming-circle"
        sizeClass={compact ? 'w-6 h-6' : 'w-[34px] h-[34px]'}
        borderColor="rgba(255,255,255,0.9)"
        className="flex-shrink-0"
      />
      <div className="w-full min-w-0 text-[10px] sm:text-xs font-semibold leading-tight text-white line-clamp-2 break-words" title={name}>
        {name}
      </div>
      {sub && <div className="w-full min-w-0 text-[10px] sm:text-[11px] leading-tight text-bambu-gray-light break-words">{sub}</div>}
    </div>
  );
}

// One unit: a single grid whose columns are the slot positions. The incoming
// filament of a slot is in row 1 of the same column, its arrow in row 2, the
// slot in row 3, so an arrow always runs straight down and none crosses
// another. A slot nothing goes into gets an empty cell above it.
function Unit({ unit, filaments, compact }: { unit: QueueTodoPictureUnit; filaments: QueueTodoFilament[]; compact: boolean }) {
  const { t } = useTranslation();
  const columns = Math.min(MAX_COLUMNS, Math.max(unit.slots.length, 4));
  const lines = chunk(unit.slots, MAX_COLUMNS);
  return (
    <section
      data-testid="todo-ams-unit"
      aria-label={unitLabel(t, unit)}
      className="min-w-0 w-fit max-w-full rounded-xl border border-bambu-dark-tertiary bg-bambu-dark p-2 sm:p-2.5 space-y-2"
    >
      <h4 className="text-[11px] font-semibold uppercase tracking-wider text-bambu-gray break-words">{unitLabel(t, unit)}</h4>
      <div
        data-testid="todo-ams-grid"
        className="grid gap-x-1.5 sm:gap-x-2.5 gap-y-0"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 7.5rem))`, justifyContent: 'start' }}
      >
        {lines.flatMap((line, li) => {
          const base = li * 3;
          const lineHasIncoming = line.some((s) => s.incoming);
          return [
            ...(lineHasIncoming
              ? line.flatMap((slot, ci) =>
                  slot.incoming
                    ? [
                        <IncomingCard
                          key={`in-${li}-${ci}`}
                          slot={slot}
                          filament={filaments[slot.incoming.filament_index]}
                          compact={compact}
                          row={base + 1}
                          column={ci + 1}
                        />,
                        <div key={`arrow-${li}-${ci}`} data-testid="todo-ams-arrow" style={{ gridRow: base + 2, gridColumn: ci + 1 }} className="flex justify-center py-1">
                          <Arrow label={t('queueTodo.picture.goesTo', { slot: pictureSlotLabel(slot) })} />
                        </div>,
                      ]
                    : [
                        <div
                          key={`gap-${li}-${ci}`}
                          data-testid="todo-ams-empty-cell"
                          aria-hidden="true"
                          style={{ gridRow: `${base + 1} / span 2`, gridColumn: ci + 1 }}
                        />,
                      ],
                )
              : []),
            ...line.map((slot, ci) => (
              <SlotCard key={`slot-${slot.ams_id}-${slot.tray_id}`} slot={slot} compact={compact} row={base + 3} column={ci + 1} />
            )),
          ];
        })}
      </div>
    </section>
  );
}

interface AmsPictureProps {
  picture: QueueTodoPicture;
  // The entry's filaments: what an incoming card says about its filament.
  filaments: QueueTodoFilament[];
}

// The printer's AMS with where each filament of the entry goes (#3726).
// Units nothing goes into are folded behind a toggle.
export function AmsPicture({ picture, filaments }: AmsPictureProps) {
  const { t } = useTranslation();
  // Per printer: switching to another one starts folded again.
  const [expandedFor, setExpandedFor] = useState<number | null>(null);
  const expanded = expandedFor === picture.printer_id;
  const open = picture.units.filter((u) => !u.collapsed);
  const folded = picture.units.filter((u) => u.collapsed);
  const shown = joinHtUnits(expanded ? picture.units : open);
  const foldedNames = joinHtUnits(folded).map((u) => unitLabel(t, u)).join(', ');
  const unplaced = picture.unplaced
    .map((i) => filaments[i])
    .filter((f): f is QueueTodoFilament => !!f)
    .map((f) => [f.type, f.color_name || f.color].filter(Boolean).join(' '));
  return (
    <div data-testid="todo-ams-picture" data-compact={picture.compact ? 'true' : 'false'} className="min-w-0 space-y-2">
      {shown.map((unit) => (
        <Unit key={`${unit.kind}-${unit.ams_id}-${unit.slots[0]?.tray_id}`} unit={unit} filaments={filaments} compact={picture.compact} />
      ))}
      {folded.length > 0 && (
        <button
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpandedFor(expanded ? null : picture.printer_id)}
          className="min-h-[44px] sm:min-h-[36px] px-3 rounded-md border border-bambu-dark-tertiary text-xs text-bambu-gray-light hover:text-white hover:border-bambu-gray"
        >
          {expanded ? t('queueTodo.picture.hideUnits', { units: foldedNames }) : t('queueTodo.picture.showUnits', { units: foldedNames })}
        </button>
      )}
      {unplaced.length > 0 && (
        <div data-testid="todo-ams-unplaced" className="text-xs text-amber-400 break-words">
          {t('queueTodo.picture.unplaced', { filaments: unplaced.join(', ') })}
        </div>
      )}
    </div>
  );
}

interface AmsPicturesProps {
  // One per printer an "Any <model>" entry lists, the one likely to take the job first at the front.
  pictures: QueueTodoPicture[];
  filaments: QueueTodoFilament[];
  // What goes under the picture shown: the actions for that printer.
  renderActions?: (picture: QueueTodoPicture) => ReactNode;
}

// A model job's picture: the printer it would likely go to first, with a
// switch to the other candidates.
export function AmsPictures({ pictures, filaments, renderActions }: AmsPicturesProps) {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<number | null>(null);
  if (pictures.length === 0) return null;
  const current = pictures.find((p) => p.printer_id === selected) ?? pictures[0];
  return (
    <div className="min-w-0 space-y-2">
      {pictures.length > 1 && (
        <div role="group" aria-label={t('queueTodo.picture.printerSwitch')} className="flex flex-wrap gap-2">
          {pictures.map((p, i) => (
            <button
              key={p.printer_id}
              type="button"
              data-testid="todo-ams-printer"
              aria-pressed={p.printer_id === current.printer_id}
              onClick={() => setSelected(p.printer_id)}
              className={`min-h-[44px] sm:min-h-[36px] max-w-full px-3 rounded-md border text-sm text-left break-words ${
                p.printer_id === current.printer_id
                  ? 'border-bambu-green bg-bambu-green/20 text-white'
                  : 'border-bambu-dark-tertiary text-bambu-gray-light hover:text-white hover:border-bambu-gray'
              }`}
            >
              {p.printer_name}
              {i === 0 && <span className="ml-1.5 text-[11px] text-bambu-gray-light">({t('queueTodo.picture.likelyNext')})</span>}
            </button>
          ))}
        </div>
      )}
      {pictures.length === 1 && <div className="text-xs text-bambu-gray-light">{current.printer_name}</div>}
      <AmsPicture picture={current} filaments={filaments} />
      {renderActions?.(current)}
    </div>
  );
}
