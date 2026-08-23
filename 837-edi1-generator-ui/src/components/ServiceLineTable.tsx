/**
 * Section 05's line-item table.
 *
 * Two columns are not editable, and both because the generator owns them:
 *   - Date of Service comes from the allocator's window (masterfile.py
 *     next_window), so a hand-typed date is refused by money_edits.
 *   - Savings for 837I is an exact 85/15 split of the charge
 *     (UHCG_Validation_Rules_Institutional.csv), so the generator derives it.
 * Allowed is read-only in both, being billed - savings.
 */
import React from 'react';
import { allowedFrom, derivedSavings, total } from '../api/money.js';
import { mono } from '../styles/ui.js';
import type { Line, TxType } from '../api/types.js';

interface Props {
  type: TxType;
  lines: Line[];
  onChange: (index: number, field: keyof Line, value: string) => void;
  onAdd: () => void;
  onRemove: (index: number) => void;
}

const COLUMNS = '36px 1fr 1fr 1fr 1fr 32px';

const cell: React.CSSProperties = { padding: '4px 0' };
const head: React.CSSProperties = {
  fontSize: 11, fontWeight: 600, color: '#5b6478', paddingBottom: 8,
};
const boxed: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '7px 9px',
  border: '1px solid #dde1ea',
  borderRadius: 6,
  fontSize: 13,
  fontFamily: mono,
};
const money: React.CSSProperties = { ...boxed, padding: '7px 9px 7px 22px' };
const frozen: React.CSSProperties = {
  background: '#f2f4f7', color: '#5b6478', cursor: 'not-allowed',
};
const totalCell: React.CSSProperties = {
  borderTop: '1px solid #eceef3',
  marginTop: 6,
  paddingTop: 10,
  fontWeight: 700,
  fontFamily: mono,
};

/** CCYYMMDD as the handoff's MM/DD/YYYY. */
export function displayDate(ccyymmdd: string): string {
  if (!/^\d{8}$/.test(ccyymmdd)) return ccyymmdd;
  return `${ccyymmdd.slice(4, 6)}/${ccyymmdd.slice(6, 8)}/${ccyymmdd.slice(0, 4)}`;
}

function savingsOf(type: TxType, line: Line): string {
  return type === 'I' ? derivedSavings(line.billed) : line.savings;
}

export function ServiceLineTable(
  { type, lines, onChange, onAdd, onRemove }: Props,
) {
  const derived = type === 'I';
  const savings = lines.map((l) => savingsOf(type, l));
  const allowed = lines.map((l, i) => allowedFrom(l.billed, savings[i]));

  return (
    <div style={{ padding: 16 }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: COLUMNS,
        gap: '0 12px',
        alignItems: 'center',
      }}
      >
        <div />
        <div style={head}>
          Date of Service
          <br />
          <span style={{ fontWeight: 400, color: '#8892a6', fontSize: 10 }}>
            MM/DD/YYYY · allocated
          </span>
        </div>
        <div style={head}>Billed</div>
        <div style={head}>
          Savings
          {derived && (
            <br />
          )}
          {derived && (
            <span style={{ fontWeight: 400, color: '#8892a6', fontSize: 10 }}>
              derived 15%
            </span>
          )}
        </div>
        <div style={head}>Allowed</div>
        <div />

        {lines.map((line, i) => (
          // eslint-disable-next-line react/no-array-index-key
          <React.Fragment key={i}>
            <div style={{
              fontWeight: 600, color: '#26408f', fontFamily: mono, padding: '6px 0',
            }}
            >
              {i + 1}
            </div>
            <div style={cell}>
              <input
                type="text"
                readOnly
                aria-label={`Date of service, line ${i + 1}`}
                title="Service dates come from the allocator's window and cannot be edited"
                value={displayDate(line.date)}
                style={{ ...boxed, ...frozen }}
              />
            </div>
            <div style={{ ...cell, position: 'relative' }}>
              <span style={{
                position: 'absolute',
                left: 9,
                top: '50%',
                transform: 'translateY(-50%)',
                color: '#5b6478',
                fontSize: 13,
              }}
              >
                $
              </span>
              <input
                type="number"
                step="0.01"
                aria-label={`Billed, line ${i + 1}`}
                value={line.billed}
                onChange={(e) => onChange(i, 'billed', e.target.value)}
                style={money}
              />
            </div>
            <div style={{ ...cell, position: 'relative' }}>
              <span style={{
                position: 'absolute',
                left: 9,
                top: '50%',
                transform: 'translateY(-50%)',
                color: '#5b6478',
                fontSize: 13,
              }}
              >
                $
              </span>
              <input
                type="number"
                step="0.01"
                aria-label={`Savings, line ${i + 1}`}
                readOnly={derived}
                title={derived
                  ? 'An 837I savings is an exact 15% of the charge, derived by the generator'
                  : undefined}
                value={savings[i]}
                onChange={derived
                  ? undefined
                  : (e) => onChange(i, 'savings', e.target.value)}
                style={derived ? { ...money, ...frozen } : money}
              />
            </div>
            <div style={{
              ...cell, fontFamily: mono, fontSize: 13, color: '#1a2233', fontWeight: 600,
            }}
            >
              {allowed[i] === '' ? '—' : `$${allowed[i]}`}
            </div>
            <div style={cell}>
              {lines.length > 1 && (
                <button
                  type="button"
                  aria-label={`Remove line ${i + 1}`}
                  onClick={() => onRemove(i)}
                  style={{
                    cursor: 'pointer',
                    color: '#8892a6',
                    fontSize: 16,
                    background: 'none',
                    border: 'none',
                    width: '100%',
                  }}
                >
                  ×
                </button>
              )}
            </div>
          </React.Fragment>
        ))}

        <div style={{ ...totalCell, gridColumn: '1 / span 2', fontFamily: 'inherit' }}>
          Total
        </div>
        <div style={{ ...totalCell, gridColumn: 3 }}>
          {`$${total(lines.map((l) => l.billed))}`}
        </div>
        <div style={{ ...totalCell, gridColumn: 4 }}>{`$${total(savings)}`}</div>
        <div style={{ ...totalCell, gridColumn: 5 }}>{`$${total(allowed)}`}</div>
      </div>
      <button
        type="button"
        onClick={onAdd}
        style={{
          marginTop: 14,
          padding: '8px 14px',
          border: '1.5px dashed #0084cc',
          background: '#fff',
          color: '#0084cc',
          borderRadius: 6,
          fontSize: 12.5,
          fontWeight: 600,
          cursor: 'pointer',
          fontFamily: mono,
        }}
      >
        + Add Line
      </button>
    </div>
  );
}
