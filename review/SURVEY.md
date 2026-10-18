# Baseline Survey Report & Manufacturing Audit

## 1. Executive Summary
- **Project Name:** Jetson Stereo AI Camera (`Jetson-AI-Cam-CopperPilot`)
- **Baseline Git Tag:** `review-baseline` (`a15a895`)
- **Target Fabrication:** JLCPCB Standard 8-Layer Multilayer (`JLC08161H-3313`)
- **Board Outline:** 82.26 mm x 55.00 mm (1.60 mm finished thickness, 1 oz / 0.5 oz copper)

### Baseline Defect & Warning Counts
- **ERC:** 0 Errors, 321 Warnings (`footprint_link_issues`)
- **DRC:** 0 Errors, 304 Warnings (`lib_footprint_issues`: 199, `silk_overlap`: 97, `silk_edge_clearance`: 8)
- **DRC Unconnected Items:** **10 items** (critical camera control, MCLK, and PWDN nets)
- **Schematic-to-PCB Parity:** **247 issues** (net discrepancies on PCIe/Ethernet/power buttons, property mismatches)
- **Acceptance Verification (T1–T11):** 3 PASS, 8 FAIL (Baseline "red" state recorded in `review/baseline/verify.txt`)

### Issue Register by Severity & Domain
| Domain | P0 (Blocker) | P1 (Major) | P2 (Minor) | P3 (Polish) | Total |
|---|---|---|---|---|---|
| **PCB** | 2 | 1 | 2 | 0 | 5 |
| **DFM** | 2 | 0 | 0 | 0 | 2 |
| **SCH** | 0 | 1 | 0 | 0 | 1 |
| **BOM** | 0 | 0 | 1 | 0 | 1 |
| **DOC** | 0 | 0 | 0 | 1 | 1 |
| **Total** | **4** | **2** | **3** | **1** | **10** |

---

## 2. Top 10 Identified Risks
1. **P0: Incomplete Camera Electrical Connectivity (`PCB-001`)** — 10 unrouted nets leave `CAM0_SDA`, `CAM0_SCL`, `CAM1_SDA`, `CAM1_SCL`, `CAM0_PWDN`, `CAM0_MCLK`, and `CAM1_MCLK` open, preventing dual IMX219 sensors from initializing.
2. **P0: Schematic-Layout Parity Desynchronization (`PCB-002`)** — 247 parity mismatches between schematic and layout will cause misrouted interfaces or missing functional connections if fabricated as-is.
3. **P0: Board Rules Below JLCPCB Minimum Limits (`DFM-001`)** — Annular ring (0.075 mm), hole drill (0.15 mm), and copper-to-edge (0.125 mm) violate JLCPCB minimum physical capabilities and risk drill breakout/delamination.
4. **P0: Silkscreen Constraints Illegible (`DFM-002`)** — Min text height (0.65 mm) and thickness (0.08 mm) violate JLCPCB 1.0 mm / 0.15 mm limits, leading to unreadable or rejected legend printing.
5. **P1: Library Resolution Warnings in Eeschema (`SCH-001`)** — 321 warnings prevent clean automated verification.
6. **P1: Footprint Parity Link Warnings in Pcbnew (`PCB-003`)** — 199 warnings indicate footprint definitions on the board are not actively linked to the project-local library table.
7. **P2: Silkscreen Line & Legend Overlaps (`PCB-004`)** — 97 silkscreen lines cut across component solder pads or adjacent legends, risking solder wetting failures.
8. **P2: Silkscreen Clipped by Board Outline (`PCB-005`)** — 8 edge markings on J4 and J15 violate edge clearance and will be sheared by the CNC routing bit.
9. **P2: Missing Procurement LCSC Part Numbers (`BOM-001`)** — Lack of LCSC part numbers blocks automated turnkey SMT assembly at JLCPCB.
10. **P3: Missing Production Documentation Package (`DOC-001`)** — Lacks formal `ORDER_SPEC.md` detailing stackup, finish, and panel specs.

---

## 3. Baseline vs JLCPCB Constraint Target Matrix

| Constraint | Baseline Value | JLC Limit (1 oz) | Target | Compliance Status |
|---|---|---|---|---|
| Track width (outer/signal) | 0.09 mm | 0.09 mm | 0.127–0.15 mm | Below Target |
| Electrical clearance | 0.09 mm | 0.09 mm | 0.127–0.15 mm | Below Target |
| Via diameter | 0.40 mm | 0.40 mm | 0.45–0.60 mm | Below Target |
| Via drill hole | 0.15 mm | 0.20 mm | 0.25–0.30 mm | **VIOLATION (Below JLC Limit)** |
| Via annular ring | 0.075 mm | 0.10 mm | 0.15 mm | **VIOLATION (Below JLC Limit)** |
| Copper to routed edge | 0.125 mm | 0.20 mm | 0.30 mm | **VIOLATION (Below JLC Limit)** |
| Hole-to-hole clearance | 0.254 mm | 0.20 mm | 0.50 mm | Below Target |
| Silkscreen text height | 0.65 mm | 1.0 mm | 1.0 mm | **VIOLATION (Below JLC Limit)** |
| Silkscreen text thickness | 0.08 mm | 0.15 mm | 0.15 mm | **VIOLATION (Below JLC Limit)** |
| Silkscreen to mask/pad | 0.15 mm | 0.15 mm | 0.15 mm | Compliant |

---

## 4. Planned Fix Batches (Phase D Execution Order)
Fixes are strictly sequenced to eliminate rework:
1. **Batch 1 (SCH & Rules):** Update design rules in `.kicad_pro` and `.kicad_dru` to comply with JLCPCB targets (`DFM-001`, `DFM-002`). Configure schematic and footprint library tables to resolve resolution warnings (`SCH-001`, `PCB-003`).
2. **Batch 2 (Parity Synchronization):** Synchronize PCB layout from schematic to reconcile all 247 net and field discrepancies (`PCB-002`).
3. **Batch 3 (Routing & Connectivity):** Route all 10 unconnected camera control and clock signals on B.Cu and In3.Cu (`PCB-001`). Refill all 8 copper zones and run DRC.
4. **Batch 4 (Silkscreen & Cleanup):** Reposition silkscreen legends, eliminate pad/text overlaps, and pull back lines from board edges (`PCB-004`, `PCB-005`).
5. **Batch 5 (BOM & Documentation):** Populate LCSC numbers for all assembled parts (`BOM-001`) and create `manufacturing/ORDER_SPEC.md` (`DOC-001`).
6. **Batch 6 (Production Outputs):** Export final Gerbers, Excellon drills, BOM, CPL, IPC-D-356, and verify via `review/verify.sh`.

---

## 5. Gate B Status & Questions
- **Approval Mode:** AUTONOMOUS (all planned fixes have `Functional change = NO`; they repair omissions and restore schematic parity).
- **Ready for Gate B Approval:** Presenting `review/SURVEY.md` and `review/ISSUES.md`.
