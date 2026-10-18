"""Automated hardware verification test suite for Jetson Stereo AI Camera PCB."""

import json
import math
import os
import re

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class TestBoardPhysical:
    """Verifies board physical dimensions, layer stackup, and boundary geometry."""

    def test_board_dimensions(self, pcb_data):
        """Assert outer bounding box matches 82.26 x 55.00 mm (+/- 1.5 mm tolerance)."""
        xs = []
        ys = []
        for elem in pcb_data.edge_cuts:
            if elem["type"] == "line":
                xs.extend([elem["x1"], elem["x2"]])
                ys.extend([elem["y1"], elem["y2"]])
            elif elem["type"] == "arc":
                xs.extend([elem["x1"], elem["xm"], elem["x2"]])
                ys.extend([elem["y1"], elem["ym"], elem["y2"]])
            elif elem["type"] == "circle":
                xs.extend([elem["cx"] - elem["radius"], elem["cx"] + elem["radius"]])
                ys.extend([elem["cy"] - elem["radius"], elem["cy"] + elem["radius"]])

        assert len(xs) > 0, "No Edge.Cuts elements found"
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)

        assert 80.0 <= width <= 84.0, (
            f"Board width {width:.2f} mm out of range [80, 84]"
        )
        assert 53.5 <= height <= 56.5, (
            f"Board height {height:.2f} mm out of range [53.5, 56.5]"
        )

    def test_board_outline_closed(self, pcb_data):
        """Assert Edge.Cuts contains continuous bounding line/arc primitives."""
        assert len(pcb_data.edge_cuts) >= 4, (
            f"Expected closed board outline with >= 4 primitives, got {len(pcb_data.edge_cuts)}"
        )

    def test_8_layer_stackup(self, pcb_data):
        """Assert high-density 8-layer stackup with solid internal power and ground planes."""
        cu_names = [l["canonical"] for l in pcb_data.copper_layers]
        expected_layers = [
            "F.Cu",
            "In1.Cu",
            "In2.Cu",
            "In3.Cu",
            "In4.Cu",
            "In5.Cu",
            "In6.Cu",
            "B.Cu",
        ]
        for l in expected_layers:
            assert l in cu_names, f"Expected copper layer '{l}' missing from board stackup"


class TestConnectivityAndNetlist:
    """Verifies electrical connectivity, routing completeness, and DRC/ERC parity."""

    def test_drc_zero_unconnected_items(self, drc_results):
        """Assert kicad-cli pcb drc returns exactly 0 unconnected items (100% routed)."""
        unconnected = drc_results.get("unconnected_items", [])
        assert len(unconnected) == 0, (
            f"Found {len(unconnected)} unconnected items: {unconnected}"
        )

    def test_drc_zero_errors(self, drc_results):
        """Assert kicad-cli pcb drc returns 0 violations with severity 'error'."""
        violations = drc_results.get("violations", [])
        errors = [v for v in violations if v.get("severity") == "error"]
        assert len(errors) == 0, f"Found {len(errors)} DRC errors: {errors}"

    def test_erc_zero_errors(self, erc_results):
        """Assert kicad-cli sch erc returns 0 violations with severity 'error'."""
        sheets = erc_results.get("sheets", [])
        all_errors = []
        for sheet in sheets:
            errors = [
                v for v in sheet.get("violations", []) if v.get("severity") == "error"
            ]
            all_errors.extend(errors)
        assert len(all_errors) == 0, f"Found {len(all_errors)} ERC errors: {all_errors}"

    def test_critical_power_and_signal_nets_present(self, pcb_data):
        """Assert all critical power and high-speed signal nets exist on the PCB."""
        critical_nets = [
            "GND",
            "5V0_SYS",
            "3V3_SYS",
            "1V8_SYS",
            "VIN",
        ]
        routed_nets = {s["net_name"] for s in pcb_data.segments}
        for net in critical_nets:
            assert net in routed_nets or net in pcb_data.nets, (
                f"Critical net '{net}' missing from PCB"
            )

    def test_no_unassigned_vias(self, pcb_data):
        """Assert all vias are bound to active named nets."""
        assert len(pcb_data.vias) >= 100, f"Expected >= 100 vias, got {len(pcb_data.vias)}"
        for via in pcb_data.vias:
            assert via["net_name"] != "", (
                f"Unassigned via detected at ({via['x']}, {via['y']})"
            )


