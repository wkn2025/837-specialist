import { useState } from 'react';
import type {
  CheckStatus, Edi2Check, Edi2ValidationResult,
} from '@/api/types';
import { CHECK_FILTERS, statusLabel, workflowLabel } from './validationView';

type Props = {
  result: Edi2ValidationResult;
  onTrace: (traceId: string) => void;
};

function Check({ check, onTrace }: {
  check: Edi2Check;
  onTrace: (traceId: string) => void;
}) {
  return (
    <article className={`edi2-check edi2-check--${check.status}`}>
      <div className="edi2-check__head">
        <span className="edi2-check__status">{check.status}</span>
        <strong>{check.label}</strong>
        <code>{check.id}</code>
      </div>
      {check.skippedReason && <p>{check.skippedReason}</p>}
      {check.findings.map((finding, index) => (
        <div className="edi2-finding" key={`${finding.ruleId}-${index}`}>
          <p>{finding.message}</p>
          {(finding.claim || finding.lineNumber !== null) && (
            <p className="edi2-meta">
              {finding.claim && `Claim ${finding.claim}`}
              {finding.lineNumber !== null && ` · Line ${finding.lineNumber}`}
            </p>
          )}
          {finding.traceIds[0] && (
            <button type="button" className="edi2-source-link"
                    onClick={() => onTrace(finding.traceIds[0])}>
              View finding source
            </button>
          )}
        </div>
      ))}
      <p className="edi2-citation">{check.citation}</p>
    </article>
  );
}

export function ValidationSummary({ result, onTrace }: Props) {
  const [filter, setFilter] = useState<CheckStatus | 'all'>('all');
  const counts = Object.fromEntries(CHECK_FILTERS.map(({ status }) => [
    status, result.checks.filter((check) => check.status === status).length,
  ])) as Record<CheckStatus, number>;
  const checks = filter === 'all'
    ? result.checks : result.checks.filter((check) => check.status === filter);
  const groups = checks.reduce<Map<string, Edi2Check[]>>((grouped, check) => {
    const family = grouped.get(check.family) ?? [];
    family.push(check);
    grouped.set(check.family, family);
    return grouped;
  }, new Map());

  return (
    <section className="edi2-results" aria-labelledby="validation-summary-heading">
      <div className={`edi2-verdict edi2-verdict--${result.status}`}>
        <div>
          <p className="edi2-kicker">Structural validation</p>
          <h2 id="validation-summary-heading">{statusLabel(result.status)}</h2>
          <p><strong>{workflowLabel(result)}</strong> · {result.workflow?.confidence ?? 'unknown'} confidence</p>
        </div>
        <dl className="edi2-counts">
          <div><dt>Claims</dt><dd>{result.summary.claims}</dd></div>
          <div><dt>Lines</dt><dd>{result.summary.lines}</dd></div>
          <div><dt>Blockers</dt><dd>{result.summary.blockers}</dd></div>
          <div><dt>Advisories</dt><dd>{result.summary.advisories}</dd></div>
        </dl>
      </div>

      <div className="edi2-coverage" aria-label="Validation coverage">
        <strong>Standalone structural validation {result.coverage.standaloneValidation}</strong>
        <span>Outbound-source comparison not performed</span>
        <span>Original 837 comparison not performed</span>
      </div>

      {result.limitations.length > 0 && (
        <aside className="edi2-limitations" aria-label="Validation limitations">
          <strong>Coverage limitation</strong>
          {result.limitations.map((limitation) => <p key={limitation}>{limitation}</p>)}
        </aside>
      )}

      {result.parseError && (
        <div className="notice" role="alert">
          <strong>{result.parseError.message}</strong>
          Parsing stopped near character {result.parseError.offset}.
        </div>
      )}

      {result.checks.length > 0 && (
        <div className="edi2-checks">
          <div className="edi2-check-filters" aria-label="Structural check filters">
            <button type="button" aria-pressed={filter === 'all'}
                    onClick={() => setFilter('all')}>
              All {result.checks.length}
            </button>
            {CHECK_FILTERS.map(({ status, label }) => (
              <button key={status} type="button" aria-pressed={filter === status}
                      onClick={() => setFilter(status)}>
                {label} {counts[status]}
              </button>
            ))}
          </div>
          <div className="edi2-check-list">
            {[...groups].map(([family, familyChecks]) => (
              <section className="edi2-check-family" key={family}>
                <h3>{family} checks</h3>
                {familyChecks.map((check) => (
                  <Check check={check} onTrace={onTrace} key={check.id} />
                ))}
              </section>
            ))}
            {!checks.length && <p className="empty">No checks in this group.</p>}
          </div>
        </div>
      )}
    </section>
  );
}
