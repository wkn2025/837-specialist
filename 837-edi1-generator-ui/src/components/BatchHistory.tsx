/**
 * Every run the masterfile records, newest first. Batch numbers are the
 * masterfile's own row numbers, so the number in this table is the number
 * the download route fetches.
 */
import { basename, downloadUrl } from '@/api/client';
import type { HistoryRow } from '@/api/types';

function when(ts: string) {
  return ts ? ts.slice(0, 10) : '—';
}

export function BatchHistory({ rows, error }: {
  rows: HistoryRow[] | null;
  error: string | null;
}) {
  return (
    <div className="page page--wide">
      <h2 style={{ fontSize: 20, fontWeight: 600, margin: '0 0 6px' }}>
        Batch History
      </h2>
      <p className="section-lede" style={{ marginBottom: 26 }}>
        Previously generated 837 test files for this environment.
      </p>

      {error && (
        <div className="notice" role="alert">
          <strong>History could not be read</strong>
          {error}
        </div>
      )}

      <div className="hist">
        <div className="hist__scroll">
          <div className="hist__row hist__row--head">
            <div>Batch</div>
            <div>Type</div>
            <div>Claims</div>
            <div>Output File</div>
            <div>Generated</div>
            <div>Status</div>
            <div />
          </div>

          {rows === null && !error && (
            <div className="empty">Reading the masterfile…</div>
          )}
          {rows?.length === 0 && (
            <div className="empty">
              No batches yet. Generate one and it lands here.
            </div>
          )}

          {rows?.map((row) => (
            <div className="hist__row" key={row.batchId}>
              <div className="hist__batch">B{row.batchId}</div>
              <div className="hist__type">837{row.type}</div>
              <div>{row.claims}</div>
              <div className="hist__file" title={row.output}>
                {basename(row.output)}
              </div>
              <div className="hist__date">{when(row.timestamp)}</div>
              {/* The masterfile records a run and its sha256; it records
                  no validator verdict, so this pill says what is actually
                  known rather than the prototype's "Validated". */}
              <div>
                <span className="pill" title={`sha256 ${row.sha256 ?? ''}`}>
                  Recorded
                </span>
              </div>
              <div>
                <a
                  className="btn-download"
                  href={downloadUrl(row.batchId, 'x12')}
                >
                  Download
                </a>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
