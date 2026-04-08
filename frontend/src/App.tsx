import { Routes, Route } from 'react-router-dom';
import Header from './components/layout/Header';
import HomePage from './pages/HomePage';
import MarketPage from './pages/MarketPage';
import FaucetPage from './pages/FaucetPage';
import PortfolioPage from './pages/PortfolioPage';
import OraclePage from './pages/OraclePage';
import SignPage from './pages/SignPage';

export default function App() {
  return (
    <div className="min-h-screen bg-[#0a0e17] text-slate-200">
      <Header />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/market/:id" element={<MarketPage />} />
        <Route path="/faucet" element={<FaucetPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/oracle" element={<OraclePage />} />
        <Route path="/sign" element={<SignPage />} />
      </Routes>
    </div>
  );
}
