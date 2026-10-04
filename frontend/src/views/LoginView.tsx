import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Clock3, Lock, Mail } from 'lucide-react';
import { useAuth } from '../auth/useAuth';
import { HOME_BY_ROLE } from '../auth/routes';
import { Alert, btn, inputCls, labelCls, Spinner } from '../components/ui';
import { errorMessage } from '../lib/api';

export function LoginView() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reason = (location.state as { reason?: string })?.reason;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const role = await login(email, password);
      const destination = HOME_BY_ROLE[role] || '/';
      navigate(destination, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[80vh] items-center justify-center px-4 py-12">
      <div className="w-full max-w-md space-y-8 rounded-3xl border border-slate-200 bg-white p-8 shadow-xl sm:p-10">
        <div className="text-center">
          <div className="mx-auto inline-flex rounded-2xl bg-indigo-600 p-3 text-white shadow-lg shadow-indigo-200">
            <Clock3 className="size-8" />
          </div>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-slate-900">Control de Asistencia</h2>
          <p className="mt-2 text-sm text-slate-500">Inicia sesión con tu cuenta corporativa</p>
        </div>

        {reason === 'expired' && (
          <Alert tone="warning">Tu sesión ha expirado por inactividad. Por favor, identifícate de nuevo.</Alert>
        )}

        {error && <Alert tone="error">{error}</Alert>}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className={labelCls}>Correo Electrónico</label>
            <div className="relative">
              <input
                type="email"
                required
                className={`${inputCls} pl-10`}
                placeholder="ejemplo@empresa.local"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
              <Mail className="pointer-events-none absolute left-3 top-3.5 size-4 text-slate-400" />
            </div>
          </div>

          <div>
            <label className={labelCls}>Contraseña</label>
            <div className="relative">
              <input
                type="password"
                required
                className={`${inputCls} pl-10`}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <Lock className="pointer-events-none absolute left-3 top-3.5 size-4 text-slate-400" />
            </div>
          </div>

          <button type="submit" disabled={loading} className={`${btn.primary} w-full`}>
            {loading ? <Spinner className="size-5" /> : 'Entrar al Sistema'}
          </button>
        </form>

        <div className="rounded-xl bg-slate-50 p-4 text-xs text-slate-500">
          <p className="font-semibold text-slate-700">Cuentas demo disponibles:</p>
          <ul className="mt-1 space-y-1">
            <li>👑 <b>Admin:</b> admin@empresa.com / AdminPass123!</li>
            <li>👔 <b>Supervisor:</b> supervisor@empresa.com / SupervisorPass123!</li>
            <li>👷 <b>Trabajador:</b> worker@empresa.com / WorkerPass123!</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
