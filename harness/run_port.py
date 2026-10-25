#!/usr/bin/env python3
"""Run AERMOD Python port on test cases."""

import argparse
import sys
from pathlib import Path
from typing import Optional

# Add port directory to path
SCRIPT_DIR = Path(__file__).parent
PORT_DIR = SCRIPT_DIR.parent / "port"
sys.path.insert(0, str(PORT_DIR))


class PortRunner:
    """Runs the AERMOD Python port."""
    
    def __init__(self):
        try:
            from aermod_py import run_case
            self.run_case = run_case
        except ImportError as e:
            raise ImportError(
                f"Could not import aermod_py: {e}\n"
                f"The port must be generated first by running agent/port.py"
            ) from e
    
    def run_case_file(
        self,
        case_dir: Path,
        output_dir: Optional[Path] = None,
        debug: bool = False,
        verbose: bool = False
    ) -> dict:
        """
        Run the Python port on a test case.
        
        Args:
            case_dir: Directory containing .inp file and met files
            output_dir: Where to write outputs (default: case_dir)
            debug: Enable debug output (intermediates)
            verbose: Print progress
            
        Returns:
            Result dict with conc[hour, receptor] and metadata
        """
        case_dir = Path(case_dir)
        if not case_dir.is_dir():
            raise ValueError(f"Case directory not found: {case_dir}")
        
        # Find the .inp file
        inp_files = list(case_dir.glob("*.inp"))
        if not inp_files:
            raise ValueError(f"No .inp file found in {case_dir}")
        if len(inp_files) > 1:
            raise ValueError(f"Multiple .inp files found in {case_dir}: {inp_files}")
        
        inp_file = inp_files[0]
        
        # Find met files
        sfc_files = list(case_dir.glob("*.sfc"))
        pfl_files = list(case_dir.glob("*.pfl"))
        
        if not sfc_files:
            raise ValueError(f"No .sfc file found in {case_dir}")
        
        if verbose:
            print(f"Running port on: {case_dir.name}")
            print(f"  Input: {inp_file.name}")
            print(f"  Met files: {len(sfc_files)} .sfc, {len(pfl_files)} .pfl")
        
        # Parse input file and run
        # Note: This assumes pyaermod is available for input parsing
        try:
            from pyaermod import input_reader
        except ImportError:
            raise ImportError(
                "pyaermod is required for input parsing. "
                "Install with: pip install pyaermod==2.2.0"
            )
        
        # Parse the input file
        project = input_reader.parse_inp(inp_file)
        
        # Parse met data
        met_data = {
            'sfc': sfc_files[0],
            'pfl': pfl_files[0] if pfl_files else None
        }
        
        # Extract point sources only (per scope)
        sources = [s for s in project.sources if s.type == 'POINT']
        
        if verbose:
            print(f"  Point sources: {len(sources)}")
        
        # Run the port
        result = self.run_case(
            project=project,
            met=met_data,
            sources=sources,
            debug=debug
        )
        
        if verbose:
            print(f"  Completed: {result['conc'].shape[0]} hours, "
                  f"{result['conc'].shape[1]} receptors")
        
        # Write output if requested
        if output_dir:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            self._write_postfile(result, output_dir / "POSTFILE.OUT", project)
        
        return result
    
    def _write_postfile(self, result: dict, output_path: Path, project) -> None:
        """Write results in AERMOD POSTFILE format."""
        # This is a simplified implementation
        # Real implementation would use pyaermod's postfile writer
        import numpy as np
        
        conc = result['conc']
        
        with open(output_path, 'w') as f:
            f.write("** AERMOD Python Port Output **\n")
            f.write(f"** {conc.shape[0]} hours, {conc.shape[1]} receptors **\n")
            
            # Write concentration matrix
            for hour_idx in range(conc.shape[0]):
                for rec_idx in range(conc.shape[1]):
                    value = conc[hour_idx, rec_idx]
                    # Simplified format: hour, receptor, concentration
                    f.write(f"{hour_idx+1:6d} {rec_idx+1:6d} {value:13.5E}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Run AERMOD Python port on test cases'
    )
    parser.add_argument(
        'case',
        type=Path,
        help='Path to case directory or case name in cases/'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output directory (default: case directory)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug output (intermediates)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Resolve case path
    case_path = args.case
    if not case_path.is_absolute():
        script_dir = Path(__file__).parent
        cases_dir = script_dir.parent / "cases"
        
        for subdir in ['epa', 'derived', 'holdout']:
            candidate = cases_dir / subdir / case_path
            if candidate.is_dir():
                case_path = candidate
                break
        else:
            case_path = case_path.resolve()
    
    if not case_path.is_dir():
        print(f"Error: Case directory not found: {case_path}", file=sys.stderr)
        return 1
    
    try:
        runner = PortRunner()
        result = runner.run_case_file(
            case_path,
            output_dir=args.output,
            debug=args.debug,
            verbose=args.verbose
        )
        
        print(f"✓ Port completed successfully for {case_path.name}")
        print(f"  Shape: {result['conc'].shape}")
        if args.output:
            print(f"  Output written to: {args.output}")
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        if args.verbose:
            traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
