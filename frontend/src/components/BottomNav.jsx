import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import './BottomNav.css'

// The app's single navigator: three query modes plus the two planning tools,
// docked at the bottom like a radio channel selector. Each section carries a
// brevity code — the mono tag is the visual identity, no icon fonts.
const ITEMS = [
  { code: 'QRY', label: 'General Query', path: '/query', mode: 'general' },
  { code: 'TRG', label: 'Triage', path: '/query', mode: 'triage' },
  { code: 'MCI', label: 'Mass Casualty', path: '/query', mode: 'mascal' },
  { code: 'MEV', label: 'Medical Evacuation', path: '/medevac', mode: null },
  { code: 'MAP', label: 'Map Planning', path: '/map', mode: null },
]

export default function BottomNav() {
  const { pathname } = useLocation()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const activeMode = searchParams.get('mode') || 'general'

  const isActive = (item) => {
    if (pathname !== item.path) return false
    return item.mode === null || item.mode === activeMode
  }

  return (
    <nav className="bottom-nav" aria-label="Sections">
      <div className="bottom-nav-dock">
        {ITEMS.map(item => (
          <button
            key={item.code}
            className={`bottom-nav-item ${isActive(item) ? 'active' : ''}`}
            onClick={() => navigate(item.mode ? `${item.path}?mode=${item.mode}` : item.path)}
          >
            <span className="bottom-nav-code">{item.code}</span>
            <span className="bottom-nav-label">{item.label}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}
