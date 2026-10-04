import { useEffect, useState } from 'react';
import { Calendar, Clock, Moon, Sun, UserCheck, PlayCircle, StopCircle, Lock } from 'lucide-react';
import { useAuth } from '../auth/useAuth';
import { fetchPunchStatus, fetchRecords, fetchSummary, recordLivePunch } from '../lib/endpoints';
import type { AttendanceRecord, AttendanceSummary, PunchStatusResponse } from '../types/api';
import { Alert, btn, EmptyState, PageHeader, StatCard, StatusBadge, Spinner } from '../components/ui';
import { currentMonth, formatDate, formatHours, formatTime, monthLabel, monthRange, recordState } from '../lib/format';
import { errorMessage } from '../lib/api';

export function WorkerView() {
  const { profile } = useAuth();
  const [month, setMonth] = useState(currentMonth());
  const [summary, setSummary] = useState<AttendanceSummary | null>(null);
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Estado del fichaje en vivo
  const [punchStatus, setPunchStatus] = useState<PunchStatusResponse | null>(null);
  const [punching, setPunching] = useState(false);
  const [punchSuccess, setPunchSuccess] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState<Date>(new Date());

  // Reloj en tiempo real
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const loadData = async (controller?: AbortController) => {
    setLoading(true);
    setError(null);
    try {
      const range = monthRange(month);
      const [sumRes, recRes, statusRes] = await Promise.all([
        fetchSummary(range, controller?.signal),
        fetchRecords(range, 0, 100, controller?.signal),
        fetchPunchStatus(controller?.signal),
      ]);
      setSummary(sumRes);
      setRecords(recRes);
      setPunchStatus(statusRes);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller);
    return () => controller.abort();
  }, [month]);

  const handlePunch = async (action: 'IN' | 'OUT') => {
    setPunching(true);
    setError(null);
    setPunchSuccess(null);
    try {
      await recordLivePunch(action);
      setPunchSuccess(
        action === 'IN'
          ? '¡Fichaje de entrada registrado correctamente! Tu jornada está activa.'
          : '¡Fichaje de salida registrado correctamente! Jornada completada y conciliada.'
      );
      await loadData();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPunching(false);
    }
  };

  const userStats = summary?.items?.[0] || {
    total_hours: 0,
    ordinary_hours: 0,
    night_hours: 0,
    holiday_hours: 0,
    excess_hours: 0,
    incidents_count: 0,
  };

  const isWorking = punchStatus?.status === 'IN_PROGRESS';

  return (
    <div className="space-y-6">
      <PageHeader
        title="Mi Portal de Asistencia"
        subtitle={`Consulta y registra tus jornadas de trabajo (${monthLabel(month)})`}
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
      {punchSuccess && <Alert tone="success">{punchSuccess}</Alert>}

      {/* Terminal de Fichaje Interactivo */}
      <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-md">
        <div className="bg-gradient-to-r from-slate-900 to-indigo-950 p-6 text-white sm:p-8">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="relative flex h-3 w-3">
                  <span
                    className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${
                      isWorking ? 'bg-emerald-400' : 'bg-slate-400'
                    }`}
                  />
                  <span
                    className={`relative inline-flex h-3 w-3 rounded-full ${
                      isWorking ? 'bg-emerald-500' : 'bg-slate-500'
                    }`}
                  />
                </span>
                <span className="text-xs font-semibold tracking-wider uppercase text-slate-300">
                  {isWorking ? 'En Jornada de Trabajo' : 'Fuera de Jornada'}
                </span>
              </div>
              <p className="mt-2 text-3xl font-extrabold tracking-tight tabular-nums sm:text-4xl">
                {currentTime.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </p>
              <p className="text-xs text-slate-400 mt-1">
                {currentTime.toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
              </p>
              {isWorking && punchStatus?.active_record?.punch_in && (
                <p className="mt-2 text-xs text-emerald-300">
                  Entrada registrada a las: <b>{formatTime(punchStatus.active_record.punch_in)}</b>
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                disabled={isWorking || punching}
                onClick={() => handlePunch('IN')}
                className={`${btn.primary} !bg-emerald-600 hover:!bg-emerald-500 !text-white px-6 py-3 font-semibold disabled:!bg-slate-700 disabled:!text-slate-400`}
              >
                {punching && !isWorking ? (
                  <Spinner className="size-5" />
                ) : (
                  <>
                    <PlayCircle className="size-5" /> Fichar Entrada
                  </>
                )}
              </button>

              <button
                type="button"
                disabled={!isWorking || punching}
                onClick={() => handlePunch('OUT')}
                className={`${btn.primary} !bg-rose-600 hover:!bg-rose-500 !text-white px-6 py-3 font-semibold disabled:!bg-slate-700 disabled:!text-slate-400`}
              >
                {punching && isWorking ? (
                  <Spinner className="size-5" />
                ) : (
                  <>
                    <StopCircle className="size-5" /> Fichar Salida
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 border-t border-slate-100 bg-slate-50/70 px-6 py-2.5 text-xs text-slate-500">
          <Lock className="size-3.5 text-slate-400 shrink-0" />
          <span>
            <b>Inmutabilidad de fichajes:</b> Una vez registrado, el trabajador no puede modificar las horas de entrada ni salida. Para cualquier corrección o rectificación, acude a tu supervisor.
          </span>
        </div>
      </div>

      {/* Tarjetas de Estadísticas Personales */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          label="Horas Ordinarias"
          value={formatHours(userStats.ordinary_hours)}
          icon={Sun}
          tone="indigo"
        />
        <StatCard
          label="Horas Nocturnas"
          value={formatHours(userStats.night_hours)}
          icon={Moon}
          tone="violet"
        />
        <StatCard
          label="Horas Festivas"
          value={formatHours(userStats.holiday_hours)}
          icon={Calendar}
          tone="emerald"
        />
        <StatCard
          label="Horas Extra / Exceso"
          value={formatHours(userStats.excess_hours)}
          icon={Clock}
          tone="amber"
        />
      </div>

      {/* Historial de Fichajes */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 bg-slate-50/50 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <UserCheck className="size-5 text-indigo-600" />
            <h2 className="text-sm font-semibold text-slate-800">
              Registros conciliados ({records.length})
            </h2>
          </div>
          <span className="text-xs text-slate-500">
            Código: <b className="text-slate-700">{profile?.employee_code || 'Asignado'}</b>
          </span>
        </div>

        {records.length === 0 && !loading ? (
          <div className="p-8">
            <EmptyState
              title="No hay registros en este mes"
              description="Asegúrate de haber seleccionado el mes en el que realizaste tus jornadas o utiliza los botones de fichaje para comenzar."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-semibold uppercase text-slate-500">
                <tr>
                  <th className="px-6 py-3">Fecha</th>
                  <th className="px-6 py-3">Entrada</th>
                  <th className="px-6 py-3">Salida</th>
                  <th className="px-6 py-3">Ordinarias</th>
                  <th className="px-6 py-3">Nocturnas</th>
                  <th className="px-6 py-3">Exceso</th>
                  <th className="px-6 py-3">Estado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {records.map((r) => {
                  const state = recordState(r);
                  return (
                    <tr key={r.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-6 py-4 font-medium text-slate-900">{formatDate(r.date)}</td>
                      <td className="px-6 py-4">{formatTime(r.punch_in)}</td>
                      <td className="px-6 py-4">{formatTime(r.punch_out)}</td>
                      <td className="px-6 py-4 tabular-nums">{formatHours(r.ordinary_hours)}</td>
                      <td className="px-6 py-4 tabular-nums">{formatHours(r.night_hours)}</td>
                      <td className="px-6 py-4 tabular-nums">
                        {r.excess_hours > 0 ? (
                          <span className="font-semibold text-amber-600">{formatHours(r.excess_hours)}</span>
                        ) : (
                          '0.00 h'
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge state={state} />
                        {r.incidents.length > 0 && r.incidents[0]?.reason && (
                          <p className="mt-1 text-xs text-slate-500 line-clamp-1 italic">
                            &quot;{r.incidents[0].reason}&quot;
                          </p>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
