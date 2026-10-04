import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AuthContext, type AuthContextValue, type AuthStatus, type LogoutReason } from './context';
import { setUnauthorizedHandler } from '../lib/api';
import { fetchProfile, login as loginRequest } from '../lib/endpoints';
import {
  clearToken,
  decodeToken,
  isExpired,
  readValidSession,
  saveToken,
  type TokenClaims,
} from '../lib/session';
import type { UserProfile, UserRole } from '../types/api';
import { ApiError } from '../lib/api';

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<AuthStatus>('loading');
  const [claims, setClaims] = useState<TokenClaims | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const expiryTimer = useRef<number | null>(null);

  const clearTimer = () => {
    if (expiryTimer.current !== null) {
      window.clearTimeout(expiryTimer.current);
      expiryTimer.current = null;
    }
  };

  const logout = useCallback(
    (reason: LogoutReason = 'manual') => {
      clearTimer();
      clearToken();
      setClaims(null);
      setProfile(null);
      setStatus('anonymous');
      navigate('/login', { replace: true, state: { reason } });
    },
    [navigate],
  );

  const scheduleExpiry = useCallback(
    (c: TokenClaims) => {
      clearTimer();
      const ms = Math.max(c.exp * 1000 - Date.now() - 5000, 0);
      expiryTimer.current = window.setTimeout(() => logout('expired'), ms);
    },
    [logout],
  );

  // Interceptor de 401: cualquier respuesta no autorizada cierra la sesión.
  useEffect(() => {
    setUnauthorizedHandler(() => logout('expired'));
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // Rehidratación de sesión al cargar la aplicación.
  useEffect(() => {
    const session = readValidSession();
    if (!session) {
      setStatus('anonymous');
      return;
    }
    const controller = new AbortController();
    setClaims(session.claims);
    scheduleExpiry(session.claims);
    fetchProfile(controller.signal)
      .then((p) => {
        setProfile(p);
        setStatus('authenticated');
      })
      .catch((err: unknown) => {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        // 401 ya gestionado por el interceptor; para otros errores, sesión anónima.
        if (!(err instanceof ApiError && err.status === 401)) {
          clearToken();
          setClaims(null);
          setStatus('anonymous');
        }
      });
    return () => {
      controller.abort();
      clearTimer();
    };
  }, [scheduleExpiry]);

  const login = useCallback(
    async (email: string, password: string): Promise<UserRole> => {
      const token = await loginRequest(email, password);
      const decoded = decodeToken(token.access_token);
      if (!decoded || isExpired(decoded)) {
        throw new ApiError(0, 'El servidor devolvió un token de sesión no válido.');
      }
      saveToken(token.access_token);
      const p = await fetchProfile();
      setClaims(decoded);
      setProfile(p);
      setStatus('authenticated');
      scheduleExpiry(decoded);
      return decoded.role;
    },
    [scheduleExpiry],
  );

  const value = useMemo<AuthContextValue>(
    () => ({ status, claims, profile, role: claims?.role ?? null, login, logout }),
    [status, claims, profile, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
