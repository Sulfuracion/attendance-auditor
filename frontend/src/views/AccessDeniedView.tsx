import { ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { btn } from '../components/ui';
import { useAuth } from '../auth/useAuth';
import { HOME_BY_ROLE } from '../auth/routes';

export function AccessDeniedView() {
  const { role } = useAuth();
  const target = role ? HOME_BY_ROLE[role] : '/login';

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center p-4">
      <div className="rounded-2xl bg-red-100 p-4 text-red-600 mb-4">
        <ShieldAlert className="size-12" />
      </div>
      <h1 className="text-2xl font-bold text-slate-900">Acceso Denegado</h1>
      <p className="mt-2 max-w-md text-sm text-slate-500">
        Tu rol actual no dispone de autorización suficiente para visualizar esta sección.
      </p>
      <div className="mt-6">
        <Link to={target} className={btn.primary}>
          Volver a mi zona autorizada
        </Link>
      </div>
    </div>
  );
}
