"use client";

import React, { createContext, useContext, useState } from "react";
import { UserMode, UserModeConfig } from "./types";
import { userModeConfigs } from "./mockData";

interface UserModeContextType {
  mode: UserMode;
  setMode: (mode: UserMode) => void;
  config: UserModeConfig;
}

const UserModeContext = createContext<UserModeContextType | undefined>(undefined);

export function UserModeProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<UserMode>("fisherman");

  const config = userModeConfigs[mode] || userModeConfigs.fisherman;

  return (
    <UserModeContext.Provider value={{ mode, setMode, config }}>
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
    };
  }
  return context;
}