// The passphrase screen that stands in front of the entire app.
//
// While the vault is anything but "unlocked", this is all that renders — no
// header nav, no routes, nothing that could touch encrypted data before the key
// exists. Once unlocked, it renders its children (the real app) and steps out of
// the way until the next lock.

import { useState } from "react";
import { useVault } from "../context/vault";
import Logo from "./Logo";
import "./VaultGate.css";

export default function VaultGate({ children }) {
  const { status, create, unlock } = useVault();
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (status === "unlocked") return children;

  // "checking" is the brief window before libsodium reports whether a vault
  // exists. Show nothing rather than flash the wrong heading.
  if (status === "checking") {
    return (
      <div className="vault-gate">
        <div className="vault-card">
          <div className="vault-icon">⧗</div>
          <p className="vault-hint">Loading secure vault…</p>
        </div>
      </div>
    );
  }

  const isNew = status === "new";

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!passphrase.trim() || busy) return;
    setBusy(true);
    try {
      if (isNew) await create(passphrase);
      else await unlock(passphrase);
      setPassphrase("");
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="vault-gate">
      <div className="vault-card">
        <div className="vault-brand">
          <Logo className="vault-brand-logo-img" />
          <span className="vault-brand-name">Nucleus</span>
        </div>
        <div className="vault-icon">🔒</div>
        <h2>{isNew ? "Create Vault Passphrase" : "Unlock Nucleus"}</h2>
        <p className="vault-hint">
          {isNew
            ? "Create you pass. it cannot be recovered."
            : "Enter your passphrase to decrypt."}
        </p>
        <form onSubmit={handleSubmit} className="vault-form">
          <input
            type="password"
            className="vault-input"
            placeholder="Passphrase"
            value={passphrase}
            onChange={(e) => setPassphrase(e.target.value)}
            autoFocus
            autoComplete={isNew ? "new-password" : "current-password"}
          />
          <button type="submit" className="vault-submit" disabled={busy || !passphrase.trim()}>
            {busy ? "…" : isNew ? "Create & Enter" : "Unlock"}
          </button>
        </form>
        {error && <p className="vault-error">{error}</p>}
      </div>
    </div>
  );
}
