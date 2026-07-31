import { NavLink } from 'react-router-dom'
import { useVault } from '../context/vault'
import Logo from './Logo'
import './Header.css'

// Slim top bar: identity on the left, trust controls on the right. All
// navigation lives in the bottom dock.
export default function Header() {
  const { lock } = useVault()

  return (
    <header className="header">
      <div className="header-brand">
        <div className="brand">
          <Logo className="brand-logo-img" />
          {/* Wordmark mirrors the word itself: a dense core (CLE) holding the
              lighter shell letters in orbit around it. */}
          <span className="wordmark" aria-label="Nucleus">
            <span className="wm-shell">NU</span>
            <span className="wm-core">CLE</span>
            <span className="wm-shell">US</span>
          </span>
        </div>
      </div>

      <div className="header-footer">
        <NavLink
          to="/privacy"
          className={({ isActive }) => `privacy-link ${isActive ? 'active' : ''}`}
          title="What left this device, and how it was protected"
        >
          <span className="privacy-link-icon"></span>
          <span>Privacy Dashboard</span>
        </NavLink>
        <button className="lock-btn" onClick={lock} title="Lock the vault (re-enter passphrase to return)">
          <span className="lock-icon">🔒</span>
          <span className="lock-label">Lock</span>
        </button>
      </div>
    </header>
  )
}
