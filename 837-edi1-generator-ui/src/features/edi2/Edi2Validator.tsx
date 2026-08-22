import type { ChangeEvent } from 'react';
import type { Edi2ValidationResult } from '@/api/types';
import {
  useEdi2Validation, type ValidateEdi2,
} from './useEdi2Validation';

type Props = {
  validate?: ValidateEdi2;
  initialResult?: Edi2ValidationResult;
};

function workflowName(result: Edi2ValidationResult) {
  if (result.workflow?.workflow === 'I') return 'Institutional 837I';
  if (result.workflow?.workflow === 'P') return 'Professional 837P';
  return 'Workflow not determined';
}

export function Edi2Validator({ validate, initialResult }: Props) {
  const { state, analyze } = useEdi2Validation(validate, initialResult);

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void analyze(file);
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

      <section className="card volume" aria-labelledby="edi2-upload-heading">
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
        {state.phase === 'complete' && (
          <section aria-labelledby="edi2-workflow-heading">
            <h2 id="edi2-workflow-heading">{workflowName(state.result)}</h2>
            <p>{state.result.file.filename}</p>
          </section>
        )}
      </div>
    </main>
  );
}
