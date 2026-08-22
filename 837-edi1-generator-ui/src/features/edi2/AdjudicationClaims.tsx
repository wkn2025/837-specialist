import { useState } from 'react';
import type {
  Edi2Amounts, Edi2Amt, Edi2Cas, Edi2Claim, Edi2Line, Edi2Note,
  Edi2Reference, Edi2ValidationResult,
} from '@/api/types';
import { money, value } from './validationView';

type TraceHandler = (traceId: string) => void;

function TraceButton({ traceIds, label, onTrace }: {
  traceIds: string[];
  label: string;
  onTrace: TraceHandler;
}) {
  if (!traceIds[0]) return null;
  return (
    <button type="button" className="edi2-source-link"
            aria-label={`View source for ${label}`}
            onClick={() => onTrace(traceIds[0])}>
      Source
    </button>
  );
}

const AMOUNT_FIELDS: Array<[keyof Edi2Amounts, string]> = [
  ['billed', 'Billed amount'],
  ['allowed', 'Allowed amount'],
  ['repricedSavings', 'Repriced savings'],
  ['deductible', 'Deductible'],
  ['coinsurance', 'Coinsurance'],
  ['copay', 'Copay'],
  ['patientResponsibility', 'Patient responsibility'],
  ['notCovered', 'Not covered'],
  ['netPaid', 'Net paid'],
  ['coveragePercentage', 'Coverage percentage'],
];

function Amounts({ values, onTrace, tracePrefix }: {
  values: Edi2Amounts;
  onTrace: TraceHandler;
  tracePrefix?: string;
}) {
  return (
    <dl className="edi2-amounts">
      {AMOUNT_FIELDS.map(([key, label]) => {
        const observed = values[key];
        if (!observed || observed.presence === 'not-applicable') return null;
        const formatted = key === 'coveragePercentage'
          ? (observed.value === null ? 'Not transmitted' : `${observed.value}%`)
          : money(observed);
        return (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{formatted}</dd>
            <TraceButton traceIds={observed.traceIds}
                         label={`${tracePrefix ?? ''}${label.toLowerCase()}`}
                         onTrace={onTrace} />
          </div>
        );
      })}
    </dl>
  );
}

function CasRows({ rows, onTrace }: { rows: Edi2Cas[]; onTrace: TraceHandler }) {
  if (!rows.length) return null;
  return (
    <section className="edi2-raw-group">
      <h4>CAS adjustments</h4>
      <ul>{rows.map((row, index) => (
        <li key={`${row.groupCode}-${row.reasonCode}-${index}`}>
          <strong>CAS {row.groupCode} / {row.reasonCode}</strong>
          {row.amount !== null && ` · $${row.amount}`}
          {row.quantity !== null && ` · quantity ${row.quantity}`}
          <TraceButton traceIds={row.traceIds} label="CAS adjustment" onTrace={onTrace} />
        </li>
      ))}</ul>
    </section>
  );
}

function NoteRows({ rows, onTrace }: { rows: Edi2Note[]; onTrace: TraceHandler }) {
  if (!rows.length) return null;
  return (
    <section className="edi2-raw-group">
      <h4>NTE remarks</h4>
      <ul>{rows.map((row, index) => (
        <li key={`${row.qualifier}-${index}`}>
          {row.remarkCode && <strong>Remark code {row.remarkCode}</strong>}
          <span>{row.remarkCode ? ` · ${row.text}` : row.text}</span>
          <TraceButton traceIds={row.traceIds} label="NTE remark" onTrace={onTrace} />
        </li>
      ))}</ul>
    </section>
  );
}

function AmtRows({ rows, onTrace }: { rows: Edi2Amt[]; onTrace: TraceHandler }) {
  if (!rows.length) return null;
  return (
    <section className="edi2-raw-group">
      <h4>AMT values</h4>
      <ul>{rows.map((row, index) => (
        <li key={`${row.qualifier}-${index}`}>
          <strong>AMT {row.qualifier}</strong> · {row.amount === null ? 'Not transmitted' : `$${row.amount}`}
          <TraceButton traceIds={row.traceIds} label="AMT value" onTrace={onTrace} />
        </li>
      ))}</ul>
    </section>
  );
}

function RefRows({ rows, onTrace }: {
  rows: Edi2Reference[];
  onTrace: TraceHandler;
}) {
  if (!rows.length) return null;
  return (
    <section className="edi2-raw-group">
      <h4>REF references</h4>
      <ul>{rows.map((row, index) => (
        <li key={`${row.qualifier}-${index}`}>
          <strong>REF {row.qualifier}</strong> · {row.value}
          <TraceButton traceIds={row.traceIds} label="REF reference" onTrace={onTrace} />
        </li>
      ))}</ul>
    </section>
  );
}

