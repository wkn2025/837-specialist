/** Section 02. The slider's ceiling is the handoff's 200. */
export function ClaimVolume({ value, onChange }: {
  value: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="card volume">
      <div className="volume__head">
        <label className="volume__label" htmlFor="claim-volume">
          Claims in this batch
        </label>
        <span className="volume__count">{value}</span>
      </div>
      <input
        id="claim-volume"
        type="range"
        min={1}
        max={200}
        value={value}
        onChange={(e) => onChange(Number(e.target.value) || 1)}
      />
      <div className="volume__scale"><span>1</span><span>200 max</span></div>
    </div>
  );
}
