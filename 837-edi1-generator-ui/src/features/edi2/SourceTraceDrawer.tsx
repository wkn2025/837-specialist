import { useEffect, useRef } from 'react';
import type { Edi2Trace } from '@/api/types';

export function SourceTraceDrawer({ trace, onClose }: {
  trace: Edi2Trace;
  onClose: () => void;
}) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => { close.current?.focus(); }, []);

  return (
    <div className="edi2-drawer-backdrop" role="presentation"
         onMouseDown={(event) => {
           if (event.target === event.currentTarget) onClose();
         }}>
      <aside className="edi2-drawer" role="dialog" aria-modal="true"
             aria-labelledby="source-trace-title"
             onKeyDown={(event) => {
               if (event.key === 'Escape') onClose();
             }}>
        <div className="edi2-drawer__head">
          <div>
            <p className="edi2-kicker">Source trace</p>
            <h2 id="source-trace-title">X12 source trace</h2>
          </div>
          <button ref={close} type="button" onClick={onClose}
                  aria-label="Close source trace">Close</button>
        </div>
        <dl className="edi2-trace-meta">
          <div><dt>Segment</dt><dd>{trace.segmentId}</dd></div>
          <div><dt>Element</dt><dd>{trace.elementPath ?? 'Whole segment'}</dd></div>
          <div><dt>Loop</dt><dd>{trace.loopId ?? 'Envelope'}</dd></div>
          <div><dt>Segment index</dt><dd>{trace.segmentIndex}</dd></div>
          {trace.claimIndex !== null && <div><dt>Claim</dt><dd>{trace.claimIndex}</dd></div>}
          {trace.lineNumber !== null && <div><dt>Line</dt><dd>{trace.lineNumber}</dd></div>}
        </dl>
        <div className="edi2-raw-segment">
          <span>Raw segment</span>
          <code>{trace.rawSegment}</code>
        </div>
      </aside>
    </div>
  );
}
