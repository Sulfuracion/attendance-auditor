import type { UserRole } from '../types/api';

/** Ruta de inicio para cada rol tras iniciar sesión. */
export const HOME_BY_ROLE: Record<UserRole, string> = {
  ADMIN: '/admin',
  SUPERVISOR: '/auditoria',
  WORKER: '/mi-panel',
};

export const ROUTE_ROLES = {
  worker: ['WORKER'],
  audit: ['SUPERVISOR', 'ADMIN'],
  admin: ['ADMIN'],
  all: ['ADMIN', 'SUPERVISOR', 'WORKER'],
} as const satisfies Record<string, readonly UserRole[]>;

export interface NavItem {
  to: string;
  label: string;
  roles: readonly UserRole[];
}

export const NAV_ITEMS: readonly NavItem[] = [
  { to: '/admin', label: 'Panel global', roles: ROUTE_ROLES.admin },
  { to: '/auditoria', label: 'Auditoría de fichajes', roles: ROUTE_ROLES.audit },
  { to: '/mi-panel', label: 'Mi portal', roles: ROUTE_ROLES.worker },
  { to: '/perfil', label: 'Mis Datos', roles: ROUTE_ROLES.all },
];
