import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import Budget from './pages/Budget';
import Trends from './pages/Trends';
import Subscriptions from './pages/Subscriptions';
import Upload from './pages/Upload';
import Settings from './pages/Settings';
import Login from './pages/Login';
import Chat from './pages/Chat';
import { useApp } from './context/AppContext';

function App() {
  const { authLoading, currentUser } = useApp();

  if (authLoading) {
    return <div className="auth-loading">Loading...</div>;
  }

  if (!currentUser) {
    return <Login />;
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="transactions" element={<Transactions />} />
          <Route path="budget" element={<Budget />} />
          <Route path="trends" element={<Trends />} />
          <Route path="subscriptions" element={<Subscriptions />} />
          <Route path="chat" element={<Chat />} />
          <Route path="upload" element={<Upload />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
