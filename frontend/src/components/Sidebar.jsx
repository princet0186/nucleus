import { NavLink, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import './Sidebar.css'

export default function Sidebar() {
  const [systemStatus, setSystemStatus] = useState(null)

  useEffect(() => {
    fetch('/health')
      .then(r => r.json())
      .then(data => setSystemStatus(data))
      .catch(() => setSystemStatus({ status: 'offline' }))
  }, [])

  const navItems = [
    { to: '/', label: 'Dashboard', icon: '◱' },
    { to: '/triage', label: 'Playground: Triage', icon: '✛' },
    { to: '/drugs', label: 'Playground: Drugs', icon: '⚕' },
    { to: '/medevac', label: 'MEDEVAC Builder', icon: '⬡' },
  ]

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="brand">
          <span className="brand-logo">✦</span>
          <span className="brand-name">Nucleus AI Studio</span>
        </div>
        <div className="brand-subtitle">Tactical Field Engine</div>
      </div>

      <div className="sidebar-nav">
        {navItems.map(item => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <span className="nav-icon">{item.icon}</span>
            <span className="nav-label">{item.label}</span>
          </NavLink>
        ))}
      </div>

      <div className="sidebar-footer">
        <div className="status-indicator">
          <div className={`status-dot ${systemStatus?.status === 'healthy' ? 'online' : 'offline'}`} />
          <div className="status-text">
            <span className="status-title">System Status</span>
            <span className="status-value">{systemStatus?.status === 'healthy' ? 'Operational' : 'Offline'}</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
