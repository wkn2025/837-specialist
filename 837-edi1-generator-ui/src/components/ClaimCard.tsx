/**
 * Section 05, one card per claim. Collapsed by default: a 200-claim batch
 * is a scroll, not a form, unless the claims stay shut.
 */
import type { ClaimDoc, Line, TxType } from '@/api/types';
import { ServiceLineTable } from './ServiceLineTable';

export function ClaimCard({
  claim, total, type, expanded, diagnosisEdited,
  onToggle, onDiagnosis, onLine, onAddLine, onRemoveLine,
}: {
  claim: ClaimDoc;
  total: number;
  type: TxType;
  expanded: boolean;
  diagnosisEdited: boolean;
  onToggle: () => void;
  onDiagnosis: (value: string) => void;
  onLine: (i: number, field: keyof Line, value: string) => void;
  onAddLine: () => void;
  onRemoveLine: (i: number) => void;
}) {
  const bodyId = `claim-${claim.n}-body`;
  return (
    <div className="claim">
      <div
        className="claim__head"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle(); }
        }}
      >
        <span>Claim {claim.n} of {total}</span>
        <button
          type="button"
          className="claim__toggle"
          // The whole header toggles too; without this the click would
          // toggle twice and land back where it started.
          onClick={(e) => { e.stopPropagation(); onToggle(); }}
        >
          {expanded ? 'Hide' : 'Show'}
        </button>
      </div>

      {/* Mounted only while open. A 200-claim batch would otherwise carry
          200 hidden line tables in the DOM, and the prototype's own body
          appears and disappears with the toggle. */}
      {expanded && (
        <div className="claim__wrap">
          <div className="claim__inner">
            <div className="claim__body" id={bodyId}>
              <div className="panel">
                <div className="panel__head">
                  <div className="panel__title">Diagnosis Codes</div>
                  {!diagnosisEdited && (
                    <div className="tag-auto">Auto-filled</div>
                  )}
                </div>
                <div className="panel__body">
                  <div className="field">
                    <label htmlFor={`dx-${claim.n}`}>
                      Primary Diagnosis (ICD-10)
                    </label>
                    <input
                      id={`dx-${claim.n}`}
                      type="text"
                      value={claim.principalDiagnosis}
                      onChange={(e) => onDiagnosis(e.target.value)}
                    />
                  </div>
                </div>
              </div>

              <ServiceLineTable
                lines={claim.lines}
                type={type}
                onChange={onLine}
                onAdd={onAddLine}
                onRemove={onRemoveLine}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
