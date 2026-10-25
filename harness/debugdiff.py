#!/usr/bin/env python3
"""
Find the first divergent intermediate variable between ref and port debug output.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_debug_output(path: Path) -> Dict[str, List[float]]:
    """
    Parse AERMOD DEBUGOPT output.
    
    Returns:
        Dict mapping variable names to lists of values
    """
    variables = {}
    
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('**'):
                continue
            
            # Parse debug output format
            # Typically: VARIABLE_NAME = value
            if '=' in line:
                parts = line.split('=')
                if len(parts) == 2:
                    var_name = parts[0].strip()
                    try:
                        value = float(parts[1].strip())
                        if var_name not in variables:
                            variables[var_name] = []
                        variables[var_name].append(value)
                    except ValueError:
                        continue
    
    return variables


def find_first_divergence(
    ref_vars: Dict[str, List[float]],
    port_vars: Dict[str, List[float]],
    tolerance: float = 1e-6
) -> Optional[Tuple[str, int, float, float]]:
    """
    Find the first variable that diverges between ref and port.
    
    Args:
        ref_vars: Reference variables
        port_vars: Port variables
        tolerance: Relative tolerance for comparison
        
    Returns:
        (variable_name, index, ref_value, port_value) or None
    """
    # Check all variables that appear in both
    common_vars = set(ref_vars.keys()) & set(port_vars.keys())
    
    # Sort for deterministic output
    for var_name in sorted(common_vars):
        ref_vals = ref_vars[var_name]
        port_vals = port_vars[var_name]
        
        # Compare element by element
        min_len = min(len(ref_vals), len(port_vals))
        
        for i in range(min_len):
            ref_val = ref_vals[i]
            port_val = port_vals[i]
            
            # Check if divergent
            if abs(ref_val) < 1e-10 and abs(port_val) < 1e-10:
                # Both essentially zero
                continue
            
            if abs(ref_val) < 1e-10:
                # Ref is zero but port is not
                if abs(port_val) > tolerance:
                    return (var_name, i, ref_val, port_val)
            else:
                # Compute relative difference
                rel_diff = abs((port_val - ref_val) / ref_val)
                if rel_diff > tolerance:
                    return (var_name, i, ref_val, port_val)
    
    return None


def print_divergence(
    var_name: str,
    index: int,
    ref_val: float,
    port_val: float
) -> None:
    """Print divergence information."""
    print(f"\n{'='*70}")
    print("FIRST DIVERGENCE FOUND")
    print(f"{'='*70}")
    print(f"Variable: {var_name}")
    print(f"Index: {index}")
    print(f"Reference: {ref_val:.10e}")
    print(f"Port: {port_val:.10e}")
    
    if abs(ref_val) > 1e-10:
        rel_diff = abs((port_val - ref_val) / ref_val)
        print(f"Relative difference: {rel_diff:.2e}")
    else:
        abs_diff = abs(port_val - ref_val)
        print(f"Absolute difference: {abs_diff:.2e}")


def main():
    parser = argparse.ArgumentParser(
        description='Find first divergent variable in debug output'
    )
    parser.add_argument(
        'ref',
        type=Path,
        help='Reference debug output file'
    )
    parser.add_argument(
        'port',
        type=Path,
        help='Port debug output file'
    )
    parser.add_argument(
        '--tolerance',
        type=float,
        default=1e-6,
        help='Relative tolerance (default: 1e-6)'
    )
    
    args = parser.parse_args()
    
    try:
        print("Parsing reference output...")
        ref_vars = parse_debug_output(args.ref)
        print(f"  Found {len(ref_vars)} variables")
        
        print("Parsing port output...")
        port_vars = parse_debug_output(args.port)
        print(f"  Found {len(port_vars)} variables")
        
        print("\nSearching for divergence...")
        result = find_first_divergence(ref_vars, port_vars, args.tolerance)
        
        if result is None:
            print("\n✓ No divergence found!")
            print("  Reference and port outputs match within tolerance.")
            return 0
        else:
            var_name, index, ref_val, port_val = result
            print_divergence(var_name, index, ref_val, port_val)
            return 1
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == '__main__':
    sys.exit(main())
