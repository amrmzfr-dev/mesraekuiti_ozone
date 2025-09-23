import React, { useEffect, useState } from 'react';
import { apiService } from '../services/api';

const Dashboard = () => {
  const [devicesData, setDevicesData] = useState({ devices: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const data = await apiService.getDevicesData();
        setDevicesData(data);
      } catch (err) {
        setError('Failed to load dashboard data');
        console.error('Dashboard data error:', err);
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30 seconds
    return () => clearInterval(interval);
  }, []);

  const devices = devicesData.devices || [];
  const onlineDevices = devices.filter(d => d.online).length;
  const offlineDevices = devices.length - onlineDevices;
  const totalTreatments = devices.reduce((sum, d) => {
    const counts = d.counts || {};
    return sum + (counts.basic || 0) + (counts.standard || 0) + (counts.premium || 0);
  }, 0);


  return (
    <div className="dashboard-container">
      <div className="dashboard-header">
        <h1>Dashboard</h1>
        <p>Monitor your ozone telemetry system in real-time</p>
      </div>
      
      {error && <div className="alert alert-danger" style={{marginBottom:'1rem'}}>{error}</div>}
      
      {/* Main Quick Stats - Real Data */}
      <div className="quick-stats-section">
        <div className="quick-stats-grid">
          <div className="quick-stat-card">
            <div className="stat-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
            </div>
            <div className="stat-content">
              <div className="stat-number">{loading ? '...' : devices.length}</div>
              <div className="stat-label">Total Devices</div>
              <div className="stat-change">{loading ? '' : `${onlineDevices} online`}</div>
            </div>
          </div>
          
          <div className="quick-stat-card">
            <div className="stat-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="stat-content">
              <div className="stat-number">{loading ? '...' : onlineDevices}</div>
              <div className="stat-label">Online Devices</div>
              <div className="stat-change">{loading ? '' : `${offlineDevices} offline`}</div>
            </div>
          </div>
          
          <div className="quick-stat-card">
            <div className="stat-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <div className="stat-content">
              <div className="stat-number">{loading ? '...' : totalTreatments}</div>
              <div className="stat-label">Total Treatments</div>
              <div className="stat-change">All time</div>
            </div>
          </div>
          
          <div className="quick-stat-card">
            <div className="stat-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="stat-content">
              <div className="stat-number">{loading ? '...' : devices.length > 0 ? Math.round((onlineDevices / devices.length) * 100) : 0}%</div>
              <div className="stat-label">System Health</div>
              <div className="stat-change">{loading ? '' : 'Device uptime'}</div>
            </div>
          </div>
        </div>
      </div>
      
      {/* Device Status Overview */}
      <div className="dashboard-grid">
        <div className="dashboard-card">
          <div className="card-header">
            <div className="card-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3>Device Status</h3>
          </div>
          
          {loading ? (
            <div style={{padding: '2rem', textAlign: 'center'}}>Loading device data...</div>
          ) : (
            <div className="device-status-list">
              {devices.length === 0 ? (
                <div style={{padding: '2rem', textAlign: 'center', color: '#666'}}>
                  No devices connected yet. ESP32 devices will appear here after handshake.
                </div>
              ) : (
                devices.slice(0, 5).map((device, index) => (
                  <div key={device.device_id || index} className="device-status-item">
                    <div className="device-info">
                      <div className="device-id">{device.device_id || 'Unknown'}</div>
                      <div className="device-mac">{device.mac || 'No MAC'}</div>
                    </div>
                    <div className="device-status">
                      <span className={`status-badge ${device.online ? 'online' : 'offline'}`}>
                        {device.online ? 'Online' : 'Offline'}
                      </span>
                      <div className="device-last-seen">
                        {device.last_seen ? new Date(device.last_seen).toLocaleString() : 'Never'}
                      </div>
                    </div>
                    <div className="device-counts">
                      <div className="count-item">
                        <span className="count-label">Basic:</span>
                        <span className="count-value">{device.counts?.basic || 0}</span>
                      </div>
                      <div className="count-item">
                        <span className="count-label">Standard:</span>
                        <span className="count-value">{device.counts?.standard || 0}</span>
                      </div>
                      <div className="count-item">
                        <span className="count-label">Premium:</span>
                        <span className="count-value">{device.counts?.premium || 0}</span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
        
        <div className="dashboard-card">
          <div className="card-header">
            <div className="card-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <h3>System Information</h3>
          </div>
          
          <div className="system-info">
            <div className="info-item">
              <span className="info-label">Total Devices:</span>
              <span className="info-value">{loading ? '...' : devices.length}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Online Devices:</span>
              <span className="info-value">{loading ? '...' : onlineDevices}</span>
            </div>
            <div className="info-item">
              <span className="info-label">Offline Devices:</span>
              <span className="info-value">{loading ? '...' : offlineDevices}</span>
            </div>
            <div className="info-item">
              <span className="info-label">System Health:</span>
              <span className="info-value">
                {loading ? '...' : devices.length > 0 ? `${Math.round((onlineDevices / devices.length) * 100)}%` : '0%'}
              </span>
            </div>
            <div className="info-item">
              <span className="info-label">Total Treatments:</span>
              <span className="info-value">{loading ? '...' : totalTreatments}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;


