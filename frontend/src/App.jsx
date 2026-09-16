import { useState, useEffect } from 'react'
import axios from 'axios'

function App() {
  const [healthData, setHealthData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const checkHealth = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await axios.get('http://localhost:8000/api/health')
      setHealthData(response.data)
    } catch (err) {
      setError(err.message || 'Failed to connect to backend')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    checkHealth()
  }, [])

  return (
    <div className="container">
      <header className="hero">
        <h1 className="title">YojnaSathi</h1>
        <p className="subtitle">Government Schemes Made Simple</p>
      </header>

      <main className="content">
        <div className="card">
          <h2>Backend Health Status</h2>
          {loading && <p className="status loading">Checking backend health...</p>}
          {error && (
            <div className="status error">
              <p>Connection Error: {error}</p>
              <button onClick={checkHealth} className="btn">Retry</button>
            </div>
          )}
          {healthData && (
            <div className="status success">
              <p>Status: <strong>{healthData.status}</strong></p>
              <p>Service: <strong>{healthData.service}</strong></p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
