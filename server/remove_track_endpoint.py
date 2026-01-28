#!/usr/bin/env python3
"""Remove all @track_endpoint decorator lines from app.py"""

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove lines containing @track_endpoint
filtered_lines = [line for line in lines if '@track_endpoint' not in line]

with open('app.py', 'w', encoding='utf-8') as f:
    f.writelines(filtered_lines)

print(f'Removed {len(lines) - len(filtered_lines)} @track_endpoint decorator lines')
print(f'Original: {len(lines)} lines, New: {len(filtered_lines)} lines')
