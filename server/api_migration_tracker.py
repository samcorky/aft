"""
API Migration Tracking System

This module helps track the migration of API endpoints to require authentication.
It provides:
- Registry of all API endpoints with their protection status
- Optional enforcement mode to require auth on ALL APIs
- Migration status report endpoint
"""

import logging
from functools import wraps
from flask import request, jsonify, g
from collections import defaultdict

logger = logging.getLogger(__name__)

# Registry of all API endpoints and their authentication status
# Format: {path: {'methods': [list], 'protected': bool, 'reason': str}}
API_REGISTRY = {}

# Migration tracking counters
MIGRATION_STATS = {
    'total_endpoints': 0,
    'protected_endpoints': 0,
    'unprotected_endpoints': 0
}

# ENFORCEMENT MODE - Set to True to require authentication on ALL API endpoints
# This will block all unauthenticated requests to /api/* endpoints
# Use this after migration is complete to ensure no endpoints are left unprotected
ENFORCE_AUTH_ON_ALL_APIS = False  # Set to True when migration is complete


def register_api_endpoint(path, methods, protected=False, reason=None):
    """
    Register an API endpoint in the tracking system.
    
    Args:
        path: The endpoint path (e.g., '/api/boards')
        methods: List of HTTP methods (e.g., ['GET', 'POST'])
        protected: Whether the endpoint requires authentication
        reason: Reason for protection status (e.g., 'requires board ownership')
    """
    if path not in API_REGISTRY:
        API_REGISTRY[path] = {
            'methods': set(),
            'protected': protected,
            'reason': reason or ('Protected' if protected else 'Not yet migrated')
        }
    
    API_REGISTRY[path]['methods'].update(methods)
    if protected:
        API_REGISTRY[path]['protected'] = True
        if reason:
            API_REGISTRY[path]['reason'] = reason
    
    # Update stats
    _update_migration_stats()


def _update_migration_stats():
    """Update migration statistics."""
    total = len(API_REGISTRY)
    protected = sum(1 for ep in API_REGISTRY.values() if ep['protected'])
    
    MIGRATION_STATS['total_endpoints'] = total
    MIGRATION_STATS['protected_endpoints'] = protected
    MIGRATION_STATS['unprotected_endpoints'] = total - protected


