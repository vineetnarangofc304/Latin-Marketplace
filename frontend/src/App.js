import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Overview from "@/pages/Overview";
import Reports from "@/pages/Reports";
import Uploads from "@/pages/Uploads";
import SalesLedger from "@/pages/SalesLedger";
import Calculations from "@/pages/Calculations";
import Reconciliation from "@/pages/Reconciliation";
import Discrepancies from "@/pages/Discrepancies";
import Recovery from "@/pages/Recovery";
import Insights from "@/pages/Insights";
import Masters from "@/pages/Masters";
import { Toaster } from "sonner";

function Shell({ children }) {
  return (
    <ProtectedRoute>
      <Layout>{children}</Layout>
    </ProtectedRoute>
  );
}

function App() {
  return (
    <div className="App">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/" element={<Shell><Overview /></Shell>} />
            <Route path="/reports" element={<Shell><Reports /></Shell>} />
            <Route path="/uploads" element={<Shell><Uploads /></Shell>} />
            <Route path="/sales" element={<Shell><SalesLedger /></Shell>} />
            <Route path="/calculations" element={<Shell><Calculations /></Shell>} />
            <Route path="/reconciliation" element={<Shell><Reconciliation /></Shell>} />
            <Route path="/discrepancies" element={<Shell><Discrepancies /></Shell>} />
            <Route path="/recovery" element={<Shell><Recovery /></Shell>} />
            <Route path="/insights" element={<Shell><Insights /></Shell>} />
            <Route path="/masters" element={<Shell><Masters /></Shell>} />
          </Routes>
        </BrowserRouter>
        <Toaster
          theme="light"
          position="top-right"
          toastOptions={{
            style: { background: "#FFFFFF", border: "1px solid #E1E4E8", fontFamily: "JetBrains Mono", fontSize: 12, borderRadius: 2, color: "#111827" },
          }}
        />
      </AuthProvider>
    </div>
  );
}

export default App;
