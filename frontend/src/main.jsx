import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import './quantile.css'
import { AuthProvider } from './auth/AuthContext.jsx'
import { ChartPreviewProvider } from './chart/ChartPreviewContext.jsx'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <ChartPreviewProvider>
          <App />
        </ChartPreviewProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
