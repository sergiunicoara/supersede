"""Seed a small FICTIONAL quality-procedure knowledge base (no real client data)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from supersede.store import Store

def seed(path: str) -> None:
    s = Store(path)
    s.add_document("QP-07", "Final inspection procedure", authority=3)      # controlled procedure
    s.add_document("CSR-A", "Customer-specific requirements (client A)", authority=4)
    s.add_document("WI-12", "Shift work instruction", authority=1)          # informal
    q1 = s.add_revision("QP-07", 1, "2024-01-01")
    q2 = s.add_revision("QP-07", 2, "2025-03-01")
    q3 = s.add_revision("QP-07", 3, "2025-11-01")
    s.supersede(q2, q1); s.supersede(q3, q2)
    c1 = s.add_revision("CSR-A", 1, "2025-01-15")
    w1 = s.add_revision("WI-12", 1, "2025-06-01")
    s.assert_fact(q1, "F01", "final_inspection", "sampling", "100% inspection")
    s.assert_fact(q2, "F02", "final_inspection", "sampling", "AQL 1.0")
    s.assert_fact(q3, "F03", "final_inspection", "sampling", "AQL 0.65")
    s.assert_fact(w1, "F04", "final_inspection", "sampling", "100% inspection")
    s.assert_fact(c1, "F05", "delivery", "otd_target", "95%")
    s.assert_fact(w1, "F06", "delivery", "otd_target", "92%")
    s.commit(); s.close()

if __name__ == "__main__":
    seed(sys.argv[1] if len(sys.argv) > 1 else "demo.relate")
    print("seeded")
