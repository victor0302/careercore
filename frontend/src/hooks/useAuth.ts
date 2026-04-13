"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import { clearTokens, getAccessToken, setTokenPair } from "@/lib/auth";
import type { TokenPair, User } from "@/types";

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

interface LoginCredentials {
  email: string;
  password: string;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  // Fetch current user on mount if a token exists
  useEffect(() => {
    const token = getAccessToken();
    if (!token) {
      setState({ user: null, isLoading: false, isAuthenticated: false });
      return;
    }

    api
      .get<User>("/api/v1/auth/me")
      .then((user) => {
        setState({ user, isLoading: false, isAuthenticated: true });
      })
      .catch(() => {
        clearTokens();
        setState({ user: null, isLoading: false, isAuthenticated: false });
      });
  }, []);

  const login = useCallback(async (credentials: LoginCredentials): Promise<void> => {
    const tokens = await api.post<TokenPair>("/api/v1/auth/login", credentials, {
      skipAuth: true,
    });
    setTokenPair(tokens.access_token, tokens.refresh_token);

    const user = await api.get<User>("/api/v1/auth/me");
    setState({ user, isLoading: false, isAuthenticated: true });
  }, []);

  const logout = useCallback(() => {
    clearTokens();
    setState({ user: null, isLoading: false, isAuthenticated: false });
  }, []);

  return {
    user: state.user,
    isLoading: state.isLoading,
    isAuthenticated: state.isAuthenticated,
    login,
    logout,
  };
}
