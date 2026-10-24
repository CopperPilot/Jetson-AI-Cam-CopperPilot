# JLCPCB Manufacturing & Assembly Order Specification

## 1. Board & General Fabrication Parameters
- **Project Name:** Jetson Stereo AI Camera (`Jetson-AI-Cam-CopperPilot`)
- **Dimensions:** 82.26 mm x 55.00 mm
- **Layer Count:** 8 Layers (Multilayer Standard)
- **Board Thickness:** 1.60 mm ±10%
- **Material:** FR-4 Standard Tg 155–170°C
- **PCB Color (Solder Mask):** Green
- **Silkscreen Color:** White
- **Surface Finish:** ENIG (Electroless Nickel Immersion Gold, 1–2 µin Gold, 100–200 µin Nickel)
- **Copper Weight:**
  - Outer Layers (F.Cu, B.Cu): 1 oz (35 µm finished)
  - Inner Layers (In1–In6): 0.5 oz (17.5 µm finished)
- **Via Process:** Tented Vias (Solder mask covered)
- **Castellated Holes:** None
- **Edge Connector / Gold Fingers:** None
- **Flying Probe Test:** 100% Electrically Tested (IPC-D-356 verified)

---

## 2. Controlled Impedance Stackup (`JLC08161H-3313`)
JLCPCB Standard 8-Layer Impedance Stackup:
- **Layer 1 (Top / F.Cu):** 1 oz (0.035 mm) — High-speed signals & component pads
- *Dielectric 1 (Prepreg FR4-3313):* 0.0994 mm (Er=4.05)
- **Layer 2 (In1_5V0_SYS_VIN):** 0.5 oz (0.0152 mm) — Power Plane (5V0_SYS / VIN)
- *Dielectric 2 (Core FR4):* 0.2000 mm (Er=4.60)
- **Layer 3 (In2_SINGAL):** 0.5 oz (0.0152 mm) — High-speed differential & camera clock signals
- *Dielectric 3 (Prepreg FR4-2116):* 0.2000 mm (Er=4.16)
- **Layer 4 (In3_SIGNAL):** 0.5 oz (0.0152 mm) — High-speed display TMDS & internal routing
- *Dielectric 4 (Core FR4):* 0.4500 mm (Er=4.60)
- **Layer 5 (In4_GND):** 0.5 oz (0.0152 mm) — Ground Plane (Continuous low-impedance reference)
- *Dielectric 5 (Prepreg FR4-2116):* 0.2000 mm (Er=4.16)
- **Layer 6 (In5_3V3_SYS_SIGNAL):** 0.5 oz (0.0152 mm) — Power / Signal (3V3_SYS & camera control)
- *Dielectric 6 (Core FR4):* 0.2000 mm (Er=4.60)
- **Layer 7 (In6_GND):** 0.5 oz (0.0152 mm) — Ground Plane (Continuous reference for Bottom layer)
- *Dielectric 7 (Prepreg FR4-3313):* 0.0994 mm (Er=4.05)
- **Layer 8 (Bottom / B.Cu):** 1 oz (0.035 mm) — High-speed MIPI CSI diff pairs & component pads

### Controlled Impedance Targets:
- **100 Ω Differential Pairs:** HDMI TMDS, DisplayPort EDP, Ethernet MDI (`Z100_ext`, `Z100_in`)
- **90 Ω Differential Pairs:** USB 3.0 SuperSpeed, USB 2.0 High-Speed (`Z90_ext`, `Z90_in`)
- **85 Ω Differential Pairs:** PCIe Gen2/3 (`Z85_in`)
- **50 Ω Single-Ended:** RF / High-Speed Single Ended (`Z50_ext`)
- **100 Ω MIPI CSI-2 Differential Pairs:** Camera 0 & Camera 1 MIPI CSI-2 Lanes (`CSI_DIFF`)

---

## 3. Surface Mount Assembly (PCBA) Specification
- **Assembly Type:** Standard / Turnkey SMT Assembly
- **Assembly Sides:** Dual-side (Top and Bottom populated)
- **Tooling / Panelization:** Single Board with Edge Rails (Tooling holes & Fiducials on breakaways)
- **BOM File:** `manufacturing/BOM.csv` (contains Designator, Value, Footprint, LCSC Part #, MPN)
- **CPL File:** `manufacturing/CPL.csv` (contains Designator, Mid X, Mid Y, Rotation, Layer)
- **DNP Components:** Excluded from assembly BOM and CPL files.
  - **BAT1 (MS621FE-FL11E Rechargeable Coin Cell):** Marked DNP in automated SMT placement. Must be secondary hand-soldered post-reflow to prevent thermal rupture in 260°C convective oven.
  - **R48 (0 Ω 0402):** Marked DNP to ensure 3.3V feedback divider network (R118/R119/R45/C24) sets proper 3.30V nominal regulation on U2.
- **Critical Connectors & SMT Components:**
  - **J11 (USB Type-C):** 24-Pin SuperSpeed USB 3.1 receptacle (Würth 632723300011 / LCSC C456013).
  - **J15 (Jetson Nano SoM Socket):** TE Connectivity 2309413-1 260-Pin DDR4 SODIMM socket (LCSC C2766246).
  - **J2 (Mini DisplayPort):** TE Connectivity 2129320-3 (LCSC C574827).
  - **J1 (Micro-HDMI):** Molex 467651001 (LCSC C563878).
  - **J5, J9 (Micro-B USB):** Molex 473460001 (LCSC C132560).
  - **REC1, RST1, USR1 (Tactile Switches):** E-Switch TL3340AF160QG (LCSC C2886925).
- **Component Packaging:** Tape & Reel / Tube / Tray as provided by LCSC inventory.

---

## 4. Quality & Acceptance Verification
- **IPC Class:** IPC-A-610 Class 2
- **Netlist File:** `manufacturing/Jetson-AI-Cam-CopperPilot.d356`
- **Electrical Verification:** Zero open circuits, zero shorts (DRC clean, 0 unconnected items)
- **Solder Mask Dam:** Minimum 0.10 mm between adjacent SMD pads.
- **Cleanliness:** De-fluxed post-reflow, no ionic contamination.

---

## 5. Mechanical Integration & Assembly Constraints
- **SMT Spacer Standoffs (SP5, SP6):** M2.5 threaded SMT spacers (Würth 9774060151R, 6.0 mm height). Fastener hardware must use M2.5 screws with maximum head/washer outer diameter $\le 5.0\text{ mm}$ to maintain clearance to adjacent passives (R135, L8, FB3).
- **Dual IMX219 Optical Lens Mount Base:** Lens holder housings affixed over CAM_L and CAM_R receptacles on B.Cu must have base dimensions not exceeding $14.0\text{ mm} \times 14.0\text{ mm}$ to prevent mechanical interference with surrounding components (D5, R47, R126, R127).
- **Tactile Switches (RST1, REC1, USR1):** Located along board edge (X = 162.14 mm). Enclosure design must provide side-access actuator cutouts along the perimeter clear of the SODIMM socket latch swing radius.
- **Coin Cell Battery (BAT1):** MS621FE-FL11E rechargeable lithium coin cell is marked DNP for automated PCBA. Must be hand-soldered post-reflow/post-wash to prevent thermal rupture at 260°C peak reflow temperatures.
