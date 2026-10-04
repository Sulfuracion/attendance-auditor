import { useEffect, useState } from 'react';
import { Users, Clock, AlertOctagon, TrendingUp } from 'lucide-react';
import { fetchSummary } from '../lib/endpoints';
import type { AttendanceSummary } from '../types/api';
import { Alert, PageHeader, StatCard } from '../components/ui';
import { currentMonth, formatHours, monthLabel, monthRange } from '../lib/format';
import { errorMessage } from '../lib/api';
import { SupervisorView } from './SupervisorView';

export function AdminView() {
  const [month, setMonth] = useState(currentMonth());
  const [summary, setSummary] = useState<AttendanceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStats() {
      setError(null);
      try {
        const data = await fetchSummary(monthRange(month));
        setSummary(data);
      } catch (err) {
        setError(errorMessage(err));
      }
    }
    loadStats();
  }, [month]);

  return (
    <div className="space-y-8">
      <div>
        <PageHeader
          title="Panel Global de Administración"
          subtitle={`Métricas agregadas y supervisión general de la plantilla (${monthLabel(month)})`}
          actions={
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-500 uppercase">Mes:</span>
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="rounded-xl border border-slate-300 bg-white px-3 py-1.5 text-sm shadow-sm"
              />
            </div>
          }
        />

        {error && <Alert tone="error">{error}</Alert>}

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard
            label="Total Registros"
            value={String(summary?.total_records || 0)}
            icon={TrendingUp}
            tone="slate"
          />
          <StatCard
            label="Plantilla Activa"
            value={String(summary?.items?.length || 0)}
            icon={Users}
            tone="indigo"
          />
          <StatCard
            label="Horas Acumuladas"
            value={formatHours(summary?.total_hours || 0)}
            icon={Clock}
            tone="emerald"
          />
          <StatCard
            label="Incidencias Totales"
            value={String(summary?.total_incidents || 0)}
            icon={AlertOctagon}
            tone={summary && summary.total_incidents > 0 ? 'red' : 'emerald'}
          />
        </div>
      </div>

      {/* Como Administrador, incluye toda la operativa de auditoría y subidas */}
      <div className="border-t border-slate-200 pt-6">
        <SupervisorView />
      </div>
    </div>
  );
}
