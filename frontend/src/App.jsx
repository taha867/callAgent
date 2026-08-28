import { Routes, Route } from "react-router";
import { Navbar } from "@/components/Navbar";
import HealthPage from "@/pages/HealthPage";
import ClaimsPage from "@/pages/ClaimsPage";
import ClaimDetailPage from "@/pages/ClaimDetailPage";
import CallsPage from "@/pages/CallsPage";
import CallDetailPage from "@/pages/CallDetailPage";
import ComplaintsPage from "@/pages/ComplaintsPage";
import ComplaintDetailPage from "@/pages/ComplaintDetailPage";

export default function App() {
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<HealthPage />} />
        <Route path="/claims" element={<ClaimsPage />} />
        <Route path="/claims/:claimId" element={<ClaimDetailPage />} />
        <Route path="/calls" element={<CallsPage />} />
        <Route path="/calls/:callId" element={<CallDetailPage />} />
        <Route path="/complaints" element={<ComplaintsPage />} />
        <Route path="/complaints/:complaintId" element={<ComplaintDetailPage />} />
      </Routes>
    </>
  );
}
