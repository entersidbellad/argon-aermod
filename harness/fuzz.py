#!/usr/bin/env python3
"""
Generate random AERMOD point-source test cases.

The oracle is our compiled reference binary.
"""

import argparse
import random
import sys
from pathlib import Path
from typing import List, Tuple


class FuzzGenerator:
    """Generate random AERMOD input decks."""
    
    def __init__(self, seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)
    
    def generate_point_source(
        self,
        source_id: str = "STACK1"
    ) -> Tuple[float, float, float, float, float, float, float]:
        """
        Generate random point source parameters.
        
        Returns:
            (x, y, base_elev, stack_height, stack_diam, exit_vel, exit_temp)
        """
        # Receptor grid: 100m x 100m centered at origin
        # Sources: within 500m of origin
        x = random.uniform(-500, 500)
        y = random.uniform(-500, 500)
        
        # Base elevation: 0-100m
        base_elev = random.uniform(0, 100)
        
        # Stack height: 10-100m
        stack_height = random.uniform(10, 100)
        
        # Stack diameter: 0.5-5m
        stack_diam = random.uniform(0.5, 5.0)
        
        # Exit velocity: 5-30 m/s
        exit_vel = random.uniform(5, 30)
        
        # Exit temperature: 300-500 K
        exit_temp = random.uniform(300, 500)
        
        return (x, y, base_elev, stack_height, stack_diam, exit_vel, exit_temp)
    
    def generate_receptors(
        self,
        n_receptors: int = 25,
        grid_size: float = 1000.0
    ) -> List[Tuple[float, float, float]]:
        """
        Generate receptor grid.
        
        Returns:
            List of (x, y, z_flag) tuples
        """
        receptors = []
        
        # Regular grid
        n_side = int(n_receptors ** 0.5)
        spacing = grid_size / (n_side - 1) if n_side > 1 else 0
        
        for i in range(n_side):
            for j in range(n_side):
                x = -grid_size/2 + i * spacing
                y = -grid_size/2 + j * spacing
                z_flag = 0.0  # Ground level
                receptors.append((x, y, z_flag))
        
        return receptors
    
    def generate_input_deck(
        self,
        output_path: Path,
        n_sources: int = 3,
        n_receptors: int = 25,
        emission_rate: float = 10.0
    ) -> None:
        """
        Generate a complete AERMOD input deck.
        
        Args:
            output_path: Where to write the .inp file
            n_sources: Number of point sources
            n_receptors: Number of receptors
            emission_rate: Emission rate in g/s
        """
        sources = []
        for i in range(n_sources):
            source_id = f"STACK{i+1}"
            params = self.generate_point_source(source_id)
            sources.append((source_id, params, emission_rate))
        
        receptors = self.generate_receptors(n_receptors)
        
        # Write input deck
        with open(output_path, 'w') as f:
            # Title and control pathway
            f.write("CO STARTING\n")
            f.write("   TITLEONE  Fuzz-generated test case\n")
            f.write("   MODELOPT  CONC FLAT\n")
            f.write("   AVERTIME  1\n")
            f.write("   POLLUTID  OTHER\n")
            f.write("   RUNORNOT  RUN\n")
            f.write("   ERRORFIL  errors.out\n")
            f.write("CO FINISHED\n\n")
            
            # Source pathway
            f.write("SO STARTING\n")
            for source_id, params, emis in sources:
                x, y, base_elev, height, diam, vel, temp = params
                f.write(f"   LOCATION  {source_id}  POINT  "
                       f"{x:.2f} {y:.2f} {base_elev:.2f}\n")
                f.write(f"   SRCPARAM  {source_id}  {emis:.6f}  "
                       f"{height:.2f}  {temp:.2f}  {vel:.2f}  {diam:.2f}\n")
                f.write(f"   SRCGROUP  ALL\n")
            f.write("SO FINISHED\n\n")
            
            # Receptor pathway
            f.write("RE STARTING\n")
            for i, (x, y, z) in enumerate(receptors):
                rec_id = f"REC{i+1}"
                f.write(f"   DISCCART  {x:.2f} {y:.2f} {z:.2f}\n")
            f.write("RE FINISHED\n\n")
            
            # Meteorology pathway (will need to be updated with actual met files)
            f.write("ME STARTING\n")
            f.write("   SURFFILE  fuzz.sfc\n")
            f.write("   PROFFILE  fuzz.pfl\n")
            f.write("   SURFDATA  99999  2020\n")
            f.write("   UAIRDATA  99999  2020\n")
            f.write("   SITEDATA  99999  2020\n")
            f.write("   PROFBASE  0.0\n")
            f.write("ME FINISHED\n\n")
            
            # Output pathway
            f.write("OU STARTING\n")
            f.write("   RECTABLE  ALLAVE  FIRST\n")
            f.write("   MAXTABLE  ALLAVE  50\n")
            f.write("   PLOTFILE  1  ALL  FIRST  fuzz_plot.dat\n")
            f.write("OU FINISHED\n")


def main():
    parser = argparse.ArgumentParser(
        description='Generate fuzz test cases for AERMOD'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('fuzz_test.inp'),
        help='Output .inp file path'
    )
    parser.add_argument(
        '--n-sources',
        type=int,
        default=3,
        help='Number of point sources (default: 3)'
    )
    parser.add_argument(
        '--n-receptors',
        type=int,
        default=25,
        help='Number of receptors (default: 25)'
    )
    parser.add_argument(
        '--emission-rate',
        type=float,
        default=10.0,
        help='Emission rate in g/s (default: 10.0)'
    )
    parser.add_argument(
        '--seed',
        type=int,
        help='Random seed for reproducibility'
    )
    
    args = parser.parse_args()
    
    try:
        generator = FuzzGenerator(seed=args.seed)
        generator.generate_input_deck(
            args.output,
            n_sources=args.n_sources,
            n_receptors=args.n_receptors,
            emission_rate=args.emission_rate
        )
        
        print(f"✓ Generated fuzz test case: {args.output}")
        print(f"  Sources: {args.n_sources}")
        print(f"  Receptors: {args.n_receptors}")
        if args.seed is not None:
            print(f"  Seed: {args.seed}")
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