function LineDetails({ line, workflow, onTrace }: {
  line: Edi2Line;
  workflow: 'I' | 'P' | 'unknown';
  onTrace: TraceHandler;
}) {
  const decision = line.benefitDecision.value;
  const status = workflow === 'P'
    ? (decision ? `${decision.code} — ${decision.label}` : 'Not transmitted')
    : `${value(line.financialOutcome)} (derived)`;
  return (
    <article className="edi2-line-detail">
      <h4>Line {line.lineNumber ?? '—'} details</h4>
      <p><strong>{workflow === 'P' ? 'Transmitted line decision' : 'Derived financial outcome'}:</strong> {status}</p>
      {workflow === 'P' && (
        <TraceButton traceIds={line.benefitDecision.traceIds}
                     label={`line ${line.lineNumber ?? 'unknown'} benefit decision`}
                     onTrace={onTrace} />
      )}
      <Amounts values={line.amounts} onTrace={onTrace}
               tracePrefix={`line ${line.lineNumber ?? 'unknown'} `} />
      <CasRows rows={line.cas} onTrace={onTrace} />
      <NoteRows rows={line.notes} onTrace={onTrace} />
      <AmtRows rows={line.amts} onTrace={onTrace} />
      <RefRows rows={line.references} onTrace={onTrace} />
      {line.reductionIndicators.length > 0 && (
        <div className="edi2-raw-group">
          <h4>Reduction / rework indicators</h4>
          {line.reductionIndicators.map((indicator, index) => (
            <p key={index}>
              {indicator.value}
              <TraceButton traceIds={indicator.traceIds}
                           label="line reduction indicator" onTrace={onTrace} />
            </p>
          ))}
        </div>
      )}
    </article>
  );
}

