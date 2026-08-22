/**
 * Section 06. Three states, in the handoff's own words: gray "Complete
 * Required Fields" while something is missing, blue "Generate File" when
 * the batch is valid, green "✓ File Generated" once it is on disk. Any
 * edit takes it back - a generated file describes the form as it was, not
 * as it is now.
 */
import type { GeneratedBatch } from '@/api/types';
import { basename, downloadUrl } from '@/api/client';

export function GenerateButton({
  canGenerate, generated, working, error, result, onGenerate,
}: {
  canGenerate: boolean;
  generated: boolean;
  working: boolean;
  error: string | null;
  result: GeneratedBatch | null;
  onGenerate: () => void;
}) {
  const label = generated
    ? '✓  File Generated'
    : working
      ? 'Generating…'
      : canGenerate ? 'Generate File' : 'Complete Required Fields';

  return (
    <div>
      <div className="generate">
        <button
          type="button"
          className={`btn-generate${generated ? ' is-done' : ''}`}
          disabled={!canGenerate || working || generated}
          onClick={onGenerate}
        >
          {label}
        </button>
        {generated && result && (
          <>
            <a
              className="btn-outline"
              href={downloadUrl(result.batchId, 'x12')}
            >
              Download .x12
            </a>
            <a
              className="btn-outline"
              href={downloadUrl(result.batchId, 'docx')}
            >
              Download Claim Detail Report (.docx)
            </a>
          </>
        )}
      </div>

      {generated && result && (
        <div className="caption">
          Batch {result.batchId} · <strong>{basename(result.x12FilePath)}</strong>
          {' · '}{basename(result.docxFilePath)}
          <br />
          Identifiers recorded in {basename(result.manifestPath)}; the batch
          keeps them for good.
        </div>
      )}

      {error && (
        <div className="notice" role="alert">
          <strong>The batch was not generated</strong>
          {error}
        </div>
      )}
    </div>
  );
}
