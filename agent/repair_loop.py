#!/usr/bin/env python3
"""
Automated repair loop for AERMOD port.

Strategy:
1. Run all tier A/B test cases
2. For first failure, generate failure packet (<= 30K tokens)
3. Call Gemini 4 Argon with targeted repair prompt
4. Apply patch and re-test all cases
5. Keep patch only if no regressions
6. Escalate to full-context consult after 3 failures on same variable
7. Budget: 10 iterations or 60 minutes per tier
"""

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Test cases by tier
TIER_A_CASES = [
    'aertest_nobldg',
    'CAPPED_STACK2',
    'CAPPED_STACK2C0',
    'CAPPED_STACK2CE',
    'HRDOW_STACK1',
    'FLATELEV_FLAT_STK',
]

TIER_B_CASES = TIER_A_CASES + [
    'AERTEST',
    'CAPPED_STACK1C0',
    'ALLSRCS_STACKDW',
]


class RepairLoop:
    """Automated repair loop for port divergences."""
    
    def __init__(
        self,
        tier: str,
        max_iterations: int = 10,
        max_duration_minutes: int = 60
    ):
        self.tier = tier
        self.max_iterations = max_iterations
        self.max_duration = timedelta(minutes=max_duration_minutes)
        self.start_time = datetime.now()
        
        self.cases = TIER_B_CASES if tier == 'B' else TIER_A_CASES
        self.divergence_counter = Counter()  # Track variable divergence counts
        
        self.script_dir = Path(__file__).parent
        self.root_dir = self.script_dir.parent
        self.harness_dir = self.root_dir / 'harness'
        self.port_dir = self.root_dir / 'port' / 'aermod_py'
    
    def run_all_tests(self) -> Dict[str, bool]:
        """
        Run all tier test cases.
        
        Returns:
            Dict mapping case name to pass/fail
        """
        results = {}
        
        print(f"\nRunning {len(self.cases)} test cases...")
        
        for case in self.cases:
            print(f"  Testing {case}...", end=' ', flush=True)
            
            # Run port
            try:
                subprocess.run(
                    [
                        sys.executable,
                        str(self.harness_dir / 'run_port.py'),
                        case,
                        '--output', f'/tmp/aermod_port_{case}'
                    ],
                    check=True,
                    capture_output=True
                )
                
                # Compare with reference
                result = subprocess.run(
                    [
                        sys.executable,
                        str(self.harness_dir / 'compare.py'),
                        f'/tmp/aermod_ref_{case}/POSTFILE.OUT',
                        f'/tmp/aermod_port_{case}/POSTFILE.OUT',
                        '--case-name', case
                    ],
                    capture_output=True
                )
                
                passed = result.returncode == 0
                results[case] = passed
                print("✓" if passed else "✗")
                
            except Exception as e:
                print(f"✗ (error: {e})")
                results[case] = False
        
        n_passed = sum(results.values())
        print(f"\nResults: {n_passed}/{len(results)} passed")
        
        return results
    
    def find_first_failure(
        self,
        results: Dict[str, bool]
    ) -> Optional[Tuple[str, str, int, float, float]]:
        """
        Find first failing case and divergent variable.
        
        Returns:
            (case_name, variable_name, hour, ref_value, port_value) or None
        """
        for case, passed in results.items():
            if not passed:
                # Run with debug to find divergence
                try:
                    # Run ref with debug
                    subprocess.run(
                        [
                            sys.executable,
                            str(self.harness_dir / 'run_ref.py'),
                            case,
                            '--debug',
                            '--output', f'/tmp/aermod_ref_debug_{case}'
                        ],
                        check=True,
                        capture_output=True
                    )
                    
                    # Run port with debug
                    subprocess.run(
                        [
                            sys.executable,
                            str(self.harness_dir / 'run_port.py'),
                            case,
                            '--debug',
                            '--output', f'/tmp/aermod_port_debug_{case}'
                        ],
                        check=True,
                        capture_output=True
                    )
                    
                    # Find divergence
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(self.harness_dir / 'debugdiff.py'),
                            f'/tmp/aermod_ref_debug_{case}/debug.out',
                            f'/tmp/aermod_port_debug_{case}/debug.out'
                        ],
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 1:  # Divergence found
                        # Parse output to extract variable info
                        # This is a simplified version - real implementation
                        # would parse debugdiff output properly
                        lines = result.stdout.split('\n')
                        var_name = None
                        for line in lines:
                            if line.startswith('Variable:'):
                                var_name = line.split(':')[1].strip()
                                break
                        
                        if var_name:
                            return (case, var_name, 0, 0.0, 0.0)
                    
                except Exception as e:
                    print(f"Warning: Could not debug {case}: {e}")
                    continue
        
        return None
    
    def generate_failure_packet(
        self,
        case: str,
        variable: str,
        hour: int,
        ref_value: float,
        port_value: float
    ) -> str:
        """
        Generate repair prompt with failure context.
        
        Returns:
            Repair prompt string (<= 30K tokens target)
        """
        # Load repair template
        template_path = self.root_dir / 'prompts' / 'repair.md'
        with open(template_path, 'r') as f:
            template = f.read()
        
        # Get Fortran source for divergent subroutine
        # This requires the subroutine index from packing
        fortran_source = self._get_subroutine_source(variable)
        
        # Get Python source for the function
        python_source = self._get_python_function(variable)
        
        # Get met data for the hour
        met_summary = self._get_met_summary(case, hour)
        
        # Fill template
        rel_diff = abs((port_value - ref_value) / ref_value) if ref_value != 0 else float('inf')
        
        prompt = template.format(
            case_name=case,
            hour=hour,
            variable_name=variable,
            L=met_summary.get('L', 0),
            ustar=met_summary.get('ustar', 0),
            wstar=met_summary.get('wstar', 0),
            zi=met_summary.get('zi', 0),
            stability='stable' if met_summary.get('L', 0) > 0 else 'convective',
            ref_value=ref_value,
            port_value=port_value,
            rel_diff=rel_diff,
            fortran_source=fortran_source,
            python_source=python_source
        )
        
        return prompt
    
    def _get_subroutine_source(self, variable: str) -> str:
        """Extract Fortran source for subroutine computing this variable."""
        # Simplified - real implementation would use the subroutine index
        # from pack.py to find the right file and line numbers
        return "! Fortran source would be extracted here\n"
    
    def _get_python_function(self, variable: str) -> str:
        """Extract Python function that should compute this variable."""
        return "# Python source would be extracted here\n"
    
    def _get_met_summary(self, case: str, hour: int) -> Dict:
        """Get meteorology summary for a specific hour."""
        # Simplified - real implementation would parse met files
        return {
            'L': 100.0,
            'ustar': 0.3,
            'wstar': 0.0,
            'zi': 1000.0
        }
    
    def apply_patch(self, patch_content: str, iteration: int) -> bool:
        """
        Apply a repair patch to the port.
        
        Returns:
            True if applied successfully
        """
        # Parse patch output (FILE markers)
        # This uses the same splitter as split.py
        from split import OutputSplitter
        
        splitter = OutputSplitter()
        
        try:
            files = splitter.parse_output(patch_content)
            
            # Write files
            for filepath, content in files:
                full_path = self.port_dir / filepath
                with open(full_path, 'w') as f:
                    f.write(content)
            
            print(f"  Applied patch to {len(files)} file(s)")
            return True
            
        except Exception as e:
            print(f"  Failed to apply patch: {e}")
            return False
    
    def commit_repair(self, iteration: int, variable: str, hypothesis: str):
        """Commit the repair with descriptive message."""
        message = f"repair {iteration}: {variable}: {hypothesis}"
        
        subprocess.run(
            ['git', 'add', 'port/aermod_py/'],
            cwd=self.root_dir,
            check=True
        )
        
        subprocess.run(
            ['git', 'commit', '-m', message, '--author', 'Argon Repair <agent@argon>'],
            cwd=self.root_dir,
            check=True
        )
        
        print(f"  ✓ Committed: {message}")
    
    def run_iteration(self, iteration: int) -> bool:
        """
        Run one repair iteration.
        
        Returns:
            True if repair was successful, False if should continue
        """
        print(f"\n{'='*70}")
        print(f"Repair Iteration {iteration + 1}/{self.max_iterations}")
        print(f"{'='*70}")
        
        # Run all tests
        results = self.run_all_tests()
        
        if all(results.values()):
            print("\n✓ All tests passing! Repair complete.")
            return True
        
        # Find first failure
        failure = self.find_first_failure(results)
        if failure is None:
            print("\n✗ Tests failing but no divergence found")
            return False
        
        case, variable, hour, ref_val, port_val = failure
        print(f"\nDivergence: {variable} in {case} (hour {hour})")
        
        # Track divergence count
        self.divergence_counter[variable] += 1
        
        # Check if we should escalate
        if self.divergence_counter[variable] >= 3:
            print(f"⚠ Variable {variable} diverged 3 times, escalating to consult")
            return self._escalate_to_consult(variable)
        
        # Generate failure packet
        print("Generating repair prompt...")
        prompt = self.generate_failure_packet(case, variable, hour, ref_val, port_val)
        
        # Call Argon for repair
        print("Requesting repair from Gemini 4 Argon...")
        patch = self._call_argon_repair(prompt)
        
        if patch is None:
            print("✗ Repair generation failed")
            return False
        
        # Extract hypothesis from patch
        hypothesis = self._extract_hypothesis(patch)
        
        # Apply patch
        if not self.apply_patch(patch, iteration):
            return False
        
        # Test for regressions
        print("Testing for regressions...")
        new_results = self.run_all_tests()
        
        # Count changes
        improvements = sum(
            1 for case in results
            if not results[case] and new_results[case]
        )
        regressions = sum(
            1 for case in results
            if results[case] and not new_results[case]
        )
        
        if regressions > 0:
            print(f"✗ Patch caused {regressions} regression(s), reverting")
            subprocess.run(
                ['git', 'reset', '--hard', 'HEAD'],
                cwd=self.root_dir,
                check=True
            )
            return False
        
        if improvements > 0:
            print(f"✓ Patch fixed {improvements} case(s), no regressions")
            self.commit_repair(iteration, variable, hypothesis)
        else:
            print("⚠ Patch had no effect")
        
        return False  # Continue to next iteration
    
    def _call_argon_repair(self, prompt: str) -> Optional[str]:
        """Call Gemini 4 Argon for repair."""
        # Similar to port.py but with repair prompt
        import google.generativeai as genai
        
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            print("Error: GEMINI_API_KEY not set", file=sys.stderr)
            return None
        
        genai.configure(api_key=api_key)
        
        try:
            model = genai.GenerativeModel('gemini-4-argon-high')
            response = model.generate_content(
                prompt,
                generation_config={'temperature': 0.0}
            )
            
            return response.text
            
        except Exception as e:
            print(f"Error calling Argon: {e}", file=sys.stderr)
            return None
    
    def _extract_hypothesis(self, patch: str) -> str:
        """Extract hypothesis from patch output."""
        # Look for === HYPOTHESIS === section
        lines = patch.split('\n')
        in_hypothesis = False
        hypothesis_lines = []
        
        for line in lines:
            if '=== HYPOTHESIS ===' in line:
                in_hypothesis = True
                continue
            if in_hypothesis:
                if line.startswith('==='):
                    break
                hypothesis_lines.append(line)
        
        return ' '.join(hypothesis_lines).strip()[:100]
    
    def _escalate_to_consult(self, variable: str) -> bool:
        """Escalate to full-context consult for persistent divergence."""
        print("\nEscalating to full-context consult...")
        # Load consult template and packed context
        # Call Argon with full context
        # This is a more expensive operation
        return False  # Simplified for now
    
    def run(self) -> int:
        """
        Run the complete repair loop.
        
        Returns:
            Exit code (0 = success, 1 = failure)
        """
        print("="*70)
        print(f"AERMOD Repair Loop - Tier {self.tier}")
        print("="*70)
        print(f"Max iterations: {self.max_iterations}")
        print(f"Max duration: {self.max_duration.total_seconds() / 60:.0f} minutes")
        print(f"Test cases: {len(self.cases)}")
        
        for iteration in range(self.max_iterations):
            # Check time budget
            elapsed = datetime.now() - self.start_time
            if elapsed > self.max_duration:
                print(f"\n⚠ Time budget exceeded ({elapsed.total_seconds() / 60:.1f} min)")
                break
            
            # Run iteration
            if self.run_iteration(iteration):
                return 0  # Success
        
        print("\n✗ Repair loop exhausted without complete fix")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description='Automated repair loop for AERMOD port'
    )
    parser.add_argument(
        '--tier',
        choices=['A', 'B'],
        default='A',
        help='Port tier'
    )
    parser.add_argument(
        '--max-iterations',
        type=int,
        default=10,
        help='Max repair iterations (default: 10)'
    )
    parser.add_argument(
        '--max-minutes',
        type=int,
        default=60,
        help='Max duration in minutes (default: 60)'
    )
    
    args = parser.parse_args()
    
    try:
        loop = RepairLoop(
            args.tier,
            max_iterations=args.max_iterations,
            max_duration_minutes=args.max_minutes
        )
        return loop.run()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    import os
    sys.exit(main())
