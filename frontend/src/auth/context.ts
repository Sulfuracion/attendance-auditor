import { createContext } from 'react';
import type { UserProfile, UserRole } from '../types/api';
import type { TokenClaims } from '../lib/session';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous';
export type LogoutReason = 'manual' | 'expired';

export interface AuthContextValue {
  status: AuthStatus;
  claims: TokenClaims | null;
  profile: UserProfile | null;
  role: UserRole | null;
  login: (email: string, password: string) => Promise<UserRole>;
  logout: (reason?: LogoutReason) => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
