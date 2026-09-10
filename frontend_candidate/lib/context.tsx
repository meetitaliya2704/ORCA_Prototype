"use client";

import React, { createContext, useContext, useState } from "react";
import { UserMode, UserModeConfig } from "./types";
import { userModeConfigs } from "./mockData";

export interface AuthUser {
  name: string;
  email: string;
  role: UserMode;
  organization?: string;
}

interface UserModeContextType {
  mode: UserMode;
  setMode: (mode: UserMode) => void;
  config: UserModeConfig;
  user: AuthUser | null;
  isLoggedIn: boolean;
  login: (email: string, password: string, role: UserMode, name?: string) => Promise<void>;
  register: (
    name: string,
    email: string,
    password: string,
    role: UserMode,
    organization?: string
  ) => Promise<void>;
  logout: () => void;
}

const UserModeContext = createContext<UserModeContextType | undefined>(undefined);

export function UserModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<UserMode>("fisherman");
  const [user, setUser] = useState<AuthUser | null>(null);

  const config = userModeConfigs[mode] || userModeConfigs.fisherman;

  const login = async (email: string, _password: string, role: UserMode, name?: string) => {
    setMode(role);
    setUser({ name: name || email.split("@")[0], email, role });
  };

  const register = async (
    name: string,
    email: string,
    _password: string,
    role: UserMode,
    organization?: string
  ) => {
    setMode(role);
    setUser({ name, email, role, organization });
  };

  const logout = () => {
    setUser(null);
  };

  return (
    <UserModeContext.Provider
      value={{ mode, setMode, config, user, isLoggedIn: !!user, login, register, logout }}
    >
      {children}
    </UserModeContext.Provider>
  );
}

export function useUserMode() {
  const context = useContext(UserModeContext);
  if (!context) {
    return {
      mode: "fisherman" as UserMode,
      setMode: () => {},
      config: userModeConfigs.fisherman,
      user: null,
      isLoggedIn: false,
      login: async () => {},
      register: async () => {},
      logout: () => {},
    };
  }
  return context;
}
