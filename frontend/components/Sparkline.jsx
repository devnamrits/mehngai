export function Sparkline({ points, stroke = "#ffb020" }) {
  const values = (points ?? []).map((p) => p.value ?? p.price);
  if (values.length < 2) return <div className="sparkwrap" />;

  const w = 320;
  const h = 110;
  const pad = 6;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  const xy = (v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return [x, y];
  };

  const line = values.map((v, i) => xy(v, i).join(",")).join(" ");
  const [lx, ly] = xy(values[values.length - 1], values.length - 1);
  const area = `${pad},${h - pad} ${line} ${lx},${h - pad}`;

  return (
    <div className="sparkwrap">
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" aria-hidden="true">
        <polygon points={area} fill={stroke} opacity="0.07" />
        <polyline
          points={line}
          fill="none"
          stroke={stroke}
          strokeWidth="1.8"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle cx={lx} cy={ly} r="3.4" fill={stroke} />
        <line x1={pad} y1={h - pad} x2={w - pad} y2={h - pad} stroke="#26262a" strokeWidth="1" />
      </svg>
      <div className="spark-caption">
        {points.length} collections · low {min.toFixed(1)} · high {max.toFixed(1)}
      </div>
    </div>
  );
}