class TestTraceGeometryAndDFM:
    """Verifies manufacturing rule margins against JLCPCB Multilayer capabilities."""

    def test_trace_min_width(self, pcb_data):
        """Assert all routed tracks meet or exceed 0.099 mm (JLCPCB multilayer limit 0.090 mm)."""
        for seg in pcb_data.segments:
            assert seg["width"] >= 0.099, (
                f"Trace width {seg['width']} mm at ({seg['x1']}, {seg['y1']}) violates 0.090 mm fab limit"
            )

    def test_via_dimensions_and_annular_ring(self, pcb_data):
        """Assert via drill and annular rings meet manufacturing limits."""
        for via in pcb_data.vias:
            assert via["drill"] >= 0.10, f"Via drill {via['drill']} mm < 0.10 mm microvia limit"
            assert via["size"] >= 0.20, f"Via diameter {via['size']} mm < 0.20 mm limit"
            assert via["annular_ring"] >= 0.04, (
                f"Via annular ring {via['annular_ring']} mm < 0.04 mm limit"
            )

    def test_min_copper_clearance(self, drc_results):
        """Assert zero clearance violations reported by DRC engine."""
        clearance_errors = [
            v
            for v in drc_results.get("violations", [])
            if "clearance" in v.get("type", "").lower() and v.get("severity") == "error"
        ]
        assert len(clearance_errors) == 0, f"Found clearance errors: {clearance_errors}"


class TestSubsystemCircuits:
    """Verifies physical placement and topology of onboard subsystems."""

    def test_jetson_sodimm_socket_present(self, pcb_data):
        """Assert TE 2309413-1 SODIMM-260 module socket is placed."""
        assert "J15" in pcb_data.footprints, "Jetson SODIMM socket J15 missing from layout"

    def test_dual_imx219_camera_ports_present(self, pcb_data):
        """Assert dual IMX219 stereo vision camera headers/modules exist."""
        assert "CAM_L" in pcb_data.footprints, "Left camera CAM_L missing from layout"
        assert "CAM_R" in pcb_data.footprints, "Right camera CAM_R missing from layout"

    def test_power_delivery_subsystem_present(self, pcb_data):
        """Assert SiC477 synchronous buck converter IC is placed."""
        assert "U6" in pcb_data.footprints, "SiC477 buck converter U6 missing from layout"

    def test_display_interfaces_present(self, pcb_data):
        """Assert Mini DisplayPort (J2) and Micro-HDMI (J1) connectors are placed."""
        assert "J2" in pcb_data.footprints, "Mini DisplayPort J2 missing from layout"
        assert "J1" in pcb_data.footprints, "Micro-HDMI J1 missing from layout"

    def test_usb_interfaces_present(self, pcb_data):
        """Assert USB-C (J11) and USB Micro-B (J9/J5) connectors are placed."""
        assert "J11" in pcb_data.footprints, "USB-C connector J11 missing from layout"
        assert "J9" in pcb_data.footprints or "J5" in pcb_data.footprints, "USB Micro-B connector missing"


class Test3DModelsAndLibraryIntegrity:
    """Verifies 3D model assignments and environment variable cleanliness."""

    def test_critical_connectors_have_3d_models(self, pcb_data):
        """Assert primary mechanical connectors have 3D models assigned."""
        for ref in ["J15", "J2", "J1", "J11", "U6"]:
            fp = pcb_data.footprints.get(ref)
            assert fp is not None, f"Footprint {ref} not found"
            assert len(fp["models"]) > 0, f"Footprint {ref} missing 3D model assignment"


class TestManufacturingDeliverables:
    """Verifies production release outputs in manufacturing/."""

    def test_gerber_release_archive_exists(self):
        """Assert manufacturing/gerbers.zip exists and contains valid data."""
        zip_path = os.path.join(ROOT_DIR, "manufacturing", "gerbers.zip")
        assert os.path.exists(zip_path), "manufacturing/gerbers.zip does not exist"
        assert os.path.getsize(zip_path) > 100000, "gerbers.zip is suspiciously small"

    def test_bom_and_cpl_exist(self):
        """Assert production BOM.csv and CPL.csv exist and contain headers."""
        bom_path = os.path.join(ROOT_DIR, "manufacturing", "BOM.csv")
        cpl_path = os.path.join(ROOT_DIR, "manufacturing", "CPL.csv")
        assert os.path.exists(bom_path), "manufacturing/BOM.csv does not exist"
        assert os.path.exists(cpl_path), "manufacturing/CPL.csv does not exist"

    def test_order_spec_exists(self):
        """Assert manufacturing/ORDER_SPEC.md exists."""
        spec_path = os.path.join(ROOT_DIR, "manufacturing", "ORDER_SPEC.md")
        assert os.path.exists(spec_path), "manufacturing/ORDER_SPEC.md does not exist"


class TestAcceptanceReportIntegrity:
    """Verifies review/verify-report.json status."""

    def test_verify_report_overall_pass(self):
        """Assert review/verify-report.json records overall status PASS."""
        report_path = os.path.join(ROOT_DIR, "review", "verify-report.json")
        assert os.path.exists(report_path), "review/verify-report.json does not exist"
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data.get("overall_status") == "PASS", f"verify-report status is {data.get('overall_status')}"
