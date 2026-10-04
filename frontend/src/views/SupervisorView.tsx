import { useEffect, useState, useRef } from 'react';
import { 
  UploadCloud, Download, Filter, 
  MessageSquarePlus, RefreshCw, X, Edit3, ShieldAlert, FileSpreadsheet,
  AlertTriangle, CheckCircle2, ArrowRight
} from 'lucide-react';
import { 
  fetchRecords, justifyIncident, exportReport, 
  uploadAttendanceFile, updateAttendanceRecord, downloadBiometricTemplate,
  previewExcelModifications, applyBulkModifications
} from '../lib/endpoints';
import type { AttendanceRecord, UploadResult, BulkDiffPreview } from '../types/api';
import { Alert, btn, EmptyState, inputCls, labelCls, PageHeader, Spinner, StatusBadge } from '../components/ui';
import { checkAttendanceFile } from '../lib/fileCheck';
import { formatDate, formatHours, formatTime, recordState } from '../lib/format';
import { errorMessage } from '../lib/api';

export function SupervisorView() {
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filtros
  const [empFilter, setEmpFilter] = useState('');
  const [onlyIncidents, setOnlyIncidents] = useState(false);

  // Ingesta / Subida
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Modal de Previsualización y Confirmación de Cambios Masivos
  const [diffPreview, setDiffPreview] = useState<BulkDiffPreview | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [bulkAuditReason, setBulkAuditReason] = useState('Actualización masiva de fichajes desde Excel');
  const [applyingBulk, setApplyingBulk] = useState(false);

  // Modal de Justificación de Incidencia
  const [selectedRecord, setSelectedRecord] = useState<AttendanceRecord | null>(null);
  const [justifyReason, setJustifyReason] = useState('');
  const [justifyAction, setJustifyAction] = useState<'APPROVED' | 'REJECTED'>('APPROVED');
  const [justifying, setJustifying] = useState(false);

  // Modal de Edición de Fichaje (Supervisor / Admin)
  const [editingRecord, setEditingRecord] = useState<AttendanceRecord | null>(null);
  const [editPunchIn, setEditPunchIn] = useState('');
  const [editPunchOut, setEditPunchOut] = useState('');
  const [editReason, setEditReason] = useState('');
  const [editing, setEditing] = useState(false);

  const loadRecords = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRecords({
        employee_code: empFilter.trim() || undefined,
        only_incidents: onlyIncidents,
      }, 0, 150);
      setRecords(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRecords();
  }, [empFilter, onlyIncidents]);

  const handleFileUpload = async (file: File) => {
    const check = await checkAttendanceFile(file);
    if (!check.ok) {
      setError(check.error);
      return;
    }
    setError(null);
    setUploading(true);
    setUploadProgress(0);

    try {
      // 1. Ejecutar previsualización para comparar con los datos existentes
      const { promise: previewPromise } = previewExcelModifications(
        file,
        (p) => setUploadProgress(Math.round((p.loaded / p.total) * 100))
      );
      const preview = await previewPromise;

      // Si detectamos cambios sobre registros existentes o nuevos, solicitar confirmación con diff detallado
      if (preview.changes_count > 0) {
        setDiffPreview(preview);
        setPendingFile(file);
        setUploading(false);
        return;
      }

      // Si no hay modificaciones ni registros nuevos, procesar normalmente por ingesta regular
      await executeStandardUpload(file);
    } catch (err) {
      setError(errorMessage(err));
      setUploading(false);
    }
  };

  const executeStandardUpload = async (file: File) => {
    setUploading(true);
    setUploadProgress(0);
    const { promise } = uploadAttendanceFile(
      file,
      (p) => setUploadProgress(Math.round((p.loaded / p.total) * 100)),
      () => setUploadProgress(100)
    );

    try {
      const res = await promise;
      setUploadResult(res);
      loadRecords();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUploading(false);
      setPendingFile(null);
    }
  };

  const confirmApplyChanges = async () => {
    if (!diffPreview) return;
    setApplyingBulk(true);
    try {
      await applyBulkModifications({
        changes: diffPreview.changes,
        audit_reason: bulkAuditReason.trim() || 'Modificación masiva desde archivo Excel',
      });
      setDiffPreview(null);
      setPendingFile(null);
      loadRecords();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setApplyingBulk(false);
    }
  };

  const handleExport = async () => {
    try {
      const { blob, filename } = await exportReport({
        employee_code: empFilter.trim() || undefined,
      });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'auditoria_asistencia.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const handleDownloadTemplate = async () => {
    try {
      const { blob, filename } = await downloadBiometricTemplate();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'plantilla_fichajes_biometricos.xlsx';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  const submitJustification = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRecord) return;
    setJustifying(true);
    try {
      await justifyIncident(selectedRecord.id, {
        reason: justifyReason,
        status: justifyAction,
      });
      setSelectedRecord(null);
      setJustifyReason('');
      loadRecords();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setJustifying(false);
    }
  };

  const openEditModal = (r: AttendanceRecord) => {
    setEditingRecord(r);
    // Convert ISO datetime to datetime-local format (YYYY-MM-DDTHH:mm)
    const toInputFormat = (isoStr: string | null) => {
      if (!isoStr) return '';
      const d = new Date(isoStr);
      return isNaN(d.getTime()) ? '' : d.toISOString().slice(0, 16);
    };
    setEditPunchIn(toInputFormat(r.punch_in));
    setEditPunchOut(toInputFormat(r.punch_out));
    setEditReason('');
  };

  const submitEdit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingRecord) return;
    setEditing(true);
    try {
      await updateAttendanceRecord(editingRecord.id, {
        punch_in: new Date(editPunchIn).toISOString(),
        punch_out: new Date(editPunchOut).toISOString(),
        reason: editReason.trim() || undefined,
      });
      setEditingRecord(null);
      loadRecords();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setEditing(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Auditoría de Fichajes y Conciliación"
        subtitle="Ingesta de partes horarios, control de excesos e incidencias laborales"
        actions={
          <div className="flex flex-wrap gap-2">
            <button onClick={loadRecords} className={btn.secondary}>
              <RefreshCw className="size-4" /> Recargar
            </button>
            <button onClick={handleDownloadTemplate} className={btn.secondary}>
              <FileSpreadsheet className="size-4 text-emerald-600" /> Descargar Plantilla Excel
            </button>
            <button onClick={handleExport} className={btn.primary}>
              <Download className="size-4" /> Exportar a Excel
            </button>
          </div>
        }
      />

      {error && <Alert tone="error">{error}</Alert>}

      {/* Zona Drag & Drop de Subida */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Ingesta de Fichajes Biométricos (CSV / XLSX)</h3>
            <p className="text-xs text-slate-500">Carga masiva de eventos de fichaje para auditoría y conciliación automática</p>
          </div>
          <button
            onClick={handleDownloadTemplate}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-800 hover:underline"
          >
            <FileSpreadsheet className="size-4 text-emerald-600" /> Descargar Plantilla de Ejemplo (.xlsx)
          </button>
        </div>
        <div
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (e.dataTransfer.files[0]) handleFileUpload(e.dataTransfer.files[0]);
          }}
          onClick={() => fileInputRef.current?.click()}
          className="flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-indigo-200 bg-indigo-50/40 p-6 text-center cursor-pointer hover:bg-indigo-50/80 transition"
        >
          <UploadCloud className="size-10 text-indigo-600 mb-2" />
          <p className="text-sm font-medium text-slate-700">
            Arrastra tu archivo aquí o <span className="text-indigo-600 underline">haz clic para examinar</span>
          </p>
          <p className="text-xs text-slate-400 mt-1">Formatos admitidos: CSV delimitado, XLSX nativo (máx. 10 MB)</p>
          <input
            type="file"
            ref={fileInputRef}
            onChange={(e) => e.target.files?.[0] && handleFileUpload(e.target.files[0])}
            accept=".csv,.xlsx"
            className="hidden"
          />
        </div>

        {uploading && (
          <div className="mt-4 space-y-1">
            <div className="flex justify-between text-xs text-slate-600">
              <span>Procesando y normalizando vectorialmente...</span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full bg-indigo-600 transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {uploadResult && (
          <div className="mt-4 rounded-xl bg-emerald-50 border border-emerald-200 p-4 text-sm text-emerald-800 flex items-start justify-between">
            <div>
              <p className="font-semibold">¡Archivo procesado con éxito!</p>
              <ul className="mt-1 text-xs space-y-0.5 list-disc list-inside">
                <li>Filas procesadas: {uploadResult.total_rows_processed}</li>
                <li>Jornadas conciliadas: {uploadResult.reconciled_shifts}</li>
                <li>Incidencias identificadas: {uploadResult.incidents_detected}</li>
              </ul>
            </div>
            <button onClick={() => setUploadResult(null)} className="text-emerald-600 hover:text-emerald-800">
              <X className="size-4" />
            </button>
          </div>
        )}
      </div>

      {/* Barra de Filtros */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="size-4 text-slate-400" />
            <input
              type="text"
              placeholder="Código empleado (ej. EMP001)"
              value={empFilter}
              onChange={(e) => setEmpFilter(e.target.value)}
              className="rounded-xl border border-slate-300 px-3 py-1.5 text-sm"
            />
          </div>
          <label className="flex items-center gap-2 text-sm text-slate-600 cursor-pointer">
            <input
              type="checkbox"
              checked={onlyIncidents}
              onChange={(e) => setOnlyIncidents(e.target.checked)}
              className="rounded text-indigo-600 focus:ring-indigo-500"
            />
            Solo con incidencias
          </label>
        </div>
        <span className="text-xs text-slate-500">Mostrando {records.length} registros</span>
      </div>

      {/* Tabla de Fichajes y Gestión de Incidencias / Edición */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {records.length === 0 && !loading ? (
          <div className="p-8">
            <EmptyState
              title="No hay registros que coincidan con la búsqueda"
              description="Ajusta los filtros o sube un archivo nuevo para reconciliar fichajes."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-xs font-semibold uppercase text-slate-500">
                <tr>
                  <th className="px-6 py-3">Empleado</th>
                  <th className="px-6 py-3">Fecha</th>
                  <th className="px-6 py-3">Entrada</th>
                  <th className="px-6 py-3">Salida</th>
                  <th className="px-6 py-3">Ordinarias</th>
                  <th className="px-6 py-3">Nocturnas</th>
                  <th className="px-6 py-3">Exceso</th>
                  <th className="px-6 py-3">Estado</th>
                  <th className="px-6 py-3 text-right">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {records.map((r) => {
                  const state = recordState(r);
                  return (
                    <tr key={r.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="px-6 py-4 font-semibold text-slate-900">{r.employee_code}</td>
                      <td className="px-6 py-4">{formatDate(r.date)}</td>
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
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openEditModal(r)}
                            title="Rectificar horas (Supervisor/Admin)"
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 transition"
                          >
                            <Edit3 className="size-3.5 text-slate-500" /> Editar
                          </button>
                          {r.has_incident && (
                            <button
                              onClick={() => setSelectedRecord(r)}
                              title="Justificar incidencia formalmente"
                              className="inline-flex items-center gap-1 rounded-lg bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 transition"
                            >
                              <MessageSquarePlus className="size-3.5" /> Justificar
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modal de Rectificación de Fichaje (Supervisor / Admin) */}
      {editingRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2">
                <Edit3 className="size-5 text-indigo-600" />
                <h3 className="text-lg font-bold text-slate-900">Rectificar Fichaje</h3>
              </div>
              <button onClick={() => setEditingRecord(null)} className="text-slate-400 hover:text-slate-600">
                <X className="size-5" />
              </button>
            </div>

            <div className="rounded-xl bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800 flex items-start gap-2">
              <ShieldAlert className="size-4 shrink-0 mt-0.5" />
              <span>
                Esta modificación recalcula automáticamente las horas ordinarias, nocturnas, festivas y excesos laborales bajo la firma del supervisor.
              </span>
            </div>

            <form onSubmit={submitEdit} className="space-y-4">
              <div>
                <label className={labelCls}>Empleado</label>
                <input
                  type="text"
                  disabled
                  value={editingRecord.employee_code}
                  className={`${inputCls} bg-slate-100 cursor-not-allowed`}
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Hora de Entrada</label>
                  <input
                    type="datetime-local"
                    required
                    value={editPunchIn}
                    onChange={(e) => setEditPunchIn(e.target.value)}
                    className={inputCls}
                  />
                </div>
                <div>
                  <label className={labelCls}>Hora de Salida</label>
                  <input
                    type="datetime-local"
                    required
                    value={editPunchOut}
                    onChange={(e) => setEditPunchOut(e.target.value)}
                    className={inputCls}
                  />
                </div>
              </div>

              <div>
                <label className={labelCls}>Motivo de la Corrección (Auditoría)</label>
                <textarea
                  rows={2}
                  value={editReason}
                  onChange={(e) => setEditReason(e.target.value)}
                  placeholder="Ej. Rectificación por fallo en reloj biométrico a la salida..."
                  className={`${inputCls} py-2`}
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setEditingRecord(null)}
                  className={btn.secondary}
                >
                  Cancelar
                </button>
                <button type="submit" disabled={editing} className={btn.primary}>
                  {editing ? <Spinner className="size-4" /> : 'Guardar y Recalcular'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal de Justificación de Incidencia */}
      {selectedRecord && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3">
              <h3 className="text-lg font-bold text-slate-900">Justificar Incidencia</h3>
              <button onClick={() => setSelectedRecord(null)} className="text-slate-400 hover:text-slate-600">
                <X className="size-5" />
              </button>
            </div>

            <div className="text-sm text-slate-600 space-y-1 bg-slate-50 p-3 rounded-xl">
              <p><b>Empleado:</b> {selectedRecord.employee_code}</p>
              <p><b>Fecha de Jornada:</b> {formatDate(selectedRecord.date)}</p>
              <p><b>Fichajes detectados:</b> {formatTime(selectedRecord.punch_in)} - {formatTime(selectedRecord.punch_out)}</p>
            </div>

            <form onSubmit={submitJustification} className="space-y-4">
              <div>
                <label className={labelCls}>Resolución del Supervisor</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                    <input
                      type="radio"
                      name="decision"
                      value="APPROVED"
                      checked={justifyAction === 'APPROVED'}
                      onChange={() => setJustifyAction('APPROVED')}
                    />
                    Aprobar (Jornada justificada)
                  </label>
                  <label className="flex items-center gap-2 text-sm text-slate-700 cursor-pointer">
                    <input
                      type="radio"
                      name="decision"
                      value="REJECTED"
                      checked={justifyAction === 'REJECTED'}
                      onChange={() => setJustifyAction('REJECTED')}
                    />
                    Rechazar (Incumplimiento)
                  </label>
                </div>
              </div>

              <div>
                <label className={labelCls}>Motivo / Comentario Formal</label>
                <textarea
                  required
                  rows={3}
                  minLength={5}
                  value={justifyReason}
                  onChange={(e) => setJustifyReason(e.target.value)}
                  placeholder="Detalla el motivo (ej. Salida autorizada para visita médica, olvido de fichaje confirmado...)"
                  className={`${inputCls} py-2`}
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setSelectedRecord(null)}
                  className={btn.secondary}
                >
                  Cancelar
                </button>
                <button type="submit" disabled={justifying} className={btn.primary}>
                  {justifying ? <Spinner className="size-4" /> : 'Guardar Resolución'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal de Confirmación de Cambios Masivos detectados en Excel */}
      {diffPreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4">
          <div className="w-full max-w-4xl max-h-[90vh] flex flex-col rounded-2xl bg-white shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            {/* Cabecera del Modal */}
            <div className="flex items-center justify-between border-b border-slate-200 bg-amber-50/70 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="flex size-10 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
                  <AlertTriangle className="size-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-slate-900">
                    Confirmación de Cambios Masivos en Fichajes
                  </h3>
                  <p className="text-xs text-slate-600">
                    Se han detectado modificaciones en {pendingFile ? <b>{pendingFile.name}</b> : 'el archivo'} respecto a los registros actuales.
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  setDiffPreview(null);
                  setPendingFile(null);
                }}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              >
                <X className="size-5" />
              </button>
            </div>

            {/* Contenido / Resumen de métricas */}
            <div className="p-6 space-y-4 overflow-y-auto flex-1">
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-center">
                  <div className="text-xs font-semibold text-slate-500 uppercase">Filas Revisadas</div>
                  <div className="text-lg font-bold text-slate-800">{diffPreview.total_rows_inspected}</div>
                </div>
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-center">
                  <div className="text-xs font-semibold text-amber-700 uppercase">Modificaciones</div>
                  <div className="text-lg font-bold text-amber-900">{diffPreview.modified_records_count}</div>
                </div>
                <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-3 text-center">
                  <div className="text-xs font-semibold text-indigo-700 uppercase">Nuevos Registros</div>
                  <div className="text-lg font-bold text-indigo-900">{diffPreview.new_records_count}</div>
                </div>
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-center">
                  <div className="text-xs font-semibold text-emerald-700 uppercase">Sin Cambios</div>
                  <div className="text-lg font-bold text-emerald-900">{diffPreview.unchanged_count}</div>
                </div>
              </div>

              {/* Tabla Comparativa de Cambios */}
              <div>
                <h4 className="text-xs font-bold uppercase text-slate-600 mb-2">
                  Detalle de Modificaciones Propuestas:
                </h4>
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-100 font-semibold text-slate-700 uppercase">
                      <tr>
                        <th className="px-3 py-2.5">Tipo</th>
                        <th className="px-3 py-2.5">Empleado</th>
                        <th className="px-3 py-2.5">Fecha</th>
                        <th className="px-3 py-2.5">Horas Anteriores</th>
                        <th className="px-3 py-2.5">Nuevas Horas (Calculadas)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 font-medium">
                      {diffPreview.changes.map((c, i) => (
                        <tr key={i} className="hover:bg-slate-50">
                          <td className="px-3 py-2.5">
                            <span
                              className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ${
                                c.change_type === 'MODIFIED'
                                  ? 'bg-amber-100 text-amber-800'
                                  : 'bg-indigo-100 text-indigo-800'
                              }`}
                            >
                              {c.change_type === 'MODIFIED' ? 'Modificado' : 'Nuevo'}
                            </span>
                          </td>
                          <td className="px-3 py-2.5">
                            <div className="font-semibold text-slate-900">{c.employee_code}</div>
                            {c.employee_name && (
                              <div className="text-[11px] text-slate-500">{c.employee_name}</div>
                            )}
                          </td>
                          <td className="px-3 py-2.5 text-slate-700">{formatDate(c.date)}</td>
                          <td className="px-3 py-2.5 text-slate-600">
                            {c.change_type === 'MODIFIED' ? (
                              <div>
                                <div>
                                  {formatTime(c.old_punch_in)} - {formatTime(c.old_punch_out)}
                                </div>
                                <div className="text-[11px] text-slate-400">
                                  {formatHours(c.old_ordinary_hours)} ord.
                                  {c.old_excess_hours > 0 && ` + ${formatHours(c.old_excess_hours)} exc.`}
                                </div>
                              </div>
                            ) : (
                              <span className="text-slate-400 italic">No existía</span>
                            )}
                          </td>
                          <td className="px-3 py-2.5 font-semibold text-indigo-700">
                            <div className="flex items-center gap-1.5">
                              {c.change_type === 'MODIFIED' && <ArrowRight className="size-3 text-amber-600" />}
                              <span>
                                {formatTime(c.new_punch_in)} - {formatTime(c.new_punch_out)}
                              </span>
                            </div>
                            <div className="text-[11px] text-slate-600">
                              {formatHours(c.new_ordinary_hours)} ord.
                              {c.new_excess_hours > 0 && (
                                <span className="text-amber-700 font-bold">
                                  {' '}
                                  + {formatHours(c.new_excess_hours)} exc.
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Justificación obligatoria para la auditoría */}
              <div>
                <label className={labelCls}>Motivo de la Modificación Masiva (Auditoría Laboral)</label>
                <input
                  type="text"
                  value={bulkAuditReason}
                  onChange={(e) => setBulkAuditReason(e.target.value)}
                  placeholder="Ej. Rectificación masiva acordada, parte horario corregido por jefatura..."
                  className={inputCls}
                />
              </div>
            </div>

            {/* Acciones de confirmación */}
            <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-4">
              <div className="text-xs text-slate-500">
                Al confirmar, se actualizarán los fichajes y se registrará trazabilidad con tu usuario.
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setDiffPreview(null);
                    setPendingFile(null);
                  }}
                  className={btn.secondary}
                >
                  Cancelar
                </button>
                <button
                  type="button"
                  onClick={confirmApplyChanges}
                  disabled={applyingBulk}
                  className="inline-flex items-center gap-2 rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-amber-700 transition disabled:opacity-50"
                >
                  {applyingBulk ? (
                    <Spinner className="size-4" />
                  ) : (
                    <>
                      <CheckCircle2 className="size-4" /> Confirmar y Aplicar Cambios
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
