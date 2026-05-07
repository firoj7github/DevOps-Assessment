import React, { useEffect, useState } from 'react';
import { fetchHealth, fetchTasks } from './api';

function App() {
  const [status, setStatus] = useState('Checking...');

  useEffect(() => {
    // API কল চেক করার জন্য একটি উদাহরণ
    fetchHealth()
      .then(() => setStatus('Backend Connected ✅'))
      .catch(() => setStatus('Backend Not Reachable ❌'));
  }, []);

  return (
    <div className="App" style={{ textAlign: 'center', marginTop: '50px', fontFamily: 'Arial' }}>
      <header className="App-header">
        <h1>Hydrus Digital BD</h1>
        <p>Frontend is running with <strong>Nginx</strong></p>
        <div style={{ padding: '20px', background: '#f4f4f4', display: 'inline-block', borderRadius: '8px' }}>
          <strong>System Status:</strong> {status}
        </div>
      </header>
    </div>
  );
}

export default App;