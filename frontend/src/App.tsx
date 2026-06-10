import UploadPanel from './components/UploadPanel'
import ChatPanel from './components/ChatPanel'
import NightQueuePanel from './components/NightQueuePanel'

function App() {
  return (
    <div className="app-container">
      <UploadPanel />
      <ChatPanel />
      <NightQueuePanel />
    </div>
  )
}

export default App
