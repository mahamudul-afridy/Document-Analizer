import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { PageLoader } from "./components/ui";
import { useAuth } from "./lib/auth";
import { JobStreamProvider } from "./lib/jobs";
import Analytics from "./pages/Analytics";
import ApiManagement from "./pages/ApiManagement";
import Dashboard from "./pages/Dashboard";
import DocumentDetail from "./pages/DocumentDetail";
import Documents from "./pages/Documents";
import Invoices from "./pages/Invoices";
import Login from "./pages/Login";
import Queue from "./pages/Queue";
import SearchPage from "./pages/Search";
import SettingsPage from "./pages/Settings";
import Upload from "./pages/Upload";
import Validation from "./pages/Validation";

export default function App() {
  const { user, loading } = useAuth();
  if (loading)
    return (
      <div className="flex h-screen items-center justify-center">
        <PageLoader />
      </div>
    );
  if (!user) return <Login />;
  return (
    <JobStreamProvider>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/documents/:id" element={<DocumentDetail />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/queue" element={<Queue />} />
          <Route path="/invoices" element={<Invoices />} />
          <Route path="/validation" element={<Validation />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/api" element={<ApiManagement />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </JobStreamProvider>
  );
}
