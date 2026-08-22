/**
 * A numbered section head. The numbering is the handoff's own device: the
 * six steps are an order of operations, not a list of cards.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';

export function Section({ num, title, note, lede, children }: {
  num: string;
  title: string;
  note?: string;
  lede?: string;
  children: ReactNode;
}) {
  const head = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);

  useEffect(() => {
    const el = head.current;
    if (!el || seen) return;
    const io = new IntersectionObserver(([entry]) => {
      // Once only: a section that rises again on every scroll past is noise.
      if (entry.isIntersecting) { setSeen(true); io.disconnect(); }
    }, { rootMargin: '0px 0px -12% 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);

  return (
    <section className="section-body">
      <div
        ref={head}
        className={`section-head${lede ? ' section-head--tight' : ''}`
          + ` reveal${seen ? ' is-in' : ''}`}
      >
        <div className="section-num">{num}</div>
        <h2>{title}</h2>
        {note && <span className="section-note">{note}</span>}
      </div>
      {lede && <p className="section-lede">{lede}</p>}
      {children}
    </section>
  );
}
