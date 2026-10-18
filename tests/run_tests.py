#!/usr/bin/env python3
"""Standalone test runner for Jetson Stereo AI Camera hardware verification tests."""

import inspect
import os
import sys

# Ensure root directory is in sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "tests"))

from conftest import KiCadPCB, KiCadSCH, PCB_FILE, SCH_FILE, KICAD_CLI
import subprocess
import json

def get_drc_results():
    report_file = os.path.join(ROOT_DIR, ".drc_standalone_tmp.json")
    cmd = [KICAD_CLI, "pcb", "drc", "--refill-zones", "--format", "json", "-o", report_file, PCB_FILE]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if os.path.exists(report_file):
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        os.remove(report_file)
        return data
    return {"violations": [], "unconnected_items": []}

def get_erc_results():
    report_file = os.path.join(ROOT_DIR, ".erc_standalone_tmp.json")
    cmd = [KICAD_CLI, "sch", "erc", "--format", "json", "-o", report_file, SCH_FILE]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if os.path.exists(report_file):
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        os.remove(report_file)
        return data
    return {"sheets": []}

def run_all_tests():
    print("=" * 65)
    print(" Jetson Stereo AI Camera - Hardware Automated Test Suite")
    print("=" * 65)

    print("Parsing PCB layout and schematic hierarchy...")
    pcb = KiCadPCB(PCB_FILE)
    sch = KiCadSCH(SCH_FILE)
    print("Running DRC check...")
    drc = get_drc_results()
    print("Running ERC check...")
    erc = get_erc_results()

    fixtures = {
        "pcb_data": pcb,
        "sch_data": sch,
        "drc_results": drc,
        "erc_results": erc,
    }

    import test_pcb

    passed = 0
    failed = 0
    total = 0

    test_classes = [
        test_pcb.TestBoardPhysical,
        test_pcb.TestConnectivityAndNetlist,
        test_pcb.TestTraceGeometryAndDFM,
        test_pcb.TestSubsystemCircuits,
        test_pcb.Test3DModelsAndLibraryIntegrity,
        test_pcb.TestManufacturingDeliverables,
        test_pcb.TestAcceptanceReportIntegrity,
    ]

    for cls in test_classes:
        instance = cls()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        for m_name in methods:
            total += 1
            method = getattr(instance, m_name)
            sig = inspect.signature(method)
            kwargs = {p: fixtures[p] for p in sig.parameters if p in fixtures}

            try:
                method(**kwargs)
                print(f"[PASS] {cls.__name__}.{m_name}")
                passed += 1
            except AssertionError as e:
                print(f"[FAIL] {cls.__name__}.{m_name}: {e}")
                failed += 1
            except Exception as e:
                print(f"[ERR]  {cls.__name__}.{m_name}: {e}")
                failed += 1

    print("=" * 65)
    print(f"Results: {passed} passed, {failed} failed out of {total} tests")
    print("=" * 65)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(run_all_tests())
