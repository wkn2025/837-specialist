/**
 * The 837 Claims EDI Toolkit shell.
 *
 * Two of its three tabs are the generator: six numbered sections and the
 * batch history, both owned by the generator UI. The third is main's EDI2
 * Validator, mounted here unchanged - it reads an adjudication return and
 * never touches the generator's state.
 */
import { useState } from 'react';
import { Edi2Validator } from '@/features/edi2/Edi2Validator';
import '@/styles/app.css';
import { downloadUrl, generate } from './api/client.js';
import { useBatchForm } from './hooks/useBatchForm.js';
import { useBatchHistory } from './hooks/useBatchHistory.js';
import { useMasterfile } from './hooks/useMasterfile.js';
import { BatchHistory } from './components/BatchHistory.js';
import { ClaimCard } from './components/ClaimCard.js';
import { ClaimVolume } from './components/ClaimVolume.js';
import { GenerateButton } from './components/GenerateButton.js';
import { IdentifierTiles } from './components/IdentifierTiles.js';
import { IdentityCards } from './components/IdentityCards.js';
import { SectionHeading } from './components/SectionHeading.js';
import { TransactionTypeCard, TYPES } from './components/TransactionTypeCard.js';
import { mono, sectionGap } from './styles/ui.js';
import logo from '../assets/logo.jpeg';

/** The bridge's own ceiling; the generator's is higher (masterfile.MAX_CLAIMS). */
const MAX_CLAIMS = 200;

type View = 'gen' | 'hist' | 'edi2';

