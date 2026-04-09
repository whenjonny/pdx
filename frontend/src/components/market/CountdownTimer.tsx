import { useState, useEffect } from 'react';
import { formatCountdown, isLocked } from '../../lib/format';
import { useChainTime } from '../../hooks/useChainTime';

interface CountdownTimerProps {
  deadline: number;
  lockTime: number;
}

export default function CountdownTimer({ deadline, lockTime }: CountdownTimerProps) {
  const [, setTick] = useState(0);
  const chainNow = useChainTime();

  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const now = chainNow;
  const expired = now >= deadline;
  const locked = isLocked(lockTime, now);

  if (expired) {
    return <span className="text-sm text-slate-500">Expired</span>;
  }

  return (
    <div className="text-sm">
      <span className={locked ? 'text-amber-400' : 'text-slate-400'}>
        {locked ? 'Locked - ' : ''}{formatCountdown(deadline, now)}
      </span>
    </div>
  );
}
