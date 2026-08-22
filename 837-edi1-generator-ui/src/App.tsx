/**
 * The generator's two views.
 *
 * The form never builds an .x12 and never decides what a valid claim is.
 * It collects a declaration, hands it to the bridge, and shows what the
 * generator says back - including its refusals, in the generator's own
 * words.
 */
import { useState } from 'react';
import { generateBatch } from '@/api/client';
import type { GeneratedBatch } from '@/api/types';
import { BatchHistory } from '@/components/BatchHistory';
import { ClaimCard } from '@/components/ClaimCard';
import { ClaimVolume } from '@/components/ClaimVolume';
import { GenerateButton } from '@/components/GenerateButton';
import { IdentifierTiles } from '@/components/IdentifierTiles';
import { IdentityCards } from '@/components/IdentityCards';
import { Section } from '@/components/Section';
import { TransactionTypeCards } from '@/components/TransactionTypeCard';
import { Edi2Validator } from '@/features/edi2/Edi2Validator';
import { useBatchForm } from '@/hooks/useBatchForm';
import { useBatchHistory } from '@/hooks/useBatchHistory';
import { useMasterfile } from '@/hooks/useMasterfile';
import '@/styles/app.css';

export default function App() {
  const [view, setView] = useState<'gen' | 'hist' | 'edi2'>('gen');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const f = useBatchForm();
  const { alloc, error: allocError } = useMasterfile(f.form.type, f.form.claims);
  const history = useBatchHistory();

  async function generate() {
    setWorking(true);
    setError(null);
    try {
      const result: GeneratedBatch = await generateBatch(
        f.form.type, f.form.claims, f.toDocument());
      f.markGenerated(result);
      // Re-read the masterfile rather than prepending a row locally: the
      // table should only ever show runs the file itself records.
      await history.refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }

  return (
    <>
      <header className="header">
        <div className="header__brand">
          <img className="header__logo" src="/logo.png" alt="" width={48}
               height={48} />
          <div>
            <div className="header__eyebrow">UHCG Claims EDI Toolkit</div>
            <div className="header__title">837 Claims EDI Toolkit</div>
          </div>
        </div>
        <div className="env">
          <div className="env__dot" aria-hidden="true" />
          <span>QA / SANDBOX ENVIRONMENT</span>
        </div>
      </header>

      <div className="tabs" role="tablist">
        <button type="button" role="tab" className="tab"
                aria-selected={view === 'gen'} onClick={() => setView('gen')}>
          New Batch
        </button>
        <button type="button" role="tab" className="tab"
                aria-selected={view === 'hist'} onClick={() => setView('hist')}>
          Batch History
        </button>
        <button type="button" role="tab" className="tab"
                aria-selected={view === 'edi2'} onClick={() => setView('edi2')}>
          EDI2 Validator
        </button>
      </div>

      {view === 'edi2' ? (
        <Edi2Validator />
      ) : view === 'hist' ? (
        <BatchHistory rows={history.rows} error={history.error} />
      ) : (
        <main className="page">
          <Section num="01" title="Transaction Type">
            <TransactionTypeCards value={f.form.type} onChange={f.setType} />
          </Section>

          <Section num="02" title="Claim Volume">
            <ClaimVolume value={f.form.claims} onChange={f.setClaims} />
          </Section>

          <Section
            num="03"
            title="Allocated Identifiers"
            note="never reused — pulled from masterfile.json"
          >
            <IdentifierTiles alloc={alloc} error={allocError} />
          </Section>

          <Section
            num="04"
            title="Personal & Provider Info"
            note="shared across the whole batch"
          >
            {f.error ? (
              <div className="notice" role="alert">
                <strong>The seed defaults could not be read</strong>
                {f.error}
              </div>
            ) : !f.loaded ? (
              <p className="working">Reading the seed…</p>
            ) : (
              <IdentityCards
                identity={f.form.identity}
                type={f.form.type}
                editedGroups={f.editedGroups}
                onChange={f.updateIdentity}
              />
            )}
          </Section>

          <Section
            num="05"
            title="Claim Data"
            lede="Click a claim to expand and edit its diagnosis and service lines."
          >
            <div className="claims">
              {f.form.claimDocs.map((claim) => (
                <ClaimCard
                  key={claim.n}
                  claim={claim}
                  total={f.form.claims}
                  type={f.form.type}
                  expanded={f.form.expanded.has(claim.n)}
                  diagnosisEdited={!!f.editedClaims[claim.n]?.diagnosis}
                  onToggle={() => f.toggleExpanded(claim.n)}
                  onDiagnosis={(v) => f.updateDiagnosis(claim.n, v)}
                  onLine={(i, field, v) => f.updateLine(claim.n, i, field, v)}
                  onAddLine={() => f.addLine(claim.n)}
                  onRemoveLine={(i) => f.removeLine(claim.n, i)}
                />
              ))}
            </div>
          </Section>

          <Section num="06" title="Generate & Review">
            <GenerateButton
              canGenerate={f.canGenerate}
              generated={f.form.generated}
              working={working}
              error={error}
              result={f.form.result}
              onGenerate={generate}
            />
          </Section>
        </main>
      )}
    </>
  );
}
