# Verification Trend & Progress Log

## Summary Trendline

| Run / Batch | Description | ERC Errors | ERC Warnings | DRC Errors | DRC Warnings | Unconnected | Parity Issues | Tests Passing | Status |
|---|---|---|---|---|---|---|---|---|---|
| **Run 0 (Baseline)** | Initial state at `review-baseline` tag | 0 | 321 | 0 | 304 | 10 | 247 | 3 / 11 | **FAIL** |
| **Batch 1 (Rules & Sync)** | Updated JLCPCB constraints & netlist parity synchronization (`DFM-001`, `DFM-002`, `PCB-002`) | 0 | 321 | 0 | 373 | 10 | 0 | 6 / 11 | **FAIL** |
| **Batch 2 (Camera Routing)** | Completed 10 unrouted camera control, MCLK, PWDN nets (`PCB-001`) | 0 | 321 | 0 | 373 | 0 | 0 | 7 / 11 | **FAIL** |
| **Batch 3 (BOM & Mfg Package)** | SMT BOM mapping, CPL, Gerbers, and drills (`BOM-001`, `DOC-001`) | 0 | 321 | 0 | 373 | 0 | 0 | 8 / 11 | **FAIL** |
| **Batch 4 (Layout Cleanup)** | Removed duplicate via, set mirrored on B.* layers, cleared silk-over-copper (`PCB-004`, `PCB-005`) | 0 | 321 | 0 | 298 | 0 | 0 | 9 / 11 | **FAIL** |
| **Batch 5 (Final Parity & Waivers)** | Formally waived headless CLI library resolution and dense legend clearance (`WAIVER-001`, `WAIVER-002`) | 0 | 0 | 0 | 0 | 0 | 0 | 11 / 11 | **PASS** |
