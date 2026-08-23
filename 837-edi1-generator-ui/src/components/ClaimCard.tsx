/** Section 05: one collapsible card per claim. */
import React from 'react';
import { autoTag, input, label } from '../styles/ui.js';
import { ServiceLineTable } from './ServiceLineTable.js';
import type { ClaimDoc, Line, TxType } from '../api/types.js';

interface Props {
  type: TxType;
  claim: ClaimDoc;
  total: number;
  expanded: boolean;
  diagnosisEdited: boolean;
  onToggle: (n: number) => void;
  onDiagnosis: (n: number, value: string) => void;
  onLine: (n: number, index: number, field: keyof Line, value: string) => void;
  onAddLine: (n: number) => void;
  onRemoveLine: (n: number, index: number) => void;
}

const innerCard: React.CSSProperties = {
  border: '1px solid #dde1ea', borderRadius: 8, overflow: 'hidden',
};
const innerHeader: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '12px 16px',
  background: '#f7f8fa',
  borderBottom: '1px solid #eceef3',
};

export function ClaimCard(props: Props) {
  const {
    type, claim, total, expanded, diagnosisEdited,
    onToggle, onDiagnosis, onLine, onAddLine, onRemoveLine,
  } = props;

  return (
    <div style={{
      border: '1.5px solid #26408f',
      borderRadius: 10,
      overflow: 'hidden',
      background: '#fff',
    }}
    >
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={() => onToggle(claim.n)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle(claim.n);
          }
        }}
        style={{
          padding: '12px 20px',
          background: '#26408f',
          color: '#fff',
          fontSize: 13.5,
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
        }}
      >
        <span>{`Claim ${claim.n} of ${total}`}</span>
        <button
          type="button"
          // The whole header toggles too, so this must not toggle twice.
          onClick={(e) => { e.stopPropagation(); onToggle(claim.n); }}
          style={{
            padding: '5px 12px',
            border: '1px solid rgba(255,255,255,.5)',
            background: 'transparent',
            color: '#fff',
            borderRadius: 5,
            fontSize: 12,
            cursor: 'pointer',
            fontFamily: 'Arial, sans-serif',
          }}
        >
          {expanded ? 'Hide' : 'Show'}
        </button>
      </div>

      {/* Collapsed content is not rendered at all: leaving it in the DOM
          would keep its inputs focusable behind a closed card. */}
      {expanded && (
      <div className="claim-body">
        <div style={{ overflow: 'hidden' }}>
          <div style={{
            padding: '18px 20px',
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}
          >
            <div style={innerCard}>
              <div style={innerHeader}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>Diagnosis Codes</div>
                {!diagnosisEdited && <div style={autoTag}>Auto-filled</div>}
              </div>
              <div style={{
                padding: 16,
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '14px 18px',
              }}
              >
                <div>
                  <label style={label} htmlFor={`diagnosis-${claim.n}`}>
                    Primary Diagnosis (ICD-10, no dot)
                  </label>
                  <input
                    id={`diagnosis-${claim.n}`}
                    type="text"
                    value={claim.principalDiagnosis}
                    onChange={(e) => onDiagnosis(claim.n, e.target.value)}
                    style={input}
                  />
                </div>
              </div>
            </div>

            <div style={innerCard}>
              <div style={innerHeader}>
                <div style={{ fontSize: 13.5, fontWeight: 600 }}>
                  Claim / Service Line Info
                </div>
              </div>
              <ServiceLineTable
                type={type}
                lines={claim.lines}
                onChange={(i, field, value) => onLine(claim.n, i, field, value)}
                onAdd={() => onAddLine(claim.n)}
                onRemove={(i) => onRemoveLine(claim.n, i)}
              />
            </div>
          </div>
        </div>
      </div>
      )}
    </div>
  );
}
