#!/usr/bin/env python3
"""Find endpoints without authentication decorators"""
import re

with open('app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

routes = []
i = 0
while i < len(lines):
    line = lines[i]
    if '@app.route' in line:
        route_line = line.strip()
        # Check previous lines for auth decorators (they appear before @app.route)
        has_auth = False
        for j in range(max(0, i-5), i):
            check_line = lines[j]
            if any(dec in check_line for dec in ['@require_authentication', '@require_permission', '@require_board_access']):
                has_auth = True
                break
        
        if not has_auth:
            # Extract route path and method
            match = re.search(r'"([^"]+)"', route_line)
            method_match = re.search(r'methods=\[([^\]]+)\]', route_line)
            if match:
                path = match.group(1)
                methods = method_match.group(1) if method_match else 'GET'
                routes.append(f'{methods:20} {path}')
    i += 1

print(f'\nEndpoints without authentication: {len(routes)}')
print('=' * 80)
for route in sorted(set(routes)):
    print(route)
