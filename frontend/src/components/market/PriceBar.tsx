interface PriceBarProps {
  priceYes: number;
  className?: string;
}

export default function PriceBar({ priceYes, className = '' }: PriceBarProps) {
  const yesPercent = Math.round(priceYes * 100);
  const noPercent = 100 - yesPercent;

  return (
    <div className={className}>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-emerald-400 font-medium">YES {yesPercent}%</span>
        <span className="text-rose-400 font-medium">NO {noPercent}%</span>
      </div>
      <div className="h-2 rounded-full overflow-hidden bg-slate-700 flex">
        <div
          className="bg-emerald-500 transition-all duration-500"
          style={{ width: `${yesPercent}%` }}
        />
        <div
          className="bg-rose-500 transition-all duration-500"
          style={{ width: `${noPercent}%` }}
        />
      </div>
    </div>
  );
}
