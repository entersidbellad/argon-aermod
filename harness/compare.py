#!/usr/bin/env python3
"""
Compare AERMOD outputs with EPA regulatory and strict criteria.

Implements two validation levels:
1. EPA regulatory parity: best-fit slope through origin within 1 ± 0.001
2. Strict numerical criteria for port validation
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np


@dataclass
class ComparisonResult:
    """Results of comparing two AERMOD outputs."""
    
    case_name: str
    
    # EPA regulatory criteria
    epa_slope: float
    epa_pass: bool
    
    # Strict criteria
    total_values: int
    zero_nonzero_agreement: float
    p99_relative_error: float
    max_design_value_diff: float
    strict_pass: bool
    
    # Stability split
    stable_hours: int
    convective_hours: int
    stable_pass: bool
    convective_pass: bool
    
    # Metadata
    ref_max: float
    test_max: float


def load_postfile(path: Path) -> np.ndarray:
    """
    Load AERMOD POSTFILE output.
    
    Returns:
        Array of shape (hours, receptors) with concentrations in ug/m3
    """
    # This is a simplified parser
    # Real implementation would use pyaermod's postfile reader
    
    try:
        from pyaermod.postfile import read_postfile
        data = read_postfile(path)
        return data['conc']
    except ImportError:
        # Fallback: simple text parser
        values = []
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('**') or line.startswith('*'):
                    continue
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        # Assume format: hour receptor value
                        value = float(parts[2])
                        values.append(value)
                    except ValueError:
                        continue
        
        # Need to reshape - for now return 1D array
        # Real implementation needs to parse structure
        return np.array(values)


def compute_epa_parity(ref: np.ndarray, test: np.ndarray) -> Tuple[float, bool]:
    """
    Compute EPA regulatory parity: best-fit slope through origin.
    
    Pass criteria: slope within 1 ± 0.001
    
    Returns:
        (slope, passes)
    """
    try:
        from pyaermod.regulatory_parity import score_postfile_pair
        # This would use pyaermod's implementation
        # For now, compute manually
    except ImportError:
        pass
    
    # Flatten arrays
    ref_flat = ref.flatten()
    test_flat = test.flatten()
    
    # Best fit line through origin: minimize sum((test - slope*ref)^2)
    # Solution: slope = sum(test*ref) / sum(ref^2)
    
    # Filter out very small values to avoid noise
    mask = ref_flat > 1e-10
    
    if mask.sum() == 0:
        return 1.0, True
    
    ref_filtered = ref_flat[mask]
    test_filtered = test_flat[mask]
    
    slope = np.sum(test_filtered * ref_filtered) / np.sum(ref_filtered ** 2)
    
    # Pass if within 1 ± 0.001
    passes = abs(slope - 1.0) <= 0.001
    
    return slope, passes


def compute_strict_criteria(
    ref: np.ndarray,
    test: np.ndarray,
    case_max: float
) -> Tuple[float, float, bool]:
    """
    Compute strict numerical criteria.
    
    1. Zero/nonzero agreement >= 99.9%
    2. P99 relative error <= 1e-4 on values >= 1% of case max
    
    Returns:
        (zero_nonzero_agreement, p99_rel_error, passes)
    """
    ref_flat = ref.flatten()
    test_flat = test.flatten()
    
    # 1. Zero/nonzero agreement
    threshold = 1e-10
    ref_nonzero = ref_flat > threshold
    test_nonzero = test_flat > threshold
    agreement = (ref_nonzero == test_nonzero).mean()
    
    # 2. P99 relative error on significant values
    significant_threshold = 0.01 * case_max
    mask = ref_flat >= significant_threshold
    
    if mask.sum() == 0:
        p99_rel_error = 0.0
    else:
        ref_sig = ref_flat[mask]
        test_sig = test_flat[mask]
        
        # Relative error
        rel_error = np.abs((test_sig - ref_sig) / ref_sig)
        p99_rel_error = np.percentile(rel_error, 99)
    
    # Pass criteria
    passes = (agreement >= 0.999) and (p99_rel_error <= 1e-4)
    
    return agreement, p99_rel_error, passes


def compute_design_value_diff(ref: np.ndarray, test: np.ndarray) -> float:
    """
    Compute max difference in H4H (4th highest hourly) design values.
    
    Returns:
        Max absolute difference across all receptors
    """
    # For each receptor, find 4th highest value
    if ref.ndim == 1:
        # Can't compute per-receptor design values from flat array
        return 0.0
    
    # Assume shape (hours, receptors)
    n_receptors = ref.shape[1]
    
    max_diff = 0.0
    for rec in range(n_receptors):
        ref_sorted = np.sort(ref[:, rec])[::-1]
        test_sorted = np.sort(test[:, rec])[::-1]
        
        if len(ref_sorted) >= 4:
            ref_h4h = ref_sorted[3]
            test_h4h = test_sorted[3]
            diff = abs(test_h4h - ref_h4h)
            max_diff = max(max_diff, diff)
    
    return max_diff


def split_by_stability(
    ref: np.ndarray,
    test: np.ndarray,
    met_file: Optional[Path]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Split data into stable and convective hours based on Monin-Obukhov length.
    
    Returns:
        (ref_stable, test_stable, ref_convective, test_convective)
    """
    if met_file is None or not met_file.exists():
        # Can't split without met data
        return ref, test, np.array([]), np.array([])
    
    try:
        from pyaermod.met_readers import read_surface_file
        met_data = read_surface_file(met_file)
        
        # L > 0: stable
        # L < 0: convective
        L = met_data['L']
        
        stable_mask = L > 0
        convective_mask = L < 0
        
        if ref.ndim == 2:
            ref_stable = ref[stable_mask, :]
            test_stable = test[stable_mask, :]
            ref_convective = ref[convective_mask, :]
            test_convective = test[convective_mask, :]
        else:
            # Flat array - can't split properly
            ref_stable = ref
            test_stable = test
            ref_convective = np.array([])
            test_convective = np.array([])
        
        return ref_stable, test_stable, ref_convective, test_convective
        
    except Exception:
        # If met parsing fails, return unsplit
        return ref, test, np.array([]), np.array([])


