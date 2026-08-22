import { useRef, useState, type ChangeEvent } from 'react';
import type { Edi2ValidationResult } from '@/api/types';
import { AdjudicationClaims } from './AdjudicationClaims';
import { SourceTraceDrawer } from './SourceTraceDrawer';
import { ValidationSummary } from './ValidationSummary';
import {
  useEdi2Validation, type ValidateEdi2,
} from './useEdi2Validation';
import './edi2.css';

type Props = {
  validate?: ValidateEdi2;
  initialResult?: Edi2ValidationResult;
};

export function Edi2Validator({ validate, initialResult }: Props) {
  const { state, analyze } = useEdi2Validation(validate, initialResult);
  const [traceId, setTraceId] = useState<string | null>(null);
  const traceOpener = useRef<HTMLElement | null>(null);

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void analyze(file);
  }

  const result = state.phase === 'complete' ? state.result : null;
  const trace = traceId && result?.adjudication
    ? result.adjudication.traces[traceId] : undefined;

  function openTrace(id: string) {
    traceOpener.current = document.activeElement instanceof HTMLElement
      ? document.activeElement : null;
    setTraceId(id);
  }

  function closeTrace() {
    setTraceId(null);
    queueMicrotask(() => traceOpener.current?.focus());
  }

  return (
    <main className="page page--wide">
      <div className="section-head">
        <span className="section-num">EDI2</span>
        <h1>EDI2 Validator</h1>
      </div>
      <p className="section-lede">
        Upload an EDI2/X12 response to validate its structure and interpret
        the adjudication it transmits. The file is never rewritten.
      </p>

      <section className="card edi2-upload" aria-labelledby="edi2-upload-heading">
        <h2 id="edi2-upload-heading">Response file</h2>
        <label htmlFor="edi2-file">Choose EDI2 file</label>
        <input
          id="edi2-file"
          type="file"
          accept=".x12,.edi,.txt,application/octet-stream,text/plain"
          disabled={state.phase === 'loading'}
          onChange={choose}
        />
        <p className="caption">Maximum upload size: 10 MB.</p>
      </section>

      <div aria-live="polite">
        {state.phase === 'loading' && (
          <p className="working">Analyzing {state.file.name}…</p>
        )}
        {state.phase === 'error' && (
          <div className="notice" role="alert">
            <strong>Validation could not be completed</strong>
            {state.message}
          </div>
        )}
      </div>
      {result && (
        <>
          <p className="edi2-filename">Analyzed file: <strong>{result.file.filename}</strong></p>
          <ValidationSummary result={result} onTrace={openTrace} />
          <AdjudicationClaims result={result} onTrace={openTrace} />
        </>
      )}
      {trace && <SourceTraceDrawer trace={trace} onClose={closeTrace} />}
    </main>
  );
}
