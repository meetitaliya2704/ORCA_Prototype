"use client";

import React, { createContext, useContext, useState } from "react";
import { UserMode, UserModeConfig } from "./types";
import { userModeConfigs } from "./mockData";

export interface AuthUser {
  name: string;
  email: string;
  role: UserMode;
  roleLabel: string;
  location: string;
  organization?: string;
}

export const DEFAULT_PERSONAS: Record<UserMode, { name: string; roleLabel: string; location: string }> = {
  fisherman: { name: "User", roleLabel: "Fisherman", location: "Veraval, Gujarat" },
  authority: { name: "User", roleLabel: "Port Authority", location: "Gujarat Coast" },
  researcher: { name: "User", roleLabel: "Researcher", location: "Arabian Sea" },
  operator: { name: "User", roleLabel: "Fleet Operator", location: "India (West Coast)" },
};

interface UserModeContextType {
  mode: UserMode;
  setMode: (mode: UserMode) => void;
  switchRole: (role: UserMode) => void;
  config: UserModeConfig;
  user: AuthUser;
  location: string;
  setLocation: (loc: string) => void;
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
  const [mode, setModeState] = useState<UserMode>("fisherman");
  const [location, setLocation] = useState<string>("Veraval, Gujarat");
  const [user, setUser] = useState<AuthUser>({
    name: "User",
    email: "user@marine.gov.in",
    role: "fisherman",
    roleLabel: DEFAULT_PERSONAS.fisherman.roleLabel,
    location: DEFAULT_PERSONAS.fisherman.location,
    organization: "Marine Operations",
  });
  const [isLoggedIn, setIsLoggedIn] = useState(true);

  const config = userModeConfigs[mode] || userModeConfigs.fisherman;

  const switchRole = (newRole: UserMode) => {
    setModeState(newRole);
    const persona = DEFAULT_PERSONAS[newRole] || DEFAULT_PERSONAS.fisherman;
    setLocation(persona.location);
    setUser({
      name: "User",
      email: "user@marine.gov.in",
      role: newRole,
      roleLabel: persona.roleLabel,
      location: persona.location,
    });
    setIsLoggedIn(true);
  };

  const setMode = (newMode: UserMode) => {
    switchRole(newMode);
  };

  const login = async (email: string, _password: string, role: UserMode, name?: string) => {
    const persona = DEFAULT_PERSONAS[role] || DEFAULT_PERSONAS.fisherman;
    setModeState(role);
    setLocation(persona.location);
    setUser({
      name: name || persona.name,
      email,
      role,
      roleLabel: persona.roleLabel,
      location: persona.location,
    });
    setIsLoggedIn(true);
  };

  const register = async (
    name: string,
    email: string,
    _password: string,
    role: UserMode,
    organization?: string
  ) => {
    const persona = DEFAULT_PERSONAS[role] || DEFAULT_PERSONAS.fisherman;
    setModeState(role);
    setLocation(persona.location);
    setUser({
      name,
      email,
      role,
      roleLabel: persona.roleLabel,
      location: persona.location,
      organization,
    });
    setIsLoggedIn(true);
  };

  const logout = () => {
    switchRole("fisherman");
    setIsLoggedIn(false);
  };

  return (
    <UserModeContext.Provider
      value={{
        mode,
        setMode,
        switchRole,
        config,
        user,
        location,
        setLocation,
        isLoggedIn,
        login,
        register,
        logout,
      }}
    >
      {children}
    </UserModeContext.Provider>
  );
}

export function useUserMode() {
  const context = useContext(UserModeContext);
  if (!context) {
    const defaultPersona = DEFAULT_PERSONAS.fisherman;
    return {
      mode: "fisherman" as UserMode,
      setMode: () => {},
      switchRole: () => {},
      config: userModeConfigs.fisherman,
      user: {
        name: defaultPersona.name,
        email: "user@marine.gov.in",
        role: "fisherman" as UserMode,
        roleLabel: defaultPersona.roleLabel,
        location: defaultPersona.location,
      },
      location: defaultPersona.location,
      setLocation: () => {},
      isLoggedIn: true,
      login: async () => {},
      register: async () => {},
      logout: () => {},
    };
  }
  return context;
}
