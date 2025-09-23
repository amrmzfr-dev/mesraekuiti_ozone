import React, { useEffect, useState } from 'react';
import { apiService } from '../services/api';

const OutletsPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [outlets, setOutlets] = useState([]);
  const [deletingOutlet, setDeletingOutlet] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      if (!mounted) return;
      setError('');
      try {
        const data = await apiService.getOutlets();
        if (!mounted) return;
        setOutlets(Array.isArray(data) ? data : (data.results || []));
      } catch (e) {
        if (!mounted) return;
        setError('Failed to load outlets');
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

  const handleDeleteOutlet = async (outlet) => {
    if (!window.confirm(`⚠️ Delete outlet "${outlet.name}"?\n\nThis will remove:\n- Outlet data\n- All associated machines\n- All device bindings\n\nThis cannot be undone!`)) {
      return;
    }

    try {
      setDeletingOutlet(outlet.id);
      // Use proper individual delete endpoint
      const response = await fetch(`https://www.ozone-p2.mesraekuiti.com/api/outlets/${outlet.id}/`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include'
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      
      // Remove outlet from local state
      setOutlets(outlets.filter(o => o.id !== outlet.id));
      alert(`✅ Outlet "${outlet.name}" deleted successfully!`);
    } catch (err) {
      alert(`❌ Failed to delete outlet: ${err.message}`);
    } finally {
      setDeletingOutlet(null);
    }
  };

  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h1>Outlets Management</h1>
        <p>View and manage all outlets in the system</p>
      </div>

      {error && <div className="alert alert-danger" style={{marginBottom:'1rem'}}>{error}</div>}

      <div className="dashboard-card">
        <div className="card-header">
          <div className="card-icon">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h3>Outlets</h3>
        </div>

        <div style={{overflowX:'auto'}}>
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Location</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="5">Loading...</td></tr>
              ) : (
                outlets.map((o) => (
                  <tr key={o.id || o.pk || o.name}>
                    <td>{o.id || o.pk}</td>
                    <td>{o.name || '-'}</td>
                    <td>{o.location || '-'}</td>
                    <td>{o.active ? 'Active' : 'Inactive'}</td>
                    <td>
                      <div className="actions-cell">
                        <button className="secondary" style={{marginRight:'0.5rem'}}>Edit</button>
                        <button className="secondary" style={{marginRight:'0.5rem'}}>View</button>
                        <button 
                          className="danger-button-small" 
                          onClick={() => handleDeleteOutlet(o)}
                          disabled={deletingOutlet === o.id}
                        >
                          {deletingOutlet === o.id ? '🗑️' : '🗑️'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
              {!loading && outlets.length === 0 && (
                <tr><td colSpan="5">No outlets found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default OutletsPage;


