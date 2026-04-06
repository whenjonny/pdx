import { useState, useEffect } from 'react';
import { formatCountdown, isLocked } from '../../lib/format';

interface CountdownTimerProps {
  deadline: number;
  lockTime: number;
}

export default function CountdownTimer({ deadline, lockTime }: CountdownTimerProps) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const now = Math.floor(Date.now() / 1000);
  const expired = now >= deadline;
  const locked = isLocked(lockTime);

  if (expired) {
    return <span className="text-sm text-slate-500">Expired</span>;
  }

  return (
    <div className="text-sm">
      <span className={locked ? 'text-amber-400' : 'text-slate-400'}>
        {locked ? 'Locked - ' : ''}{formatCountdown(deadline)}
      </span>
    </div>
  );
}
