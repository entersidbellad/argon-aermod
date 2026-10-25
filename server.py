#!/usr/bin/env python3
"""
Minimal server for AERMOD port UI.

Provides REST API for:
- GET /runs - List all port runs
- POST /run - Trigger a new port
- POST /certify - Certify verification results
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("FastAPI not installed. Install with: pip install fastapi uvicorn")
    sys.exit(1)


app = FastAPI(title="AERMOD Port Server")

# Paths
SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR
UI_DIR = ROOT_DIR / "ui"
RUNS_DIR = ROOT_DIR / "agent" / "runs"
CASES_DIR = ROOT_DIR / "cases"


@app.get("/api/runs")
def list_runs() -> List[Dict]:
    """List all port runs."""
    runs = []
    
    if not RUNS_DIR.exists():
        return runs
    
    for run_dir in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        
        # Load metadata
        metadata_file = run_dir / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        else:
            metadata = {}
        
        # Check if split
        port_exists = (ROOT_DIR / "port" / "aermod_py" / "__init__.py").exists()
        
        runs.append({
            'id': run_dir.name,
            'timestamp': metadata.get('timestamp', ''),
            'model': metadata.get('model', 'unknown'),
            'tier': 'B' if 'tier_B' in run_dir.name else 'A',
            'duration': metadata.get('duration_seconds', 0),
            'output_tokens': metadata.get('usage', {}).get('output_tokens', 0),
            'port_exists': port_exists,
        })
    
    return runs


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Dict:
    """Get details for one run."""
    run_dir = RUNS_DIR / run_id
    
    if not run_dir.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Load metadata
    metadata_file = run_dir / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
    else:
        metadata = {}
    
    # Check files
    has_output = (run_dir / "raw_output.txt").exists()
    has_prompt = (run_dir / "prompt.txt").exists()
    
    return {
        'id': run_id,
        'metadata': metadata,
        'has_output': has_output,
        'has_prompt': has_prompt,
    }


@app.get("/api/test-results")
def get_test_results() -> Dict:
    """Get current test results."""
    # This would actually run the tests or read cached results
    # For now, return a stub
    
    tier_a_cases = [
        'aertest_nobldg',
        'CAPPED_STACK2',
        'CAPPED_STACK2C0',
        'CAPPED_STACK2CE',
        'HRDOW_STACK1',
        'FLATELEV_FLAT_STK',
    ]
    
    tier_b_cases = tier_a_cases + [
        'AERTEST',
        'CAPPED_STACK1C0',
        'ALLSRCS_STACKDW',
    ]
    
    # Stub results - real implementation would run tests
    results = {}
    for case in tier_b_cases:
        results[case] = {
            'epa_pass': None,  # Not yet run
            'strict_pass': None,
            'stable_pass': None,
            'convective_pass': None,
        }
    
    return {
        'tier_a': tier_a_cases,
        'tier_b': tier_b_cases,
        'results': results,
        'compare_hash': 'not_computed',
    }


@app.post("/api/run")
def trigger_run(tier: str = 'A', thinking: str = 'high') -> Dict:
    """Trigger a new port run."""
    if tier not in ['A', 'B']:
        raise HTTPException(status_code=400, detail="tier must be A or B")
    
    if thinking not in ['low', 'medium', 'high', 'xhigh', 'max']:
        raise HTTPException(status_code=400, detail="Invalid thinking level")
    
    # This would actually call agent/port.py
    # For now, return a stub response
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f'tier_{tier}_{timestamp}'
    
    return {
        'run_id': run_id,
        'status': 'started',
        'message': 'Port run triggered (stub - implement agent/port.py call)'
    }


@app.post("/api/certify")
def certify_results(data: Dict) -> Dict:
    """Certify verification results."""
    # This would:
    # 1. Verify compare.py hash matches
    # 2. Verify all tests pass
    # 3. Verify git log shows agent commits
    # 4. Generate certification artifact
    
    return {
        'certified': False,
        'message': 'Certification not yet implemented'
    }


# Serve static UI files
if UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="static")


def main():
    """Run the server."""
    print("="*70)
    print("AERMOD Port Server")
    print("="*70)
    print(f"Root: {ROOT_DIR}")
    print(f"UI: {UI_DIR}")
    print(f"Runs: {RUNS_DIR}")
    print()
    print("Starting server on http://localhost:8000")
    print("  API: http://localhost:8000/api/runs")
    print("  UI:  http://localhost:8000/")
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == '__main__':
    main()
