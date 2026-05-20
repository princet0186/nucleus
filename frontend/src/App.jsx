import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import TriagePage from './pages/TriagePage'
import DrugCheckPage from './pages/DrugCheckPage'
import MedevacPage from './pages/MedevacPage'
import CasualtyTrackerPage from './pages/CasualtyTrackerPage'

export default function App() {
  return (
    <div className="app-container">
      <Sidebar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/triage" element={<TriagePage />} />
          <Route path="/drugs" element={<DrugCheckPage />} />
          <Route path="/medevac" element={<MedevacPage />} />
          <Route path="/tracker" element={<CasualtyTrackerPage />} />
        </Routes>
      </main>
    </div>
  )
}
