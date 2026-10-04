import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './useAuth';
import { HOME_BY_ROLE } from './routes';
import type { UserRole } from '../types/api';
import { FullPageSpinner } from '../components/ui';

interface ProtectedRouteProps {
  roles: readonly UserRole[];
}

/**
 * Guarda de navegación:
 *  - Sin sesión → /login (recordando la ruta solicitada).
 *  - Rol no autorizado → /acceso-denegado.
 * El backend vuelve a autorizar cada petición: esto es solo control de UX.
 */
export function ProtectedRoute({ roles }: ProtectedRouteProps) {
  const { status, role } = useAuth();
  const location = useLocation();

  if (status === 'loading') return <FullPageSpinner />;
  if (status === 'anonymous' || !role) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (!roles.includes(role)) {
    return <Navigate to="/acceso-denegado" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

/** Redirige a la página de inicio del rol actual (o a /login). */
export function RoleHomeRedirect() {
  const { status, role } = useAuth();
  if (status === 'loading') return <FullPageSpinner />;
  if (!role) return <Navigate to="/login" replace />;
  return <Navigate to={HOME_BY_ROLE[role]} replace />;
}
