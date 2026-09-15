import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import './quantile.css'
import { AuthProvider } from './auth/AuthContext.jsx'
import { ChartPreviewProvider } from './chart/ChartPreviewContext.jsx'
import { PushNotificationsProvider } from './push/PushNotificationsContext.jsx'
import App from './App.jsx'

// No <StrictMode> — its dev-only double-invoked effects were firing
// every page's data fetch twice (confirmed in the Flask access log:
// paired OPTIONS+GET for every endpoint, and ChartWall's 356-symbol EMA
// cross scan sending 712 requests). Real cost against real backends
// (Dhan/DynamoDB/Cognito), not just perceived load time, and it doesn't
// happen in a production build anyway — the one place it caught a real
// bug (Callback.jsx reusing a consumed PKCE code_verifier) is already
// guarded with a ranOnce ref, not relying on StrictMode to keep working.
createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <AuthProvider>
      <PushNotificationsProvider>
        <ChartPreviewProvider>
          <App />
        </ChartPreviewProvider>
      </PushNotificationsProvider>
    </AuthProvider>
  </BrowserRouter>,
)
