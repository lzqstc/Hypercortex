import './assets/styles/global.css'
import { createRoot } from 'react-dom/client'
import './index.css'
import './assets/styles/font.css'
import App from './App'
import { FeedbackProvider } from './components/Feedback'
import './styles/hide-demo.css'
import './styles/interactions.css'
import './styles/qa-layout.css'
import './styles/wiki-content.css'
import './styles/layout-fixes.css'

createRoot(document.getElementById('root')!).render(
    <FeedbackProvider>
        <App />
    </FeedbackProvider>
)

