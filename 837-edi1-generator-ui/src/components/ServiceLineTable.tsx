/**
 * The per-claim line-item table.
 *
 * For 837I the Savings column is read-only and shows the derived 85/15
 * split: overrides.py computes that split itself and refuses a supplied
 * value that disagrees with it, so an editable input there would be a lie
 * about what the generator will accept. For 837P the savings is a real
 * input - the generator requires one per line.
 */
import type { Line, TxType } from '@/api/types';
import { allowed, cents, derivedSavings, money, parseDate, showDate }
  from '@/lib/fields';

function total(lines: Line[], pick: (l: Line) => string): number {
  return lines.reduce((sum, l) => sum + (cents(pick(l)) ?? 0), 0);
}

export function ServiceLineTable({ lines, type, onChange, onAdd, onRemove }: {
  lines: Line[];
  type: TxType;
  onChange: (i: number, field: keyof Line, value: string) => void;
  onAdd: () => void;
  onRemove: (i: number) => void;
}) {
  const derived = type === 'I';
  const savingsOf = (l: Line) => (derived ? derivedSavings(l.billed) : l.savings);
  const billedTotal = total(lines, (l) => l.billed);
  const savingsTotal = total(lines, savingsOf);

  return (
    <div className="panel">
      <div className="panel__head">
        <div className="panel__title">Claim / Service Line Info</div>
      </div>
      <div className="lines">
        {/* Four numeric columns do not fit a phone; the table scrolls in
            its own box rather than squeezing every input past use. */}
        <div className="lines__scroll">
        <div className="lines__grid">
          <div />
          <div className="lines__hd">
            Date of Service<span>MM/DD/YYYY</span>
          </div>
          <div className="lines__hd">Billed</div>
          <div className="lines__hd">
            Savings{derived && <span>15% of billed</span>}
          </div>
          <div className="lines__hd">Allowed</div>
          <div />

          {lines.map((line, i) => {
            const savings = savingsOf(line);
            return (
              // Lines have no id of their own; the row's position IS its
              // identity, exactly as splice_lines addresses LX loops.
              // eslint-disable-next-line react/no-array-index-key
              <div className="lines__row" key={i}>
                <div className="lines__n">{i + 1}</div>
                <div className="lines__cell">
                  <input
                    type="text"
                    aria-label={`Line ${i + 1} date of service`}
                    placeholder="MM/DD/YYYY"
                    value={showDate(line.date)}
                    onChange={(e) =>
                      onChange(i, 'date', parseDate(e.target.value))}
                  />
                </div>
                <div className="lines__cell lines__cell--money">
                  <span className="lines__money" aria-hidden="true">$</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    aria-label={`Line ${i + 1} billed`}
                    value={line.billed}
                    onChange={(e) => onChange(i, 'billed', e.target.value)}
                  />
                </div>
                <div className="lines__cell lines__cell--money">
                  <span className="lines__money" aria-hidden="true">$</span>
                  <input
                    type="text"
                    inputMode="decimal"
                    aria-label={`Line ${i + 1} savings`}
                    value={savings}
                    readOnly={derived}
                    title={derived
                      ? '837I savings is the 85/15 split of the billed charge'
                      : undefined}
                    onChange={(e) => onChange(i, 'savings', e.target.value)}
                  />
                </div>
                <div className="lines__derived">
                  ${allowed(line.billed, savings) || '0.00'}
                </div>
                {lines.length > 1 ? (
                  <button
                    type="button"
                    className="lines__remove"
                    aria-label={`Remove line ${i + 1}`}
                    onClick={() => onRemove(i)}
                  >
                    ×
                  </button>
                ) : <div />}
              </div>
            );
          })}

          <div className="lines__total lines__total--label">Total</div>
          <div className="lines__total">${money(billedTotal)}</div>
          <div className="lines__total">${money(savingsTotal)}</div>
          <div className="lines__total">
            ${money(billedTotal - savingsTotal)}
          </div>
        </div>
        </div>
        <button type="button" className="btn-add" onClick={onAdd}>
          + Add Line
        </button>
      </div>
    </div>
  );
}