def track_endpoint(protected=False, reason=None):
    """
    Decorator to track an API endpoint in the migration registry.
    
    Usage:
        @app.route('/api/boards', methods=['GET'])
        @track_endpoint(protected=True, reason='Requires authentication')
        def get_boards():
            ...
    
    Args:
        protected: Whether this endpoint requires authentication
        reason: Reason for protection status
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Register on first call
            if request.path not in API_REGISTRY:
                register_api_endpoint(
                    request.path,
                    [request.method],
                    protected=protected,
                    reason=reason
                )
            
            # If enforcement mode is on, require authentication for all /api/* endpoints
            if ENFORCE_AUTH_ON_ALL_APIS and request.path.startswith('/api/'):
                # Skip auth endpoints and migration report
                if not (request.path.startswith('/api/auth/') or 
                       request.path == '/api/migration-status' or
                       request.path == '/api/test'):
                    if not g.get('user'):
                        logger.warning(f"Blocked unauthenticated request to {request.path} (enforcement mode)")
                        return jsonify({
                            'success': False,
                            'error': 'Authentication required',
                            'message': 'All API endpoints require authentication. Please log in.',
                            'enforcement_mode': True
                        }), 401
            
            return f(*args, **kwargs)
        
        return wrapper
    return decorator


def get_migration_status():
    """
    Get the current migration status.
    
    Returns:
        dict: Migration status including stats and endpoint list
    """
    # Group endpoints by protection status
    protected = {}
    unprotected = {}
    
    for path, info in sorted(API_REGISTRY.items()):
        endpoint_info = {
            'methods': sorted(list(info['methods'])),
            'reason': info['reason']
        }
        
        if info['protected']:
            protected[path] = endpoint_info
        else:
            unprotected[path] = endpoint_info
    
    return {
        'enforcement_mode': ENFORCE_AUTH_ON_ALL_APIS,
        'stats': MIGRATION_STATS.copy(),
        'progress_percentage': round(
            (MIGRATION_STATS['protected_endpoints'] / MIGRATION_STATS['total_endpoints'] * 100)
            if MIGRATION_STATS['total_endpoints'] > 0 else 0,
            1
        ),
        'protected_endpoints': protected,
        'unprotected_endpoints': unprotected,
        'endpoints_to_migrate': list(unprotected.keys())
    }


def enable_enforcement_mode():
    """
    Enable enforcement mode - all APIs will require authentication.
    Call this after migration is complete.
    """
    global ENFORCE_AUTH_ON_ALL_APIS
    ENFORCE_AUTH_ON_ALL_APIS = True
    logger.warning("⚠️  API ENFORCEMENT MODE ENABLED - All API endpoints now require authentication")


def disable_enforcement_mode():
    """
    Disable enforcement mode - allows gradual migration.
    """
    global ENFORCE_AUTH_ON_ALL_APIS
    ENFORCE_AUTH_ON_ALL_APIS = False
    logger.info("API enforcement mode disabled - gradual migration mode")


# Blueprint for migration status endpoint
from flask import Blueprint

migration_bp = Blueprint('migration', __name__)


@migration_bp.route('/api/migration-status', methods=['GET'])
def migration_status_endpoint():
    """
    Get API migration status report.
    
    Returns detailed information about which endpoints are protected
    and which still need to be migrated.
    
    Query params:
        format: 'json' (default) or 'html' for human-readable report
    """
    status = get_migration_status()
    
    format_type = request.args.get('format', 'json')
    
    if format_type == 'html':
        # Return HTML report
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>API Migration Status</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                h1 {{ color: #333; border-bottom: 3px solid #667eea; padding-bottom: 10px; }}
                .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
                .stat-card {{ flex: 1; padding: 20px; border-radius: 8px; text-align: center; }}
                .stat-card.total {{ background: #e3f2fd; border: 2px solid #2196f3; }}
                .stat-card.protected {{ background: #e8f5e9; border: 2px solid #4caf50; }}
                .stat-card.unprotected {{ background: #fff3e0; border: 2px solid #ff9800; }}
                .stat-value {{ font-size: 48px; font-weight: bold; margin: 10px 0; }}
                .stat-label {{ font-size: 14px; color: #666; text-transform: uppercase; }}
                .progress-bar {{ width: 100%; height: 30px; background: #e0e0e0; border-radius: 15px; overflow: hidden; margin: 20px 0; }}
                .progress-fill {{ height: 100%; background: linear-gradient(90deg, #4caf50, #8bc34a); transition: width 0.3s; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; }}
                .enforcement {{ padding: 15px; border-radius: 8px; margin: 20px 0; font-weight: bold; }}
                .enforcement.on {{ background: #ffebee; border: 2px solid #f44336; color: #c62828; }}
                .enforcement.off {{ background: #fff9c4; border: 2px solid #fbc02d; color: #f57f17; }}
                .endpoints {{ margin-top: 30px; }}
                .endpoint-section {{ margin: 20px 0; }}
                .endpoint-section h2 {{ color: #666; font-size: 18px; margin-bottom: 10px; }}
                .endpoint {{ background: #f5f5f5; padding: 12px; margin: 5px 0; border-radius: 4px; border-left: 4px solid #ccc; }}
                .endpoint.protected {{ border-left-color: #4caf50; background: #f1f8f4; }}
                .endpoint.unprotected {{ border-left-color: #ff9800; background: #fff8f1; }}
                .endpoint-path {{ font-family: monospace; font-weight: bold; color: #333; }}
                .endpoint-methods {{ display: inline-block; margin-left: 10px; }}
                .method {{ display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: bold; margin-right: 5px; }}
                .method.GET {{ background: #4caf50; color: white; }}
                .method.POST {{ background: #2196f3; color: white; }}
                .method.PUT {{ background: #ff9800; color: white; }}
                .method.PATCH {{ background: #9c27b0; color: white; }}
                .method.DELETE {{ background: #f44336; color: white; }}
                .endpoint-reason {{ color: #666; font-size: 13px; margin-top: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🔒 API Migration Status</h1>
                
                <div class="enforcement {'on' if status['enforcement_mode'] else 'off'}">
                    {'⚠️ ENFORCEMENT MODE ENABLED - All APIs require authentication' if status['enforcement_mode'] else '⚙️ ENFORCEMENT MODE OFF - Gradual migration in progress'}
                </div>
                
                <div class="stats">
                    <div class="stat-card total">
                        <div class="stat-label">Total Endpoints</div>
                        <div class="stat-value">{status['stats']['total_endpoints']}</div>
                    </div>
                    <div class="stat-card protected">
                        <div class="stat-label">Protected</div>
                        <div class="stat-value">{status['stats']['protected_endpoints']}</div>
                    </div>
                    <div class="stat-card unprotected">
                        <div class="stat-label">To Migrate</div>
                        <div class="stat-value">{status['stats']['unprotected_endpoints']}</div>
                    </div>
                </div>
                
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {status['progress_percentage']}%">
                        {status['progress_percentage']}% Complete
                    </div>
                </div>
                
                <div class="endpoints">
                    <div class="endpoint-section">
                        <h2>✅ Protected Endpoints ({len(status['protected_endpoints'])})</h2>
                        {''.join([f'''
                        <div class="endpoint protected">
                            <div class="endpoint-path">{path}</div>
                            <div class="endpoint-methods">
                                {''.join([f'<span class="method {m}">{m}</span>' for m in info['methods']])}
                            </div>
                            <div class="endpoint-reason">{info['reason']}</div>
                        </div>
                        ''' for path, info in status['protected_endpoints'].items()])}
                    </div>
                    
                    <div class="endpoint-section">
                        <h2>⚠️ Unprotected Endpoints ({len(status['unprotected_endpoints'])})</h2>
                        {''.join([f'''
                        <div class="endpoint unprotected">
                            <div class="endpoint-path">{path}</div>
                            <div class="endpoint-methods">
                                {''.join([f'<span class="method {m}">{m}</span>' for m in info['methods']])}
                            </div>
                            <div class="endpoint-reason">{info['reason']}</div>
                        </div>
                        ''' for path, info in status['unprotected_endpoints'].items()]) if status['unprotected_endpoints'] else '<div class="endpoint protected">🎉 All endpoints are protected!</div>'}
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    # Return JSON by default
    return jsonify(status)
