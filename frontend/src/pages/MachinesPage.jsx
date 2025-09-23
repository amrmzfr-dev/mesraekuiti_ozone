import React, { useEffect, useState } from 'react';
import { apiService } from '../services/api';

const MachinesPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [machines, setMachines] = useState([]);
  const [deletingMachine, setDeletingMachine] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      if (!mounted) return;
      setError('');
      try {
        const data = await apiService.getMachines();
        if (!mounted) return;
        setMachines(Array.isArray(data) ? data : (data.results || []));
      } catch (e) {
        if (!mounted) return;
        setError('Failed to load machines');
      } finally {
        if (!mounted) return;
        setLoading(false);
      }
    };
    setLoading(true);
    fetchData();
    const interval = setInterval(fetchData, 5000);
    const onVisibility = () => { if (document.visibilityState === 'visible') fetchData(); };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      mounted = false;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  const handleDeleteMachine = async (machine) => {
    if (!window.confirm(`⚠️ Delete machine "${machine.name}"?\n\nThis will remove:\n- Machine data\n- All device bindings\n- Associated treatment data\n\nThis cannot be undone!`)) {
      return;
    }

    try {
      setDeletingMachine(machine.id);
      // Use proper individual delete endpoint
      const response = await fetch(`https://www.ozone-p2.mesraekuiti.com/api/machines/${machine.id}/`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include'
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      // Remove machine from local state
      setMachines(machines.filter(m => m.id !== machine.id));
      alert(`✅ Machine "${machine.name}" deleted successfully!`);
    } catch (err) {
      alert(`❌ Failed to delete machine: ${err.message}`);
    } finally {
      setDeletingMachine(null);
    }
  };

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h1>Machines Management</h1>
        <p>View and manage machines</p>
      </div>

      {error && <div className="alert alert-danger" style={{marginBottom:'1rem'}}>{error}</div>}

      <div className="dashboard-card">
        <div className="card-header">
          <div className="card-icon">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </div>
          <h3>Machines</h3>
        </div>

        <div style={{overflowX:'auto'}}>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Outlet</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="5">Loading...</td></tr>
              ) : (
                machines.map((m) => (
                  <tr key={m.id || m.pk || m.name}>
                    <td>{m.id || m.pk}</td>
                    <td>{m.name || '-'}</td>
                    <td>{m.outlet || '-'}</td>
                    <td>{m.active ? 'Active' : 'Inactive'}</td>
                    <td>
                      <div className="actions-cell">
                        <button className="secondary" style={{marginRight:'0.5rem'}}>Edit</button>
                        <button className="secondary" style={{marginRight:'0.5rem'}}>View</button>
                        <button 
                          className="danger-button-small" 
                          onClick={() => handleDeleteMachine(m)}
                          disabled={deletingMachine === m.id}
                        >
                          {deletingMachine === m.id ? '🗑️' : '🗑️'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
              {!loading && machines.length === 0 && (
                <tr><td colSpan="5">No machines found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default MachinesPage;


