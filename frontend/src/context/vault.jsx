// App-wide vault state.
//
// The passphrase gate protects the whole application, not one page. Every screen
// — chat, triage, MEDEVAC, map — sits behind it, because the encryption key it
// derives is what makes anything stored on the device readable, and locking must
// black out all of it at once, not just the tab that happens to be open.
//
// The derived key lives only in this module's memory (see lib/vault.js). This
// context exposes the *status* and the transitions; it never holds the key or
// the passphrase.

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  vaultStatus,
  setupVault,
  unlockVault,
  lockVault,
} from "../lib/vault";

const VaultContext = createContext(null);

export function VaultProvider({ children }) {
  // "checking" until libsodium reports whether a vault already exists on disk.
  const [status, setStatus] = useState("checking"); // checking | new | locked | unlocked

  useEffect(() => {
    vaultStatus().then(setStatus);
  }, []);

  const value = useMemo(
    () => ({
      status,
      isUnlocked: status === "unlocked",

      // Create a brand-new vault (first run) with this passphrase.
      async create(passphrase) {
        await setupVault(passphrase);
        setStatus("unlocked");
      },

      // Unlock an existing vault. Throws "Wrong passphrase" on mismatch, leaving
      // status untouched so the gate stays up.
      async unlock(passphrase) {
        await unlockVault(passphrase);
        setStatus("unlocked");
      },

      // Drop the in-memory key. The salt stays on disk, so this is a re-lock, not
      // a wipe: the same passphrase unlocks again. Returns the app to the gate.
      lock() {
        lockVault();
        setStatus("locked");
      },
    }),
    [status]
  );

  return <VaultContext.Provider value={value}>{children}</VaultContext.Provider>;
}

export function useVault() {
  const ctx = useContext(VaultContext);
  if (!ctx) throw new Error("useVault must be used within a VaultProvider");
  return ctx;
}
