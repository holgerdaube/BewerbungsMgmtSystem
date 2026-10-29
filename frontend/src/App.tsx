import { Routes, Route } from 'react-router-dom'
import { ReviewCountProvider } from './context/ReviewCount'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Suche from './pages/Suche'
import Jobs from './pages/Jobs'
import JobNew from './pages/JobNew'
import JobDetail from './pages/JobDetail'
import Companies from './pages/Companies'
import Review from './pages/Review'
import FollowUps from './pages/FollowUps'
import Inbox from './pages/Inbox'
import Pipeline from './pages/Pipeline'
import Outreach from './pages/Outreach'
import Netzwerk from './pages/Netzwerk'
import Beirat from './pages/Beirat'
import Tasks from './pages/Tasks'
import Budget from './pages/Budget'
import Profil from './pages/Profil'
import Einstellungen from './pages/Einstellungen'
import Rechtliches from './pages/Rechtliches'
import Dokumentation from './pages/Dokumentation'

export default function App() {
  return (
    <ReviewCountProvider>
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/suche" element={<Suche />} />
        <Route path="/review" element={<Review />} />
        <Route path="/followups" element={<FollowUps />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="/jobs/neu" element={<JobNew />} />
        <Route path="/jobs/:id" element={<JobDetail />} />
        <Route path="/inbox" element={<Inbox />} />
        <Route path="/outreach" element={<Outreach />} />
        <Route path="/netzwerk" element={<Netzwerk />} />
        <Route path="/beirat" element={<Beirat />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/budget" element={<Budget />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/radar" element={<Companies radar />} />
        <Route path="/profil" element={<Profil />} />
        <Route path="/einstellungen" element={<Einstellungen />} />
        <Route path="/dokumentation" element={<Dokumentation />} />
        <Route path="/rechtliches" element={<Rechtliches />} />
      </Routes>
    </Layout>
    </ReviewCountProvider>
  )
}
