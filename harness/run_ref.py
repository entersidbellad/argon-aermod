#!/usr/bin/env python3
"""Run AERMOD reference binary on test cases."""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


class AERMODRunner:
    """Runs the AERMOD reference binary."""
    
    def __init__(self, binary_path: Optional[Path] = None):
        if binary_path is None:
            # Try to find the binary
            script_dir = Path(__file__).parent
            binary_path = script_dir.parent / "ref" / "aermod"
        
        self.binary_path = Path(binary_path)
        if not self.binary_path.exists():
            raise FileNotFoundError(
                f"AERMOD binary not found at {self.binary_path}\n"
                f"Run ref/build_aermod.sh first"
            )
    
    def run_case(
        self,
        case_dir: Path,
        output_dir: Optional[Path] = None,
        debug: bool = False,
        verbose: bool = False
    ) -> subprocess.CompletedProcess:
        """
        Run AERMOD on a test case.
        
        Args:
            case_dir: Directory containing .inp file and met files
            output_dir: Where to write outputs (default: case_dir)
            debug: Enable DEBUGOPT output (MODEL METEOR PRIME)
            verbose: Print command and output
            
        Returns:
            CompletedProcess with return code and output
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
        
        # Set up output directory
        if output_dir is None:
            output_dir = case_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create working directory with case files
        work_dir = output_dir / "aermod_run"
        if work_dir.exists():
            shutil.rmtree(work_dir)
        work_dir.mkdir(parents=True)
        
        # Copy input file and met files to work directory
        shutil.copy2(inp_file, work_dir / inp_file.name)
        for met_file in case_dir.glob("*.sfc"):
            shutil.copy2(met_file, work_dir / met_file.name)
        for met_file in case_dir.glob("*.pfl"):
            shutil.copy2(met_file, work_dir / met_file.name)
        
        # Modify input file to enable debug output if requested
        work_inp = work_dir / inp_file.name
        if debug:
            self._enable_debug(work_inp)
        
        # Run AERMOD
        cmd = [str(self.binary_path), str(work_inp.name)]
        
        if verbose:
            print(f"Running: {' '.join(cmd)}")
            print(f"Working directory: {work_dir}")
        
        result = subprocess.run(
            cmd,
            cwd=work_dir,
            capture_output=True,
            text=True
        )
        
        if verbose:
            print(f"Return code: {result.returncode}")
            if result.stdout:
                print("STDOUT:")
                print(result.stdout)
            if result.stderr:
                print("STDERR:")
                print(result.stderr)
        
        # Copy outputs back to output_dir
        for out_file in work_dir.glob("*.OUT"):
            shutil.copy2(out_file, output_dir / out_file.name)
        for out_file in work_dir.glob("*.out"):
            shutil.copy2(out_file, output_dir / out_file.name)
        
        return result
    
    def _enable_debug(self, inp_file: Path) -> None:
        """
        Add DEBUGOPT keywords to input file for intermediate output.
        
        Adds: CO DEBUGOPT MODEL METEOR PRIME
        """
        with open(inp_file, 'r') as f:
            lines = f.readlines()
        
        # Find the CO STARTING section
        co_start_idx = None
        for i, line in enumerate(lines):
            if line.strip().startswith('CO STARTING'):
                co_start_idx = i
                break
        
        if co_start_idx is None:
            print("Warning: Could not find CO STARTING, debug output may not work")
            return
        
        # Insert DEBUGOPT lines after CO STARTING
        debug_lines = [
            "CO DEBUGOPT MODEL\n",
            "CO DEBUGOPT METEOR\n",
            "CO DEBUGOPT PRIME\n",
        ]
        
        # Check if debug options already present
        has_debug = any('DEBUGOPT' in line for line in lines)
        if not has_debug:
            for i, debug_line in enumerate(debug_lines):
                lines.insert(co_start_idx + 1 + i, debug_line)
        
        with open(inp_file, 'w') as f:
            f.writelines(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Run AERMOD reference binary on test cases'
    )
    parser.add_argument(
        'case',
        type=Path,
        help='Path to case directory or case name in cases/'
    )
    parser.add_argument(
        '--binary',
        type=Path,
        help='Path to AERMOD binary (default: ../ref/aermod)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output directory (default: case directory)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable DEBUGOPT output (MODEL METEOR PRIME)'
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
        # Try to find in cases/ subdirectories
        script_dir = Path(__file__).parent
        cases_dir = script_dir.parent / "cases"
        
        for subdir in ['epa', 'derived', 'holdout']:
            candidate = cases_dir / subdir / case_path
            if candidate.is_dir():
                case_path = candidate
                break
        else:
            # Try as relative path
            case_path = case_path.resolve()
    
    if not case_path.is_dir():
        print(f"Error: Case directory not found: {case_path}", file=sys.stderr)
        return 1
    
    try:
        runner = AERMODRunner(args.binary)
        result = runner.run_case(
            case_path,
            output_dir=args.output,
            debug=args.debug,
            verbose=args.verbose
        )
        
        if result.returncode == 0:
            print(f"✓ AERMOD completed successfully for {case_path.name}")
            if args.output:
                print(f"  Outputs written to: {args.output}")
            else:
                print(f"  Outputs written to: {case_path}")
        else:
            print(f"✗ AERMOD failed with return code {result.returncode}", file=sys.stderr)
            return result.returncode
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
