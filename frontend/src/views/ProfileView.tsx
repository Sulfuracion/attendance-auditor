import { useState } from 'react';
import { User, Shield, Building, Clock, Key, CheckCircle2, Lock } from 'lucide-react';
import { useAuth } from '../auth/useAuth';
import { changePassword, updateProfile, fetchProfile } from '../lib/endpoints';
import { Alert, btn, inputCls, labelCls, PageHeader, Spinner } from '../components/ui';
import { ROLE_LABELS } from '../lib/format';
import { errorMessage } from '../lib/api';

export function ProfileView() {
  const { profile } = useAuth();

  // Estado para actualizar nombres
  const [firstName, setFirstName] = useState(profile?.first_name || '');
  const [lastName, setLastName] = useState(profile?.last_name || '');
  const [savingProfile, setSavingProfile] = useState(false);
  const [profileSuccess, setProfileSuccess] = useState<string | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Estado para cambio de contraseña
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError(null);
    setProfileSuccess(null);
    setSavingProfile(true);
    try {
      await updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      });
      setProfileSuccess('Datos personales actualizados correctamente.');
      // Refrescar en background
      await fetchProfile();
    } catch (err) {
      setProfileError(errorMessage(err));
    } finally {
      setSavingProfile(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError(null);
    setPasswordSuccess(null);

    if (newPassword !== confirmPassword) {
      setPasswordError('Las contraseñas nuevas no coinciden.');
      return;
    }

    setSavingPassword(true);
    try {
      const res = await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordSuccess(res.message);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setPasswordError(errorMessage(err));
    } finally {
      setSavingPassword(false);
    }
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      <PageHeader
        title="Mis Datos Personales"
        subtitle="Consulta y gestiona tu información de usuario y credenciales de seguridad"
      />

      {/* Tarjeta de Resumen de Cuenta */}
      <div className="rounded-3xl border border-slate-200 bg-white p-6 sm:p-8 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center gap-6 pb-6 border-b border-slate-100">
          <div className="size-20 rounded-2xl bg-indigo-600 text-white flex items-center justify-center font-bold text-2xl shadow-lg shadow-indigo-200 shrink-0">
            {profile?.first_name ? profile.first_name[0]?.toUpperCase() : profile?.email[0]?.toUpperCase()}
          </div>
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-slate-900">
              {profile?.first_name || profile?.last_name
                ? `${profile.first_name || ''} ${profile.last_name || ''}`
                : 'Usuario Corporativo'}
            </h2>
            <p className="text-sm text-slate-500">{profile?.email}</p>
            <div className="flex flex-wrap gap-2 pt-1">
              <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-3 py-0.5 text-xs font-semibold text-indigo-700 ring-1 ring-inset ring-indigo-200">
                <Shield className="size-3" />
                {profile?.role ? ROLE_LABELS[profile.role] : 'Rol no definido'}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-0.5 text-xs font-medium text-slate-600">
                <Building className="size-3" />
                {profile?.organization_name || 'Organización Corporativa'}
              </span>
              {profile?.employee_code && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-3 py-0.5 text-xs font-semibold text-emerald-700">
                  Código: {profile.employee_code}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Detalles Técnicos */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-6 text-sm">
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs text-slate-400 uppercase font-semibold">Horas Contractuales</p>
            <p className="text-base font-bold text-slate-800 mt-1 flex items-center gap-1.5">
              <Clock className="size-4 text-indigo-600" />
              {profile?.weekly_contract_hours ? `${profile.weekly_contract_hours} h/semana` : 'No asignadas'}
            </p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs text-slate-400 uppercase font-semibold">Estado de Cuenta</p>
            <p className="text-base font-bold text-emerald-600 mt-1 flex items-center gap-1.5">
              <CheckCircle2 className="size-4" />
              {profile?.is_active ? 'Activa y Verificada' : 'Inactiva'}
            </p>
          </div>
          <div className="rounded-2xl bg-slate-50 p-4">
            <p className="text-xs text-slate-400 uppercase font-semibold">Identificador de Usuario</p>
            <p className="text-xs font-mono text-slate-600 mt-1.5 truncate" title={profile?.id}>
              {profile?.id || '—'}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Formulario de Modificación de Nombres */}
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <div className="flex items-center gap-2 border-b pb-3">
            <User className="size-5 text-indigo-600" />
            <h3 className="text-base font-bold text-slate-900">Editar Nombre y Apellidos</h3>
          </div>

          {profileError && <Alert tone="error">{profileError}</Alert>}
          {profileSuccess && <Alert tone="success">{profileSuccess}</Alert>}

          <form onSubmit={handleUpdateProfile} className="space-y-4">
            <div>
              <label className={labelCls}>Nombre</label>
              <input
                type="text"
                required
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                placeholder="Ej. Carlos"
                className={inputCls}
              />
            </div>

            <div>
              <label className={labelCls}>Apellidos</label>
              <input
                type="text"
                required
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                placeholder="Ej. García López"
                className={inputCls}
              />
            </div>

            <button type="submit" disabled={savingProfile} className={`${btn.primary} w-full`}>
              {savingProfile ? <Spinner className="size-4" /> : 'Guardar Información'}
            </button>
          </form>
        </div>

        {/* Formulario de Cambio de Contraseña */}
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm space-y-4">
          <div className="flex items-center gap-2 border-b pb-3">
            <Key className="size-5 text-indigo-600" />
            <h3 className="text-base font-bold text-slate-900">Seguridad y Contraseña</h3>
          </div>

          {passwordError && <Alert tone="error">{passwordError}</Alert>}
          {passwordSuccess && <Alert tone="success">{passwordSuccess}</Alert>}

          <form onSubmit={handleChangePassword} className="space-y-3">
            <div>
              <label className={labelCls}>Contraseña Actual</label>
              <div className="relative">
                <input
                  type="password"
                  required
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder="••••••••"
                  className={`${inputCls} pl-9`}
                />
                <Lock className="pointer-events-none absolute left-3 top-3.5 size-4 text-slate-400" />
              </div>
            </div>

            <div>
              <label className={labelCls}>Nueva Contraseña</label>
              <div className="relative">
                <input
                  type="password"
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Mín. 8 caracteres, mayúscula, minúscula, dígito"
                  className={`${inputCls} pl-9`}
                />
                <Lock className="pointer-events-none absolute left-3 top-3.5 size-4 text-slate-400" />
              </div>
            </div>

            <div>
              <label className={labelCls}>Confirmar Nueva Contraseña</label>
              <div className="relative">
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repite la nueva contraseña"
                  className={`${inputCls} pl-9`}
                />
                <Lock className="pointer-events-none absolute left-3 top-3.5 size-4 text-slate-400" />
              </div>
            </div>

            <button type="submit" disabled={savingPassword} className={`${btn.primary} w-full mt-2`}>
              {savingPassword ? <Spinner className="size-4" /> : 'Actualizar Contraseña'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
