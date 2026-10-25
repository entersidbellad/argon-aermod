#!/usr/bin/env python3
"""
Split Gemini 4 Argon output into files.

Parses output with file markers like:
    === FILE: path/to/file.py ===
    <content>
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple


class OutputSplitter:
    """Split Argon's output into separate files."""
    
    FILE_MARKER_PATTERN = re.compile(
        r'^===\s*FILE:\s*(.+?)\s*===$',
        re.MULTILINE
    )
    
    def parse_output(self, text: str) -> List[Tuple[str, str]]:
        """
        Parse output into (filepath, content) tuples.
        
        Args:
            text: Full Argon output
            
        Returns:
            List of (filepath, content) tuples
        """
        files = []
        
        # Find all file markers
        markers = list(self.FILE_MARKER_PATTERN.finditer(text))
        
        if not markers:
            raise ValueError(
                "No file markers found in output. "
                "Expected format: === FILE: path ===\\n<content>"
            )
        
        for i, match in enumerate(markers):
            filepath = match.group(1).strip()
            start = match.end()
            
            # Find end (next marker or end of text)
            if i + 1 < len(markers):
                end = markers[i + 1].start()
            else:
                end = len(text)
            
            content = text[start:end].strip()
            files.append((filepath, content))
        
        return files
    
    def write_files(
        self,
        files: List[Tuple[str, str]],
        output_dir: Path,
        dry_run: bool = False
    ) -> None:
        """
        Write parsed files to disk.
        
        Args:
            files: List of (filepath, content) tuples
            output_dir: Base directory for output
            dry_run: If True, only print what would be written
        """
        for filepath, content in files:
            full_path = output_dir / filepath
            
            if dry_run:
                print(f"Would write: {full_path} ({len(content)} bytes)")
                continue
            
            # Create parent directories
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write file
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✓ Wrote: {full_path} ({len(content)} bytes)")


def main():
    parser = argparse.ArgumentParser(
        description='Split Gemini 4 Argon output into files'
    )
    parser.add_argument(
        'input',
        type=Path,
        help='Input file with Argon output'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('port/aermod_py'),
        help='Output directory (default: port/aermod_py)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be written without writing'
    )
    
    args = parser.parse_args()
    
    try:
        # Read input
        print(f"Reading: {args.input}")
        with open(args.input, 'r', encoding='utf-8') as f:
            text = f.read()
        
        # Parse
        print("Parsing output...")
        splitter = OutputSplitter()
        files = splitter.parse_output(text)
        
        print(f"Found {len(files)} files")
        
        # Write
        if args.dry_run:
            print("\nDry run - would write:")
        else:
            print(f"\nWriting to: {args.output_dir}")
        
        splitter.write_files(files, args.output_dir, dry_run=args.dry_run)
        
        if not args.dry_run:
            print(f"\n✓ Wrote {len(files)} files to {args.output_dir}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
