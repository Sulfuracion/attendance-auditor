import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { Clock3, LogOut, Menu, X } from 'lucide-react';
import { useAuth } from '../auth/useAuth';
import { NAV_ITEMS } from '../auth/routes';
import { ROLE_LABELS } from '../lib/format';

export function Layout() {
  const { role, profile, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();

  // Cierra el menú móvil al navegar.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  const items = NAV_ITEMS.filter((i) => role && i.roles.includes(role));

  const linkCls = ({ isActive }: { isActive: boolean }) =>
    `flex min-h-11 items-center rounded-lg px-3 text-sm font-medium transition ${
      isActive ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
    }`;

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <div className="flex items-center gap-2">
            <span className="rounded-lg bg-indigo-600 p-1.5 text-white">
              <Clock3 className="size-5" aria-hidden="true" />
            </span>
            <span className="font-semibold text-slate-900">Auditor de Asistencia</span>
          </div>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Navegación principal">
            {items.map((i) => (
              <NavLink key={i.to} to={i.to} className={linkCls}>
                {i.label}
              </NavLink>
            ))}
          </nav>

          <div className="hidden items-center gap-3 md:flex">
            <NavLink
              to="/perfil"
              title="Ir a Mis Datos Personales"
              className="text-right leading-tight rounded-lg px-2 py-1 hover:bg-slate-50 transition"
            >
              <p className="max-w-56 truncate text-sm font-semibold text-slate-800">
                {profile?.first_name ? `${profile.first_name} ${profile.last_name || ''}` : profile?.email}
              </p>
              <p className="text-xs text-indigo-600 font-medium">{role ? ROLE_LABELS[role] : ''}</p>
            </NavLink>
            <button
              type="button"
              onClick={() => logout('manual')}
              className="inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm text-slate-600 hover:bg-slate-100"
            >
              <LogOut className="size-4" aria-hidden="true" />
              Cerrar sesión
            </button>
          </div>

          <button
            type="button"
            className="inline-flex size-11 items-center justify-center rounded-lg text-slate-700 hover:bg-slate-100 md:hidden"
            aria-label={menuOpen ? 'Cerrar menú' : 'Abrir menú'}
            aria-expanded={menuOpen}
            aria-controls="menu-movil"
            onClick={() => setMenuOpen((o) => !o)}
          >
            {menuOpen ? <X className="size-6" /> : <Menu className="size-6" />}
          </button>
        </div>

        {menuOpen && (
          <div id="menu-movil" className="border-t border-slate-200 bg-white px-4 pb-4 pt-2 md:hidden">
            <nav className="flex flex-col gap-1" aria-label="Navegación móvil">
              {items.map((i) => (
                <NavLink key={i.to} to={i.to} className={linkCls}>
                  {i.label}
                </NavLink>
              ))}
            </nav>
            <div className="mt-3 border-t border-slate-100 pt-3">
              <p className="truncate text-sm font-medium text-slate-800">{profile?.email}</p>
              <p className="text-xs text-slate-500">{role ? ROLE_LABELS[role] : ''}</p>
              <button
                type="button"
                onClick={() => logout('manual')}
                className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-xl border border-slate-300 text-sm font-medium text-slate-700"
              >
                <LogOut className="size-4" aria-hidden="true" />
                Cerrar sesión
              </button>
            </div>
          </div>
        )}
      </header>

      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  );
}
