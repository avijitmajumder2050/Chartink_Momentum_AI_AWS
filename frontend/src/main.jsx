import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import './quantile.css'
import { AuthProvider } from './auth/AuthContext.jsx'
import { ChartPreviewProvider } from './chart/ChartPreviewContext.jsx'
import { PushNotificationsProvider } from './push/PushNotificationsContext.jsx'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <PushNotificationsProvider>
          <ChartPreviewProvider>
            <App />
          </ChartPreviewProvider>
        </PushNotificationsProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
