#!/usr/bin/env python3
"""
Pack AERMOD Fortran source into a single context for Gemini 4 Argon.

Includes:
- Scoped Fortran files (modules.f, aermod.f, calc1/2, prise, sigmas, etc.)
- Subroutine index for navigation
- Token count using Gemini API or tiktoken proxy
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Files in scope for Tier A (no building downwash)
TIER_A_FILES = [
    'modules.f',
    'aermod.f',
    'metext.f',
    'iblval.f',
    'siggrid.f',
    'tempgrid.f',
    'windgrid.f',
    'calc1.f',
    'calc2.f',
    'prise.f',
    'sigmas.f',
]

# Additional files for Tier B (with PRIME)
TIER_B_ADDITIONAL = [
    'prime.f',
]


class FortranPacker:
    """Pack Fortran source files with subroutine index."""
    
    def __init__(self, source_dir: Path):
        self.source_dir = source_dir
        self.subroutine_index: Dict[str, Tuple[str, int]] = {}
    
    def extract_subroutines(self, filepath: Path) -> List[Tuple[str, int]]:
        """
        Extract subroutine/function names and line numbers from Fortran file.
        
        Returns:
            List of (name, line_number) tuples
        """
        subroutines = []
        
        with open(filepath, 'r', encoding='latin-1', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                # Match SUBROUTINE or FUNCTION declarations
                # Fortran is case-insensitive
                match = re.match(
                    r'^\s+(SUBROUTINE|FUNCTION)\s+(\w+)',
                    line,
                    re.IGNORECASE
                )
                if match:
                    name = match.group(2).upper()
                    subroutines.append((name, line_num))
        
        return subroutines
    
    def build_index(self, files: List[str]) -> str:
        """
        Build subroutine index for all files.
        
        Returns:
            Formatted index string
        """
        self.subroutine_index.clear()
        
        index_lines = ["# SUBROUTINE INDEX\n\n"]
        
        for filename in files:
            filepath = self.source_dir / filename
            if not filepath.exists():
                print(f"Warning: File not found: {filepath}", file=sys.stderr)
                continue
            
            subs = self.extract_subroutines(filepath)
            if subs:
                index_lines.append(f"## {filename}\n\n")
                for name, line_num in subs:
                    index_lines.append(f"- {name} (line {line_num})\n")
                    self.subroutine_index[name] = (filename, line_num)
                index_lines.append("\n")
        
        return "".join(index_lines)
    
    def pack_files(
        self,
        files: List[str],
        include_index: bool = True
    ) -> str:
        """
        Pack Fortran files into a single context.
        
        Returns:
            Combined content string
        """
        parts = []
        
        if include_index:
            index = self.build_index(files)
            parts.append(index)
            parts.append("\n" + "="*70 + "\n")
            parts.append("# FORTRAN SOURCE FILES\n")
            parts.append("="*70 + "\n\n")
        
        for filename in files:
            filepath = self.source_dir / filename
            if not filepath.exists():
                print(f"Warning: Skipping missing file: {filepath}", file=sys.stderr)
                continue
            
            parts.append(f"\n{'='*70}\n")
            parts.append(f"FILE: {filename}\n")
            parts.append(f"{'='*70}\n\n")
            
            with open(filepath, 'r', encoding='latin-1', errors='ignore') as f:
                parts.append(f.read())
            
            parts.append("\n")
        
        return "".join(parts)
    
    def save_packed(self, content: str, output_path: Path) -> None:
        """Save packed content to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def count_tokens(self, text: str, use_gemini: bool = True) -> int:
        """
        Count tokens using Gemini API or tiktoken proxy.
        
        Args:
            text: Text to count
            use_gemini: Try Gemini API first (requires GEMINI_API_KEY)
            
        Returns:
            Token count
        """
        if use_gemini:
            try:
                import google.generativeai as genai
                
                api_key = os.environ.get('GEMINI_API_KEY')
                if api_key:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel('gemini-4-argon')
                    
                    result = model.count_tokens(text)
                    return result.total_tokens
            except Exception as e:
                print(f"Gemini token count failed: {e}", file=sys.stderr)
                print("Falling back to tiktoken proxy...", file=sys.stderr)
        
        # Fallback to tiktoken o200k proxy
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("o200k_base")
            return len(encoding.encode(text))
        except ImportError:
            print("Warning: tiktoken not available, using rough estimate", 
                  file=sys.stderr)
            # Very rough estimate: ~4 chars per token
            return len(text) // 4


def main():
    parser = argparse.ArgumentParser(
        description='Pack AERMOD Fortran source for Gemini 4 Argon'
    )
    parser.add_argument(
        '--source-dir',
        type=Path,
        default=Path('ref/aermod_source'),
        help='AERMOD source directory'
    )
    parser.add_argument(
        '--tier',
        choices=['A', 'B'],
        default='A',
        help='Tier: A (no PRIME) or B (with PRIME)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Output file path (default: context/tier_{A|B}_packed.txt)'
    )
    parser.add_argument(
        '--no-index',
        action='store_true',
        help='Skip subroutine index'
    )
    parser.add_argument(
        '--count-tokens',
        action='store_true',
        help='Count tokens after packing'
    )
    
    args = parser.parse_args()
    
    # Determine files to pack
    files = TIER_A_FILES.copy()
    if args.tier == 'B':
        files.extend(TIER_B_ADDITIONAL)
    
    # Default output path
    if args.output is None:
        args.output = Path(f'context/tier_{args.tier}_packed.txt')
    
    try:
        # Find source directory
        source_dir = args.source_dir
        
        # Check common locations
        if not source_dir.exists():
            for subdir in ['source', 'src', '']:
                candidate = args.source_dir / subdir
                if (candidate / 'modules.f').exists():
                    source_dir = candidate
                    break
        
        if not (source_dir / 'modules.f').exists():
            print(f"Error: Cannot find modules.f in {source_dir}", 
                  file=sys.stderr)
            print("Run ref/download_aermod.sh first", file=sys.stderr)
            return 1
        
        print(f"Packing Tier {args.tier} source files...")
        print(f"Source directory: {source_dir}")
        
        packer = FortranPacker(source_dir)
        content = packer.pack_files(files, include_index=not args.no_index)
        
        # Save packed content
        packer.save_packed(content, args.output)
        
        print(f"\n✓ Packed {len(files)} files to: {args.output}")
        print(f"  Size: {len(content):,} bytes")
        
        if not args.no_index:
            print(f"  Subroutines indexed: {len(packer.subroutine_index)}")
        
        # Count tokens if requested
        if args.count_tokens:
            print("\nCounting tokens...")
            
            # Try Gemini first if API key available
            use_gemini = os.environ.get('GEMINI_API_KEY') is not None
            token_count = packer.count_tokens(content, use_gemini=use_gemini)
            
            method = "Gemini API" if use_gemini else "tiktoken o200k proxy"
            print(f"  Token count ({method}): {token_count:,}")
            
            # Show context utilization for Gemini 4 Argon (1M context)
            utilization = (token_count / 1_048_576) * 100
            print(f"  Context utilization: {utilization:.1f}% of 1M")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