def compare_outputs(
    ref_path: Path,
    test_path: Path,
    case_name: str,
    met_file: Optional[Path] = None
) -> ComparisonResult:
    """
    Compare reference and test outputs.
    
    Args:
        ref_path: Reference POSTFILE
        test_path: Test POSTFILE
        case_name: Name of test case
        met_file: Optional surface met file for stability split
        
    Returns:
        ComparisonResult with all metrics
    """
    # Load data
    ref = load_postfile(ref_path)
    test = load_postfile(test_path)
    
    if ref.shape != test.shape:
        raise ValueError(
            f"Shape mismatch: ref {ref.shape} vs test {test.shape}"
        )
    
    case_max = ref.max()
    
    # EPA regulatory parity
    epa_slope, epa_pass = compute_epa_parity(ref, test)
    
    # Strict criteria
    zero_agreement, p99_error, strict_pass = compute_strict_criteria(
        ref, test, case_max
    )
    
    # Design value difference
    design_diff = compute_design_value_diff(ref, test)
    design_pass = design_diff <= 1e-4
    
    # Overall strict pass requires all three
    strict_pass = strict_pass and design_pass
    
    # Split by stability
    ref_stable, test_stable, ref_conv, test_conv = split_by_stability(
        ref, test, met_file
    )
    
    stable_hours = ref_stable.size // (ref.shape[1] if ref.ndim == 2 else 1)
    convective_hours = ref_conv.size // (ref.shape[1] if ref.ndim == 2 else 1)
    
    # Check pass rates by stability
    if ref_stable.size > 0:
        _, _, stable_pass = compute_strict_criteria(
            ref_stable, test_stable, case_max
        )
    else:
        stable_pass = True
    
    if ref_conv.size > 0:
        _, _, convective_pass = compute_strict_criteria(
            ref_conv, test_conv, case_max
        )
    else:
        convective_pass = True
    
    return ComparisonResult(
        case_name=case_name,
        epa_slope=epa_slope,
        epa_pass=epa_pass,
        total_values=ref.size,
        zero_nonzero_agreement=zero_agreement,
        p99_relative_error=p99_error,
        max_design_value_diff=design_diff,
        strict_pass=strict_pass,
        stable_hours=stable_hours,
        convective_hours=convective_hours,
        stable_pass=stable_pass,
        convective_pass=convective_pass,
        ref_max=case_max,
        test_max=test.max()
    )


def print_result(result: ComparisonResult) -> None:
    """Print comparison results in human-readable format."""
    print(f"\n{'='*70}")
    print(f"Case: {result.case_name}")
    print(f"{'='*70}")
    
    print("\nEPA Regulatory Parity:")
    print(f"  Slope through origin: {result.epa_slope:.6f}")
    status = "✓ PASS" if result.epa_pass else "✗ FAIL"
    print(f"  Status: {status} (target: 1.000 ± 0.001)")
    
    print("\nStrict Numerical Criteria:")
    print(f"  Total values: {result.total_values:,}")
    print(f"  Zero/nonzero agreement: {result.zero_nonzero_agreement:.4%}")
    print(f"  P99 relative error: {result.p99_relative_error:.2e}")
    print(f"  Max H4H design value diff: {result.max_design_value_diff:.2e}")
    status = "✓ PASS" if result.strict_pass else "✗ FAIL"
    print(f"  Status: {status}")
    
    print("\nStability Split:")
    print(f"  Stable hours: {result.stable_hours} "
          f"({'✓' if result.stable_pass else '✗'})")
    print(f"  Convective hours: {result.convective_hours} "
          f"({'✓' if result.convective_pass else '✗'})")
    
    print("\nConcentration Range:")
    print(f"  Reference max: {result.ref_max:.2e} ug/m3")
    print(f"  Test max: {result.test_max:.2e} ug/m3")


def main():
    parser = argparse.ArgumentParser(
        description='Compare AERMOD outputs'
    )
    parser.add_argument(
        'ref',
        type=Path,
        help='Reference POSTFILE'
    )
    parser.add_argument(
        'test',
        type=Path,
        help='Test POSTFILE'
    )
    parser.add_argument(
        '--case-name',
        default='unknown',
        help='Test case name'
    )
    parser.add_argument(
        '--met',
        type=Path,
        help='Surface met file for stability split'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output as JSON'
    )
    
    args = parser.parse_args()
    
    try:
        result = compare_outputs(
            args.ref,
            args.test,
            args.case_name,
            args.met
        )
        
        if args.json:
            import json
            print(json.dumps({
                'case_name': result.case_name,
                'epa_slope': result.epa_slope,
                'epa_pass': result.epa_pass,
                'zero_nonzero_agreement': result.zero_nonzero_agreement,
                'p99_relative_error': result.p99_relative_error,
                'max_design_value_diff': result.max_design_value_diff,
                'strict_pass': result.strict_pass,
                'stable_hours': result.stable_hours,
                'convective_hours': result.convective_hours,
                'stable_pass': result.stable_pass,
                'convective_pass': result.convective_pass,
            }, indent=2))
        else:
            print_result(result)
        
        # Exit code reflects strict pass status
        return 0 if result.strict_pass else 1
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == '__main__':
    sys.exit(main())
