#!/usr/bin/env python3
"""
One-pass Gemini 4 Argon port of AERMOD.

Uses the google-genai SDK >= 2.3.0 with Interactions API.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


def check_dependencies():
    """Check required dependencies."""
    try:
        import google.generativeai as genai
        # Check version
        import importlib.metadata
        version = importlib.metadata.version('google-generativeai')
        major, minor = map(int, version.split('.')[:2])
        if major < 2 or (major == 2 and minor < 3):
            print(f"Warning: google-generativeai {version} < 2.3.0", 
                  file=sys.stderr)
    except ImportError:
        print("Error: google-generativeai not installed", file=sys.stderr)
        print("Install with: pip install 'google-generativeai>=2.3.0'", 
              file=sys.stderr)
        sys.exit(1)


def load_prompt_and_context(
    tier: str,
    packed_context_path: Path,
    prompt_path: Path,
    contract_path: Path
) -> str:
    """
    Load and combine prompt with packed Fortran context.
    
    Returns:
        Complete prompt string
    """
    # Load contract
    with open(contract_path, 'r') as f:
        contract = f.read()
    
    # Load port prompt
    with open(prompt_path, 'r') as f:
        port_prompt = f.read()
    
    # Load packed Fortran
    with open(packed_context_path, 'r') as f:
        fortran_context = f.read()
    
    # Combine
    full_prompt = f"{port_prompt}\n\n"
    full_prompt += f"## Contract Reference\n\n{contract}\n\n"
    full_prompt += f"## Fortran Source\n\n{fortran_context}"
    
    return full_prompt


def run_argon_port(
    prompt: str,
    output_dir: Path,
    thinking_level: str = "high",
    use_background: bool = False
) -> dict:
    """
    Run Gemini 4 Argon on the porting task.
    
    Args:
        prompt: Complete prompt with Fortran source
        output_dir: Where to save results
        thinking_level: Thinking level (low, medium, high, xhigh, max)
        use_background: Use background processing for large outputs
        
    Returns:
        Result dict with output, token usage, etc.
    """
    import google.generativeai as genai
    
    # Check for API key
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY environment variable not set.\n"
            "Set it with: export GEMINI_API_KEY=your_key"
        )
    
    genai.configure(api_key=api_key)
    
    # Configure model
    model_id = f"gemini-4-argon-{thinking_level}"
    
    print(f"Initializing {model_id}...")
    model = genai.GenerativeModel(model_id)
    
    # Count input tokens
    print("Counting input tokens...")
    token_count = model.count_tokens(prompt)
    print(f"  Input tokens: {token_count.total_tokens:,}")
    
    # Generate config
    generation_config = {
        'temperature': 0.0,  # Deterministic for code generation
    }
    
    # For large outputs, may need background=True
    if use_background:
        generation_config['background'] = True
    
    print("\nGenerating port...")
    print("  (This may take several minutes for full-context pass)")
    
    start_time = datetime.now()
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=generation_config
        )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\n✓ Generation complete ({duration:.1f}s)")
        
        # Extract output
        if hasattr(response, 'text'):
            output_text = response.text
        else:
            output_text = response.candidates[0].content.parts[0].text
        
        # Get usage metadata
        usage = {
            'input_tokens': token_count.total_tokens,
            'output_tokens': getattr(response.usage_metadata, 'candidates_token_count', 0),
            'total_tokens': getattr(response.usage_metadata, 'total_token_count', 0),
        }
        
        print(f"  Output tokens: {usage['output_tokens']:,}")
        print(f"  Total tokens: {usage['total_tokens']:,}")
        
        # Save results
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save raw output
        output_file = output_dir / 'raw_output.txt'
        with open(output_file, 'w') as f:
            f.write(output_text)
        print(f"\n✓ Saved raw output: {output_file}")
        
        # Save metadata
        metadata = {
            'model': model_id,
            'thinking_level': thinking_level,
            'timestamp': start_time.isoformat(),
            'duration_seconds': duration,
            'usage': usage,
        }
        
        metadata_file = output_dir / 'metadata.json'
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"✓ Saved metadata: {metadata_file}")
        
        # Save prompt (for reproducibility)
        prompt_file = output_dir / 'prompt.txt'
        with open(prompt_file, 'w') as f:
            f.write(prompt)
        print(f"✓ Saved prompt: {prompt_file}")
        
        return {
            'output': output_text,
            'metadata': metadata,
            'output_dir': output_dir,
        }
        
    except Exception as e:
        print(f"\n✗ Generation failed: {e}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(
        description='Run Gemini 4 Argon one-pass AERMOD port'
    )
    parser.add_argument(
        '--tier',
        choices=['A', 'B'],
        default='A',
        help='Port tier (A=no PRIME, B=with PRIME)'
    )
    parser.add_argument(
        '--thinking',
        choices=['low', 'medium', 'high', 'xhigh', 'max'],
        default='high',
        help='Thinking level (default: high)'
    )
    parser.add_argument(
        '--background',
        action='store_true',
        help='Use background processing (for max_output_tokens > 65536)'
    )
    parser.add_argument(
        '--packed-context',
        type=Path,
        help='Path to packed Fortran context (default: context/tier_{A|B}_packed.txt)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Output directory (default: agent/runs/<timestamp>)'
    )
    
    args = parser.parse_args()
    
    # Check dependencies first
    check_dependencies()
    
    # Set up paths
    script_dir = Path(__file__).parent
    root_dir = script_dir.parent
    
    if args.packed_context is None:
        args.packed_context = root_dir / 'context' / f'tier_{args.tier}_packed.txt'
    
    if args.output_dir is None:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        args.output_dir = script_dir / 'runs' / f'tier_{args.tier}_{timestamp}'
    
    contract_path = root_dir / 'prompts' / 'contract.md'
    prompt_path = root_dir / 'prompts' / 'port.md'
    
    # Verify files exist
    for path in [args.packed_context, contract_path, prompt_path]:
        if not path.exists():
            print(f"Error: Required file not found: {path}", file=sys.stderr)
            if 'packed' in str(path):
                print("Run pack.py first to generate packed context", file=sys.stderr)
            return 1
    
    try:
        print("="*70)
        print(f"AERMOD Port - Tier {args.tier}")
        print("="*70)
        print(f"Thinking level: {args.thinking}")
        print(f"Packed context: {args.packed_context}")
        print(f"Output directory: {args.output_dir}")
        print()
        
        # Load prompt
        print("Loading prompt and context...")
        prompt = load_prompt_and_context(
            args.tier,
            args.packed_context,
            prompt_path,
            contract_path
        )
        print(f"  Prompt length: {len(prompt):,} characters")
        
        # Run port
        result = run_argon_port(
            prompt,
            args.output_dir,
            thinking_level=args.thinking,
            use_background=args.background
        )
        
        print("\n" + "="*70)
        print("Next steps:")
        print("="*70)
        print(f"1. Split output: ./split.py {args.output_dir}/raw_output.txt")
        print(f"2. Run tests: harness/run_port.py AERTEST")
        print(f"3. Compare: harness/compare.py ref_output port_output")
        print(f"4. If issues: agent/repair_loop.py")
        
        return 0
        
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
