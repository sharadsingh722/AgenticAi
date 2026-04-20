import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Resumes from './pages/Resumes';
import ResumeView from './pages/ResumeView';
import Tenders from './pages/Tenders';
import TenderView from './pages/TenderView';
import Matching from './pages/Matching';
import Chat from './pages/Chat';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/resumes" element={<Resumes />} />
          <Route path="/resumes/:id" element={<ResumeView />} />
          <Route path="/tenders" element={<Tenders />} />
          <Route path="/tenders/:id" element={<TenderView />} />
          <Route path="/matching" element={<Matching />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="*" element={<Navigate to="/resumes" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