function ClaimDetails({ claim, workflow, onTrace }: {
  claim: Edi2Claim;
  workflow: 'I' | 'P' | 'unknown';
  onTrace: TraceHandler;
}) {
  const decision = claim.benefitDecision.value;
  return (
    <div className="edi2-claim__body">
      <dl className="edi2-identifiers">
        <div><dt>CCN / REF F8</dt><dd>{value(claim.identifiers.ccn)}</dd></div>
        <div><dt>UHAP claim ID / REF 9A</dt><dd>{value(claim.identifiers.uhapClaimId)}</dd></div>
        <div><dt>Client claim ID / REF D9</dt><dd>{value(claim.identifiers.clientClaimId)}</dd></div>
        <div><dt>Original UHAP ID / REF 9F</dt><dd>{value(claim.identifiers.originalUhapClaimId)}</dd></div>
        <div><dt>Frequency code</dt><dd>{value(claim.adjustment.frequencyCode)}</dd></div>
        <div><dt>CLM20 rework indicator</dt><dd>{value(claim.adjustment.clm20)}</dd></div>
      </dl>
      {decision && (
        <p className="edi2-decision">
          <strong>Claim benefit decision:</strong> {decision.code} — {decision.label}
          <TraceButton traceIds={claim.benefitDecision.traceIds}
                       label="claim benefit decision" onTrace={onTrace} />
        </p>
      )}
      <h3>Claim amounts</h3>
      <Amounts values={claim.amounts} onTrace={onTrace} />

      <div className="edi2-lines__scroll">
        <table className="edi2-lines">
          <caption>Service lines</caption>
          <thead><tr>
            <th>Line</th><th>Service</th><th>Date</th><th>Billed</th>
            <th>Allowed</th><th>{workflow === 'P' ? 'Decision' : 'Outcome'}</th>
          </tr></thead>
          <tbody>{claim.lines.map((line, index) => {
            const lineDecision = line.benefitDecision.value;
            return (
              <tr key={`${line.lineNumber}-${index}`}>
                <td>{line.lineNumber ?? '—'}</td>
                <td>{value(line.service.procedure)}</td>
                <td>{value(line.serviceDate)}</td>
                <td>{money(line.amounts.billed)}</td>
                <td>{money(line.amounts.allowed)}</td>
                <td>{workflow === 'P'
                  ? (lineDecision ? `${lineDecision.code} — ${lineDecision.label}` : 'Not transmitted')
                  : `${value(line.financialOutcome)} (derived)`}</td>
              </tr>
            );
          })}</tbody>
        </table>
      </div>
      {claim.lines.map((line, index) => (
        <LineDetails key={`${line.lineNumber}-${index}`} line={line}
                     workflow={workflow} onTrace={onTrace} />
      ))}

      <div className="edi2-raw-grid">
        <CasRows rows={claim.cas} onTrace={onTrace} />
        <NoteRows rows={claim.notes} onTrace={onTrace} />
        <AmtRows rows={claim.amts} onTrace={onTrace} />
        <RefRows rows={claim.references} onTrace={onTrace} />
      </div>
      {claim.otherPayers.length > 0 && (
        <section className="edi2-raw-group">
          <h4>COB / other payer values</h4>
          {claim.otherPayers.map((payer, index) => (
            <div key={index}>
              <dl className="edi2-identifiers">
                <div><dt>Responsibility sequence</dt><dd>{value(payer.responsibilitySequence)}</dd>
                  <TraceButton traceIds={payer.responsibilitySequence.traceIds}
                               label="COB responsibility sequence" onTrace={onTrace} /></div>
                <div><dt>Relationship code</dt><dd>{value(payer.relationshipCode)}</dd>
                  <TraceButton traceIds={payer.relationshipCode.traceIds}
                               label="COB relationship code" onTrace={onTrace} /></div>
                <div><dt>Subscriber group number</dt><dd>{value(payer.subscriberGroupNumber)}</dd>
                  <TraceButton traceIds={payer.subscriberGroupNumber.traceIds}
                               label="COB subscriber group number" onTrace={onTrace} /></div>
                <div><dt>Claim filing indicator</dt><dd>{value(payer.claimFilingIndicator)}</dd>
                  <TraceButton traceIds={payer.claimFilingIndicator.traceIds}
                               label="COB claim filing indicator" onTrace={onTrace} /></div>
                <div><dt>Other payer</dt><dd>{value(payer.payer.name)}</dd>
                  <TraceButton traceIds={payer.payer.name.traceIds}
                               label="other payer name" onTrace={onTrace} /></div>
                <div><dt>Payer ID</dt><dd>{value(payer.payer.identifier)}</dd>
                  <TraceButton traceIds={payer.payer.identifier.traceIds}
                               label="other payer identifier" onTrace={onTrace} /></div>
                <div><dt>Payer identifier qualifier</dt><dd>{value(payer.payer.identifierQualifier)}</dd>
                  <TraceButton traceIds={payer.payer.identifierQualifier.traceIds.length
                                       ? payer.payer.identifierQualifier.traceIds : payer.payer.traceIds}
                               label="other payer identifier qualifier" onTrace={onTrace} /></div>
                <div><dt>Other subscriber</dt><dd>{value(payer.subscriber.name)}</dd>
                  <TraceButton traceIds={payer.subscriber.name.traceIds}
                               label="other subscriber name" onTrace={onTrace} /></div>
                <div><dt>Subscriber ID</dt><dd>{value(payer.subscriber.identifier)}</dd>
                  <TraceButton traceIds={payer.subscriber.identifier.traceIds}
                               label="other subscriber identifier" onTrace={onTrace} /></div>
                <div><dt>Subscriber identifier qualifier</dt><dd>{value(payer.subscriber.identifierQualifier)}</dd>
                  <TraceButton traceIds={payer.subscriber.identifierQualifier.traceIds.length
                                       ? payer.subscriber.identifierQualifier.traceIds
                                       : payer.subscriber.traceIds}
                               label="other subscriber identifier qualifier" onTrace={onTrace} /></div>
              </dl>
              <RefRows rows={payer.references} onTrace={onTrace} />
              <p><code>{payer.sbr}</code>
                <TraceButton traceIds={payer.traceIds} label="other payer value" onTrace={onTrace} />
              </p>
            </div>
          ))}
        </section>
      )}
      {claim.reductionIndicators.length > 0 && (
        <section className="edi2-raw-group">
          <h4>Reduction / rework indicators</h4>
          {claim.reductionIndicators.map((indicator, index) => (
            <p key={index}>
              {indicator.value}
              <TraceButton traceIds={indicator.traceIds}
                           label="claim reduction indicator" onTrace={onTrace} />
            </p>
          ))}
        </section>
      )}
    </div>
  );
}

export function AdjudicationClaims({ result, onTrace }: {
  result: Edi2ValidationResult;
  onTrace: TraceHandler;
}) {
  const [open, setOpen] = useState<Set<number>>(new Set());
  const adjudication = result.adjudication;
  if (!adjudication) return null;
  const workflow = result.workflow?.workflow ?? 'unknown';

  function toggle(index: number) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(index)) next.delete(index); else next.add(index);
      return next;
    });
  }

  return (
    <section className="edi2-adjudication" aria-labelledby="adjudication-heading">
      <div className="edi2-section-title">
        <div>
          <p className="edi2-kicker">Adjudication interpretation</p>
          <h2 id="adjudication-heading">What this EDI2 communicates</h2>
        </div>
        <p>Transmitted values remain separate from derived interpretations.</p>
      </div>
      <div className="edi2-claims">
        {adjudication.claims.map((claim) => {
          const expanded = open.has(claim.claimIndex);
          const identifier = value(claim.claimIdentifier);
          return (
            <article className="edi2-claim" key={claim.claimIndex}>
              <button type="button" className="edi2-claim__head"
                      aria-expanded={expanded}
                      onClick={() => toggle(claim.claimIndex)}>
                <span>Claim {identifier}</span>
                <span>{expanded ? 'Collapse' : 'Inspect'}</span>
              </button>
              {expanded && (
                <ClaimDetails claim={claim} workflow={workflow} onTrace={onTrace} />
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
