import './App.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

function App() {
  return (
    <section id="center">
      <div>
        <h1>Hive Inspect Template Importer</h1>
        <p>
          Frontend foundation only. The UI is generated with Lovable and talks to the
          backend over HTTP.
        </p>
        <p>API base URL: {API_BASE_URL}</p>
      </div>
    </section>
  )
}

export default App