import type { ReactNode } from 'react';
import { AlertCircle, CheckCircle2, Clock, Info, Loader2, XCircle, type LucideIcon } from 'lucide-react';
import type { RecordState } from '../lib/format';

export function Spinner({ className = 'size-5' }: { className?: string }) {
  return <Loader2 className={`animate-spin ${className}`} aria-hidden="true" />;
}

export function FullPageSpinner({ label = 'Cargando…' }: { label?: string }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center gap-3 text-slate-500" role="status">
      <Spinner className="size-6" />
      <span>{label}</span>
    </div>
  );
}

type AlertTone = 'error' | 'success' | 'info' | 'warning';

const ALERT_STYLES: Record<AlertTone, { box: string; icon: LucideIcon }> = {
  error: { box: 'border-red-200 bg-red-50 text-red-800', icon: XCircle },
  success: { box: 'border-emerald-200 bg-emerald-50 text-emerald-800', icon: CheckCircle2 },
  info: { box: 'border-sky-200 bg-sky-50 text-sky-800', icon: Info },
  warning: { box: 'border-amber-200 bg-amber-50 text-amber-800', icon: AlertCircle },
};

export function Alert({ tone, children }: { tone: AlertTone; children: ReactNode }) {
  const { box, icon: Icon } = ALERT_STYLES[tone];
  return (
    <div
      className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-sm ${box}`}
      role={tone === 'error' ? 'alert' : 'status'}
    >
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const STAT_TONES = {
  indigo: 'bg-indigo-50 text-indigo-600',
  sky: 'bg-sky-50 text-sky-600',
  violet: 'bg-violet-50 text-violet-600',
  amber: 'bg-amber-50 text-amber-600',
  red: 'bg-red-50 text-red-600',
  emerald: 'bg-emerald-50 text-emerald-600',
  slate: 'bg-slate-100 text-slate-600',
} as const;

export function StatCard({
  label,
  value,
  icon: Icon,
  tone = 'indigo',
  hint,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  tone?: keyof typeof STAT_TONES;
  hint?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-slate-500">{label}</p>
        <span className={`rounded-lg p-2 ${STAT_TONES[tone]}`}>
          <Icon className="size-4" aria-hidden="true" />
        </span>
      </div>
      <p className="mt-3 text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

const STATE_BADGE: Record<RecordState, { label: string; cls: string; icon: LucideIcon }> = {
  OK: { label: 'Correcto', cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200', icon: CheckCircle2 },
  PENDING: { label: 'Pendiente', cls: 'bg-amber-50 text-amber-700 ring-amber-200', icon: Clock },
  APPROVED: { label: 'Aprobada', cls: 'bg-sky-50 text-sky-700 ring-sky-200', icon: CheckCircle2 },
  REJECTED: { label: 'Rechazada', cls: 'bg-red-50 text-red-700 ring-red-200', icon: XCircle },
};

export function StatusBadge({ state }: { state: RecordState }) {
  const { label, cls, icon: Icon } = STATE_BADGE[state];
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${cls}`}
    >
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
      <p className="font-medium text-slate-700">{title}</p>
      {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
    </div>
  );
}

export const btn = {
  primary:
    'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-indigo-600 px-4 text-sm font-medium text-white shadow-sm transition hover:bg-indigo-500 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60',
  secondary:
    'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-slate-300 bg-white px-4 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:cursor-not-allowed disabled:opacity-60',
  ghost:
    'inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-3 text-sm font-medium text-slate-600 transition hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-600',
} as const;

export const inputCls =
  'block min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30';

export const labelCls = 'mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500';
