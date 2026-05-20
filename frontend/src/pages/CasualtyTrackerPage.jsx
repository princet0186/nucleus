import { useState, useEffect } from 'react';
import './CasualtyTracker.css';

export default function CasualtyTrackerPage() {
  const [casualties, setCasualties] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  // New Casualty Form State
  const [showAddForm, setShowAddForm] = useState(false);
  const [formData, setFormData] = useState({
    patient_id: '',
    full_name: '',
    unit: '',
    injury_type: '',
    triage_category: 'T1-IMMEDIATE',
  });

  const fetchCasualties = async () => {
    try {
      const response = await fetch('http://localhost:8000/nucleus/casualty');
      if (!response.ok) throw new Error('Failed to fetch casualties');
      const data = await response.json();
      setCasualties(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCasualties();
  }, []);

  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleAddCasualty = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch('http://localhost:8000/nucleus/casualty/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      if (!response.ok) {
         const d = await response.json();
         throw new Error(d.detail || 'Failed to create casualty');
      }
      setShowAddForm(false);
      setFormData({ patient_id: '', full_name: '', unit: '', injury_type: '', triage_category: 'T1-IMMEDIATE' });
      fetchCasualties(); // refresh list
    } catch (err) {
      alert("Error: " + err.message);
    }
  };

  const updateRole = async (patient_id, new_role) => {
    try {
      const response = await fetch(`http://localhost:8000/nucleus/casualty/${patient_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ evacuation_role: new_role })
      });
      if (!response.ok) throw new Error('Failed to update role');
      fetchCasualties(); // refresh list
    } catch (err) {
      alert("Error updating role: " + err.message);
    }
  };

  const roles = ['Role 1', 'Role 2', 'Role 3'];

  if (loading) return <div className="loading-state">Initializing tracking grid...</div>;

  return (
    <div className="tracker-page">
      <div className="tracker-header">
        <div>
          <h2>Patient Evacuation Tracker</h2>
          <p>Secure replacement for DD Form 1380 (E2E Encrypted)</p>
        </div>
        <button className="add-btn" onClick={() => setShowAddForm(!showAddForm)}>
          {showAddForm ? 'Cancel' : '+ Add Casualty'}
        </button>
      </div>

      {showAddForm && (
        <form className="add-casualty-form glass-panel" onSubmit={handleAddCasualty}>
          <div className="form-grid">
            <input name="patient_id" placeholder="Patient ID (e.g. ALPHA-01)" value={formData.patient_id} onChange={handleInputChange} required />
            <input name="full_name" placeholder="Full Name" value={formData.full_name} onChange={handleInputChange} required />
            <input name="unit" placeholder="Unit" value={formData.unit} onChange={handleInputChange} required />
            <select name="triage_category" value={formData.triage_category} onChange={handleInputChange} required>
              <option value="T1-IMMEDIATE">T1-IMMEDIATE</option>
              <option value="T2-DELAYED">T2-DELAYED</option>
              <option value="T3-MINIMAL">T3-MINIMAL</option>
              <option value="T4-EXPECTANT">T4-EXPECTANT</option>
            </select>
          </div>
          <textarea name="injury_type" placeholder="Injury Details" value={formData.injury_type} onChange={handleInputChange} required></textarea>
          <button type="submit" className="submit-btn">Create Secure Record</button>
        </form>
      )}

      {error && <div className="error-banner">{error}</div>}

      <div className="kanban-board">
        {roles.map(role => (
          <div key={role} className="kanban-column">
            <h3>{role}</h3>
            <div className="kanban-cards">
              {casualties.filter(c => c.evacuation_role === role).map(casualty => (
                <div key={casualty.id} className={`casualty-card ${casualty.triage_category.split('-')[0].toLowerCase()}`}>
                  <div className="card-header">
                    <span className="patient-id">{casualty.patient_id}</span>
                    <span className={`triage-badge ${casualty.triage_category.split('-')[0].toLowerCase()}`}>
                      {casualty.triage_category}
                    </span>
                  </div>
                  <div className="card-body">
                    <p><strong>Name:</strong> <span className="encrypted-data">{casualty.full_name}</span></p>
                    <p><strong>Unit:</strong> <span className="encrypted-data">{casualty.unit}</span></p>
                    <p><strong>Injury:</strong> {casualty.injury_type}</p>
                  </div>
                  <div className="card-actions">
                    {role !== 'Role 1' && (
                      <button onClick={() => updateRole(casualty.patient_id, roles[roles.indexOf(role) - 1])}>&larr; Prev Role</button>
                    )}
                    {role !== 'Role 3' && (
                      <button onClick={() => updateRole(casualty.patient_id, roles[roles.indexOf(role) + 1])}>Next Role &rarr;</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
