/**
 * Section 03. Read-only, and read-only for a reason: these identifiers are
 * allocated from masterfile.json and never reused, so the batch cannot be
 * asked to take a different one.
 */
import type { Allocation } from '@/api/types';

function range(values: string[] | undefined) {
  if (!values?.length) return '—';
  return values.length === 1
    ? values[0]
    : `${values[0]}–${values[values.length - 1]}`;
}

export function IdentifierTiles({ alloc, error }: {
  alloc: Allocation | null;
  error: string | null;
}) {
  const tiles = [
    ['Next Batch', alloc && `Batch ${alloc.nextBatch}`],
    ['ISA13', alloc?.isa13],
    ['GS06', alloc?.gs06],
    ['BHT03 Range', alloc && range(alloc.bht03)],
  ] as const;

  return (
    <>
      <div className="tiles">
        {tiles.map(([label, value]) => (
          <div className="tile" key={label}>
            <div className="tile__label">{label}</div>
            <div
              className={`tile__value${value ? '' : ' tile__value--waiting'}`}
            >
              {value ?? 'reading masterfile…'}
            </div>
          </div>
        ))}
      </div>
      {error && (
        <div className="notice" role="status">
          <strong>The masterfile could not be read</strong>
          {error}
        </div>
      )}
    </>
  );
}