export default function App() {
  const [view, setView] = useState<View>('gen');
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const form = useBatchForm({ initialType: 'I', initialClaims: 3 });
  const masterfile = useMasterfile(form.form.type, form.form.claims);
  const history = useBatchHistory();

  const onGenerate = async () => {
    setBusy(true);
    setFailure(null);
    try {
      const result = await generate(
        form.form.type, form.form.claims, form.toDocument(),
      );
      form.markGenerated(result);
      await history.refresh();
      masterfile.refresh();
    } catch (e: unknown) {
      setFailure(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const tab = (active: boolean) => ({
    border: 'none',
    borderRadius: 0,
    background: 'transparent',
    fontFamily: 'inherit',
    padding: '14px 18px',
    fontSize: 13.5,
    fontWeight: 600,
    cursor: 'pointer',
    color: active ? '#26408f' : '#8892a6',
    borderBottom: `2.5px solid ${active ? '#26408f' : 'transparent'}`,
  } as const);

  return (
    <div style={{ minHeight: '100vh' }}>
      <header style={{
        background: '#26408f',
        color: '#fff',
        padding: '26px 52px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: '0 2px 12px rgba(38,64,143,.25)',
      }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <img
            src={logo}
            alt=""
            width={48}
            height={48}
            style={{ width: 48, height: 48, borderRadius: 6, objectFit: 'cover' }}
          />
          <div>
            <div style={{
              fontFamily: mono,
              fontSize: 11,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: '#c7cd3d',
              fontWeight: 600,
            }}
            >
              UHCG Claims EDI Toolkit
            </div>
            <div style={{
              fontSize: 23, fontWeight: 600, letterSpacing: '-.01em', marginTop: 2,
            }}
            >
              837 Claims EDI Toolkit
            </div>
          </div>
        </div>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          background: 'rgba(255,255,255,.08)',
          padding: '7px 14px',
          borderRadius: 20,
        }}
        >
          <div style={{
            width: 7, height: 7, borderRadius: '50%', background: '#c7cd3d',
          }}
          />
          <span style={{
            fontFamily: mono,
            fontSize: 11.5,
            color: 'rgba(255,255,255,.9)',
            letterSpacing: '.05em',
          }}
          >
            QA / SANDBOX ENVIRONMENT
          </span>
        </div>
      </header>

      <nav role="tablist" style={{
        display: 'flex',
        gap: 4,
        padding: '0 52px',
        background: '#fff',
        borderBottom: '1px solid #dde1ea',
      }}
      >
        <button type="button" role="tab" aria-selected={view === 'gen'} style={tab(view === 'gen')} onClick={() => setView('gen')}>
          New Batch
        </button>
        <button type="button" role="tab" aria-selected={view === 'hist'} style={tab(view === 'hist')} onClick={() => setView('hist')}>
          Batch History
        </button>
        <button type="button" role="tab" aria-selected={view === 'edi2'} style={tab(view === 'edi2')} onClick={() => setView('edi2')}>
          EDI2 Validator
        </button>
      </nav>

      {view === 'edi2' ? (
        <Edi2Validator />
      ) : view === 'hist' ? (
        <BatchHistory
          rows={history.rows}
          loading={history.loading}
          error={history.error}
        />
      ) : (
        <main style={{ maxWidth: 900, margin: '0 auto', padding: '44px 24px 100px' }}>
          <SectionHeading number="01" title="Transaction Type" />
          <div style={{
            display: 'flex', gap: 20, flexWrap: 'wrap', marginBottom: sectionGap,
          }}
          >
            {TYPES.map((info) => (
              <TransactionTypeCard
                key={info.id}
                info={info}
                selected={form.form.type === info.id}
                onSelect={form.setType}
              />
            ))}
          </div>

          <SectionHeading number="02" title="Claim Volume" />
          <div style={{ marginBottom: sectionGap }}>
            <ClaimVolume
              claims={form.form.claims}
              max={MAX_CLAIMS}
              onChange={form.setClaims}
            />
          </div>

          <SectionHeading
            number="03"
            title="Allocated Identifiers"
            note="never reused — pulled from masterfile.json"
          />
          <div style={{ marginBottom: sectionGap }}>
            <IdentifierTiles preview={masterfile.preview} error={masterfile.error} />
          </div>

          <SectionHeading
            number="04"
            title="Personal & Provider Info"
            note="shared across the whole batch"
          />
          <div style={{ marginBottom: sectionGap }}>
            <IdentityCards
              identity={form.form.identity}
              editedGroups={form.editedGroups}
              onChange={form.updateIdentity}
            />
          </div>

          <SectionHeading number="05" title="Claim Data" />
          <p style={{ fontSize: 13.5, color: '#5b6478', margin: '0 0 20px' }}>
            Click a claim to expand and edit its diagnosis and service lines.
          </p>
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 14, marginBottom: sectionGap,
          }}
          >
            {form.form.claimDocs.map((claim) => (
              <ClaimCard
                key={claim.n}
                type={form.form.type}
                claim={claim}
                total={form.form.claims}
                expanded={form.form.expanded.has(claim.n)}
                diagnosisEdited={form.editedGroups.has(`diagnosis:${claim.n}`)}
                onToggle={form.toggleExpanded}
                onDiagnosis={form.updateDiagnosis}
                onLine={form.updateLine}
                onAddLine={form.addLine}
                onRemoveLine={form.removeLine}
              />
            ))}
            {form.loading && (
              <div style={{ fontSize: 13, color: '#5b6478' }}>
                Reading the seed…
              </div>
            )}
            {form.error && (
              <div style={{ fontSize: 13, color: '#a1341f' }}>{form.error}</div>
            )}
          </div>

          <SectionHeading number="06" title="Generate & Review" />
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <GenerateButton
              canGenerate={form.canGenerate}
              generated={form.form.generated}
              busy={busy}
              onGenerate={() => { void onGenerate(); }}
            />
            {form.form.generated && form.result && (
              <a
                href={downloadUrl(form.result.batchId, 'docx')}
                style={{
                  padding: '13px 24px',
                  borderRadius: 7,
                  fontSize: 14.5,
                  fontWeight: 600,
                  border: '1.5px solid #26408f',
                  background: '#fff',
                  color: '#26408f',
                  fontFamily: mono,
                  textDecoration: 'none',
                }}
              >
                Download Claim Detail Report (.docx)
              </a>
            )}
          </div>
          {failure && (
            <p style={{ marginTop: 14, fontSize: 13, color: '#a1341f' }}>
              {`The generator refused this batch: ${failure}`}
            </p>
          )}
          {form.result && form.form.generated && (
            <p style={{
              marginTop: 14, fontSize: 12.5, color: '#5b6478', fontFamily: mono,
            }}
            >
              {`${form.result.x12} · ISA13 ${form.result.isa13} · `}
              {`CLM01 ${form.result.clm01[0]}..${form.result.clm01[1]}`}
            </p>
          )}
        </main>
      )}
    </div>
  );
}
