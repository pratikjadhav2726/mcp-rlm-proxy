"""
Script to update all config.yaml references to mcp.json across the repository.
"""

import re
from pathlib import Path

# Files to update
FILES_TO_UPDATE = [
    'docs/MIGRATION_GUIDE.md',
    'docs/MIDDLEWARE_ADOPTION.md',
    'docs/QUICK_REFERENCE.md',
    'docs/SUMMARY.md',
    'docs/CONFIGURATION.md',
    'docs/LOGGING.md',
    'examples/README.md',
    'examples/comprehensive_example.py',
    'examples/example_usage.py',
    'tests/test_config.py',
    'tests/test_proxy.py',
]

# Replacement patterns
REPLACEMENTS = [
    (r'config\.yaml\.example', 'mcp.json.example'),
    (r'config\.yaml', 'mcp.json'),
    (r'underlying_servers:', 'mcpServers:'),
    (r'```yaml\nunderlying_servers:', '```json\n{\n  "mcpServers": {'),
    (r'  - name: (\w+)', r'    "\1": {'),
    (r'    command: (\w+)', r'      "command": "\1",'),
    (r'    args: \[(.*?)\]', r'      "args": [\1]'),
]

def update_file(filepath):
    """Update a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        for pattern, replacement in REPLACEMENTS:
            content = re.sub(pattern, replacement, content)
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✓ Updated {filepath}")
            return True
        else:
            print(f"- No changes needed in {filepath}")
            return False
    except Exception as e:
        print(f"✗ Error updating {filepath}: {e}")
        return False

def main():
    """Main function."""
    updated_count = 0
    for filepath in FILES_TO_UPDATE:
        path = Path(filepath)
        if path.exists():
            if update_file(path):
                updated_count += 1
        else:
            print(f"⚠ File not found: {filepath}")
    
    print(f"\n{'='*60}")
    print(f"Updated {updated_count}/{len(FILES_TO_UPDATE)} files")
    print(f"{'='*60}")

if __name__ == '__main__':
    main()

