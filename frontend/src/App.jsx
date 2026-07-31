import { Routes, Route, Navigate } from 'react-router-dom'
import Header from './components/Header'
import BottomNav from './components/BottomNav'
import VaultGate from './components/VaultGate'
import { VaultProvider } from './context/vault'
import MedevacPage from './pages/MedevacPage'
import QueryPage from './pages/QueryPage'
import MapPage from './pages/MapPage'
import PrivacyPage from './pages/PrivacyPage'

export default function App() {
  // The vault gate wraps the entire app: no route, and not even the header,
  // renders until the passphrase has derived the encryption key. Locking from
  // anywhere returns the whole app to this gate.
  return (
    <VaultProvider>
      <VaultGate>
        <div className="app-container">
          <Header />
          <main className="main-content">
            <Routes>
              <Route path="/" element={<Navigate to="/query" replace />} />
              {/* Triage lives inside the Query page as a mode; keep old links working */}
              <Route path="/triage" element={<Navigate to="/query?mode=triage" replace />} />
              <Route path="/medevac" element={<MedevacPage />} />
              <Route path="/query" element={<QueryPage />} />
              <Route path="/map" element={<MapPage />} />
              <Route path="/privacy" element={<PrivacyPage />} />
            </Routes>
          </main>
          <BottomNav />
        </div>
      </VaultGate>
    </VaultProvider>
  )
}
