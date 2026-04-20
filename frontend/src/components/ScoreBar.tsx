interface ScoreBarProps {
  score: number;
  max?: number;
  label?: string;
  showValue?: boolean;
}

export default function ScoreBar({ score, max = 100, label, showValue = true }: ScoreBarProps) {
  const pct = Math.min((score / max) * 100, 100);
  const segments = Array.from({ length: 10 }, (_, i) => i * 10 < pct);

  const activeColor =
    pct >= 75 ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)]' :
      pct >= 50 ? 'bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.3)]' :
        'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.3)]';

  return (
    <div className="flex flex-col gap-1.5 group">
      <div className="flex justify-between items-baseline">
        {label && (
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 group-hover:text-indigo-600 transition-colors duration-300">
            {label}
          </span>
        )}
        {showValue && (
          <div className="flex items-baseline gap-1">
            <span className="text-sm font-black text-slate-900 tracking-tighter tabular-nums">{score.toFixed(1)}</span>
            <span className="text-[9px] font-black text-slate-400 uppercase italic">/ {max}</span>
          </div>
        )}
      </div>

      <div className="flex gap-1.5 items-center">
        {segments.map((active, i) => (
          <div
            key={i}
            className={`flex-1 h-3 rounded-[3px] transition-all duration-700 ease-out ${active
              ? `${activeColor} border-t border-white/20`
              : 'bg-slate-100 border border-slate-200/50'
              }`}
            style={{
              transitionDelay: `${i * 30}ms`,
              transform: active ? 'scaleY(1)' : 'scaleY(0.8)'
            }}
          />
        ))}
        <div className="ml-2 w-1.5 h-1.5 rounded-full bg-slate-200 animate-pulse" />
      </div>
    </div>
  );
}
