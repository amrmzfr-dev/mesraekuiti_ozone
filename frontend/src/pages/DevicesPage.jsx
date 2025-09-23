import React, { useEffect, useState, useRef } from 'react';
import { apiService } from '../services/api';

const DevicesPage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [devices, setDevices] = useState([]);
  const [machines, setMachines] = useState([]);
  const [showBindModal, setShowBindModal] = useState(false);
  const [selectedDevice, setSelectedDevice] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      if (!mounted) return;
      setError('');
      try {
        const [devicesData, machinesData] = await Promise.all([
          apiService.getDevicesData(),
          apiService.getMachines()
        ]);
        if (!mounted) return;
        setDevices(devicesData.devices || []);
        setMachines(machinesData.results || machinesData || []);
      } catch (e) {
        if (!mounted) return;
        setError('Failed to load devices');
        console.error('Devices data error:', e);
      } finally {
        if (!mounted) return;
        setLoading(false);
      }
    };

    // initial and fast polling
    setLoading(true);
    fetchData();
    const interval = setInterval(fetchData, 5000); // 5s polling

    // refetch on tab focus/visibility
    const onVisibility = () => { if (document.visibilityState === 'visible') fetchData(); };
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      mounted = false;
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  const handleBindDevice = (device) => {
    setSelectedDevice(device);
    setShowBindModal(true);
  };


  const formatLastSeen = (lastSeen) => {
    if (!lastSeen) return 'Never';
    const date = new Date(lastSeen);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return date.toLocaleDateString();
  };

  return (
    <div className="page-container">
      <div style={{ marginBottom: '1rem' }}>
        <h1 style={{ margin: 0 }}>ESP32 Devices</h1>
        <p style={{ marginTop: '0.25rem', color: '#64748b' }}>Manage ESP32 devices and their machine bindings</p>
      </div>

      {error && <div className="alert alert-danger" style={{marginBottom:'1rem'}}>{error}</div>}

      <div style={{overflowX:'auto'}}>
        <table>
            <thead>
              <tr>
                <th>Device ID</th>
                <th>MAC Address</th>
                <th>Firmware</th>
                <th>Status</th>
                <th>Last Seen</th>
                <th>Treatments</th>
                <th>Machine</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan="8">Loading devices...</td></tr>
              ) : (
                devices.map((device) => (
                  <tr key={device.device_id}>
                    <td>
                      <div className="device-id-cell">
                        <strong>{device.device_id}</strong>
                        {device.assigned && <span className="assigned-badge">Assigned</span>}
                      </div>
                    </td>
                    <td>
                      <code className="mac-address">{device.mac}</code>
                    </td>
                    <td>{device.firmware || 'Unknown'}</td>
                    <td>
                      <span className={`status-badge ${device.online ? 'online' : 'offline'}`}>
                        {device.online ? 'Online' : 'Offline'}
                      </span>
                    </td>
                    <td>
                      <div className="last-seen-cell">
                        <div>{formatLastSeen(device.last_seen)}</div>
                        {device.last_seen && (
                          <small className="timestamp">
                            {new Date(device.last_seen).toLocaleString()}
                          </small>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="treatments-cell">
                        <div className="treatment-count">
                          <span className="count-label">B:</span>
                          <span className="count-value">{device.counts?.basic || 0}</span>
                        </div>
                        <div className="treatment-count">
                          <span className="count-label">S:</span>
                          <span className="count-value">{device.counts?.standard || 0}</span>
                        </div>
                        <div className="treatment-count">
                          <span className="count-label">P:</span>
                          <span className="count-value">{device.counts?.premium || 0}</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="machine-cell">
                        {device.assigned ? (
                          <span className="machine-assigned">Bound to Machine</span>
                        ) : (
                          <span className="machine-unassigned">Unassigned</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button 
                          className="secondary" 
                          onClick={() => handleBindDevice(device)}
                          disabled={device.assigned}
                        >
                          {device.assigned ? 'Bound' : 'Bind'}
                        </button>
                        <button className="secondary">View</button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
              {!loading && devices.length === 0 && (
                <tr><td colSpan="8">No ESP32 devices found. Devices will appear here after handshake.</td></tr>
              )}
            </tbody>
        </table>
      </div>

      {/* Machine Binding Modal */}
      {showBindModal && (
        <div className="modal-overlay" onClick={() => setShowBindModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Bind Device to Machine</h3>
              <button className="modal-close" onClick={() => setShowBindModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <div className="device-info">
                <h4>Device: {selectedDevice?.device_id}</h4>
                <p>MAC: {selectedDevice?.mac}</p>
                <p>Firmware: {selectedDevice?.firmware}</p>
              </div>
              <div className="machine-selection">
                <h4>Select Machine:</h4>
                <select className="machine-select">
                  <option value="">Choose a machine...</option>
                  {machines.map((machine) => (
                    <option key={machine.id} value={machine.id}>
                      {machine.name} - {machine.outlet?.name || 'No Outlet'}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="modal-footer">
              <button className="secondary" onClick={() => setShowBindModal(false)}>Cancel</button>
              <button onClick={() => {
                // TODO: Implement machine binding API call
                setShowBindModal(false);
              }}>Bind Device</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DevicesPage;


