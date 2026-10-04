import { BrowserRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { ProtectedRoute, RoleHomeRedirect } from './auth/ProtectedRoute';
import { ROUTE_ROLES } from './auth/routes';
import { Layout } from './components/Layout';
import { LoginView } from './views/LoginView';
import { WorkerView } from './views/WorkerView';
import { SupervisorView } from './views/SupervisorView';
import { AdminView } from './views/AdminView';
import { AccessDeniedView } from './views/AccessDeniedView';

import { ProfileView } from './views/ProfileView';

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Ruta pública */}
          <Route path="/login" element={<LoginView />} />
          <Route path="/acceso-denegado" element={<AccessDeniedView />} />

          {/* Rutas protegidas dentro del Layout */}
          <Route element={<Layout />}>
            <Route index element={<RoleHomeRedirect />} />

            {/* Zona Trabajador */}
            <Route element={<ProtectedRoute roles={ROUTE_ROLES.worker} />}>
              <Route path="/mi-panel" element={<WorkerView />} />
            </Route>

            {/* Zona Supervisor y Administrador */}
            <Route element={<ProtectedRoute roles={ROUTE_ROLES.audit} />}>
              <Route path="/auditoria" element={<SupervisorView />} />
            </Route>

            {/* Zona Exclusiva Administrador */}
            <Route element={<ProtectedRoute roles={ROUTE_ROLES.admin} />}>
              <Route path="/admin" element={<AdminView />} />
            </Route>

            {/* Perfil y Datos Personales (Común a todos los roles) */}
            <Route element={<ProtectedRoute roles={ROUTE_ROLES.all} />}>
              <Route path="/perfil" element={<ProfileView />} />
            </Route>
          </Route>

          {/* Fallback */}
          <Route path="*" element={<RoleHomeRedirect />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
