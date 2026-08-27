import { Routes, Route } from "react-router";
import HealthPage from "@/pages/HealthPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HealthPage />} />
    </Routes>
  );
}
