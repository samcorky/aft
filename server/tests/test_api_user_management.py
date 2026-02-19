"""
Tests for user management API endpoints (admin only).

Tests the following endpoints:
- GET /api/users - List all users
- GET /api/users/pending - List pending approval users
- POST /api/users/:id/approve - Approve a user
- POST /api/users/:id/reject - Reject a user
- POST /api/users/:id/activate - Activate a user
- POST /api/users/:id/deactivate - Deactivate a user
- POST /api/users/:id/roles/:role_id - Assign role to user
- DELETE /api/users/:id/roles/:role_id - Remove role from user
"""
import pytest
import requests
import time

# API base URL - matching conftest.py
API_BASE_URL = "http://localhost"


@pytest.fixture(scope="module")
def setup_test_environment():
    """Setup test environment with admin and test users."""
    # Clean database
    try:
        requests.delete(f"{API_BASE_URL}/api/database")
        time.sleep(0.5)
    except:
        pass
    
    # Create admin user
    requests.post(f"{API_BASE_URL}/api/auth/setup/admin", json={
        "email": "admin@localhost",
        "username": "admin",
        "password": "AdminPass123!"
    })
    
    # Create some pending users
    for i in range(3):
        requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": f"user{i}@test.com",
            "username": f"user{i}",
            "password": f"UserPass{i}123!"
        })
    
    time.sleep(0.2)
    yield
    
    # Cleanup
    try:
        requests.delete(f"{API_BASE_URL}/api/database")
    except:
        pass


@pytest.fixture
def admin_session():
    """Create an authenticated admin session."""
    session = requests.Session()
    response = session.post(f"{API_BASE_URL}/api/auth/login", json={
        "email": "admin@localhost",
        "password": "AdminPass123!"
    })
    assert response.status_code == 200
    return session


@pytest.fixture
def regular_session(setup_test_environment):
    """Create a session for a non-admin user (will need approval first)."""
    # This fixture creates the session but user won't be able to access admin endpoints
    session = requests.Session()
    return session


class TestUserListing:
    """Test user listing endpoints."""
    
    def test_list_users_unauthenticated(self, setup_test_environment):
        """List users should require authentication."""
        response = requests.get(f"{API_BASE_URL}/api/users")
        assert response.status_code == 401
    
    def test_list_users_as_admin(self, admin_session, setup_test_environment):
        """Admin should be able to list all users."""
        response = admin_session.get(f"{API_BASE_URL}/api/users")
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'users' in data
        assert len(data['users']) >= 4  # Admin + 3 registered users
        
        # Check user data structure
        user = data['users'][0]
        assert 'id' in user
        assert 'email' in user
        assert 'username' in user
        assert 'is_active' in user
        assert 'is_approved' in user
        assert 'roles' in user
    
    def test_list_pending_users(self, admin_session, setup_test_environment):
        """Admin should be able to list pending users."""
        response = admin_session.get(f"{API_BASE_URL}/api/users/pending")
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert 'users' in data
        assert len(data['users']) == 3  # 3 pending users
        
        # All should be unapproved
        for user in data['users']:
            assert user['is_approved'] is False


class TestUserApproval:
    """Test user approval/rejection."""
    
    def test_approve_user_unauthenticated(self, setup_test_environment):
        """Approval should require authentication."""
        response = requests.post(f"{API_BASE_URL}/api/users/999/approve")
        assert response.status_code == 401
    
    def test_approve_nonexistent_user(self, admin_session):
        """Approving nonexistent user should fail."""
        response = admin_session.post(f"{API_BASE_URL}/api/users/99999/approve")
        assert response.status_code == 404
    
    def test_approve_user_success(self, admin_session, setup_test_environment):
        """Admin should be able to approve pending users."""
        # Get pending users
        response = admin_session.get(f"{API_BASE_URL}/api/users/pending")
        pending_users = response.json()['users']
        assert len(pending_users) > 0
        
        user_id = pending_users[0]['id']
        user_email = pending_users[0]['email']
        
        # Approve user
        response = admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/approve")
        assert response.status_code == 200
        
        data = response.json()
        assert data['success'] is True
        assert data['user']['is_approved'] is True
        
        # Verify user can now login
        user_session = requests.Session()
        # Extract password from user email (user0@test.com -> UserPass0123!)
        user_num = user_email.split('@')[0].replace('user', '')
        response = user_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": user_email,
            "password": f"UserPass{user_num}123!"
        })
        assert response.status_code == 200
    
    def test_reject_user_success(self, admin_session, setup_test_environment):
        """Admin should be able to reject pending users."""
        # Get pending users
        response = admin_session.get(f"{API_BASE_URL}/api/users/pending")
        pending_users = response.json()['users']
        
        if len(pending_users) > 0:
            user_id = pending_users[0]['id']
            
            # Reject user
            response = admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/reject")
            assert response.status_code == 200
            assert response.json()['success'] is True
            
            # Verify user no longer in pending list
            response = admin_session.get(f"{API_BASE_URL}/api/users/pending")
            remaining = response.json()['users']
            assert user_id not in [u['id'] for u in remaining]


class TestUserActivation:
    """Test user activation/deactivation."""
    
    def test_deactivate_user(self, admin_session, setup_test_environment):
        """Admin should be able to deactivate users."""
        # Get an approved user
        response = admin_session.get(f"{API_BASE_URL}/api/users/pending")
        pending = response.json()['users']
        
        if len(pending) > 0:
            # Approve one first
            user_id = pending[0]['id']
            admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/approve")
            
            # Deactivate
            response = admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/deactivate")
            assert response.status_code == 200
            
            data = response.json()
            assert data['success'] is True
            assert data['user']['is_active'] is False
    
    def test_activate_user(self, admin_session, setup_test_environment):
        """Admin should be able to reactivate users."""
        # Get users and find a deactivated one
        response = admin_session.get(f"{API_BASE_URL}/api/users")
        users = response.json()['users']
        
        deactivated = [u for u in users if not u['is_active']]
        if len(deactivated) > 0:
            user_id = deactivated[0]['id']
            
            # Activate
            response = admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/activate")
            assert response.status_code == 200
            
            data = response.json()
            assert data['success'] is True
            assert data['user']['is_active'] is True
    
    def test_login_deactivated_user(self, admin_session, setup_test_environment):
        """Deactivated users should not be able to login."""
        # Approve a user
        response = admin_session.get(f"{API_BASE_URL}/api/users/pending")
        pending = response.json()['users']
        
        if len(pending) > 0:
            user_id = pending[0]['id']
            user_email = pending[0]['email']
            user_num = user_email.split('@')[0].replace('user', '')
            password = f"UserPass{user_num}123!"
            
            # Approve user
            admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/approve")
            
            # Verify can login
            user_session = requests.Session()
            response = user_session.post(f"{API_BASE_URL}/api/auth/login", json={
                "email": user_email,
                "password": password
            })
            assert response.status_code == 200
            
            # Deactivate user
            admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/deactivate")
            
            # Try to login again (should fail)
            user_session2 = requests.Session()
            response = user_session2.post(f"{API_BASE_URL}/api/auth/login", json={
                "email": user_email,
                "password": password
            })
            assert response.status_code == 403


class TestRoleManagement:
    """Test role assignment and removal."""
    
    def test_assign_role_to_user(self, admin_session, setup_test_environment):
        """Admin should be able to assign roles to users."""
        # Get a user
        response = admin_session.get(f"{API_BASE_URL}/api/users")
        users = response.json()['users']
        
        # Find non-admin user
        regular_user = [u for u in users if 'administrator' not in [r['name'] for r in u['roles']]]
        if len(regular_user) > 0:
            user_id = regular_user[0]['id']
            
            # Get available roles (we need the role ID)
            # For now, we'll use known role IDs from initial setup
            # Role IDs: 1=administrator, 2=board_admin, 3=editor, 4=read_only
            
            # Assign editor role
            response = admin_session.post(
                f"{API_BASE_URL}/api/users/{user_id}/roles/3",  # editor role
                json={}
            )
            assert response.status_code == 200
            
            data = response.json()
            assert data['success'] is True
            assert 'editor' in [r['name'] for r in data['user']['roles']]
    
    def test_remove_role_from_user(self, admin_session, setup_test_environment):
        """Admin should be able to remove roles from users."""
        # Get a user with roles
        response = admin_session.get(f"{API_BASE_URL}/api/users")
        users = response.json()['users']
        
        # Find user with editor role
        for user in users:
            if 'editor' in [r['name'] for r in user['roles']]:
                user_id = user['id']
                
                # Remove editor role
                response = admin_session.delete(
                    f"{API_BASE_URL}/api/users/{user_id}/roles/3"  # editor role
                )
                assert response.status_code == 200
                
                data = response.json()
                assert data['success'] is True
                assert 'editor' not in [r['name'] for r in data['user']['roles']]
                break
    
    def test_assign_role_invalid_user(self, admin_session):
        """Assigning role to nonexistent user should fail."""
        response = admin_session.post(f"{API_BASE_URL}/api/users/99999/roles/3", json={})
        assert response.status_code == 404
    
    def test_assign_invalid_role(self, admin_session, setup_test_environment):
        """Assigning nonexistent role should fail."""
        response = admin_session.get(f"{API_BASE_URL}/api/users")
        users = response.json()['users']
        
        if len(users) > 0:
            user_id = users[0]['id']
            response = admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/roles/99999", json={})
            assert response.status_code == 404

    def test_create_custom_role(self, admin_session):
        """Admin should be able to create a custom role."""
        response = admin_session.post(
            f"{API_BASE_URL}/api/roles",
            json={
                "name": "test_custom_role",
                "description": "A test custom role",
                "permissions": ["board.view", "board.create"]
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['role']['name'] == 'test_custom_role'
        assert len(data['role']['permissions']) == 2

    def test_create_role_duplicate_name(self, admin_session):
        """Creating a role with duplicate name should fail."""
        # Try to create a role with the same name as a system role
        response = admin_session.post(
            f"{API_BASE_URL}/api/roles",
            json={
                "name": "administrator",
                "description": "Duplicate role",
                "permissions": ["board.view"]
            }
        )
        assert response.status_code == 409

    def test_copy_role(self, admin_session):
        """Admin should be able to copy a role."""
        # First get list of roles
        response = admin_session.get(f"{API_BASE_URL}/api/roles")
        roles = response.json()['roles']
        
        if len(roles) > 0:
            source_role_id = roles[0]['id']
            
            response = admin_session.post(
                f"{API_BASE_URL}/api/roles/{source_role_id}/copy",
                json={"name": "copied_test_role"}
            )
            assert response.status_code == 201
            data = response.json()
            assert data['success'] is True
            assert data['role']['name'] == 'copied_test_role'

    def test_update_role_permissions(self, admin_session):
        """Admin should be able to update a custom role's permissions."""
        # First create a role
        response = admin_session.post(
            f"{API_BASE_URL}/api/roles",
            json={
                "name": "test_update_role",
                "description": "Test role for updating",
                "permissions": ["board.view"]
            }
        )
        assert response.status_code == 201
        role_id = response.json()['role']['id']
        
        # Now update it
        response = admin_session.patch(
            f"{API_BASE_URL}/api/roles/{role_id}",
            json={
                "name": "test_update_role_renamed",
                "permissions": ["board.view", "board.create", "board.edit"]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['role']['name'] == 'test_update_role_renamed'
        assert len(data['role']['permissions']) == 3

    def test_update_system_role_fails(self, admin_session):
        """Updating a system role should fail."""
        # Get list of roles and find a system role
        response = admin_session.get(f"{API_BASE_URL}/api/roles")
        roles = response.json()['roles']
        
        system_role = next((r for r in roles if r['is_system_role']), None)
        if system_role:
            response = admin_session.patch(
                f"{API_BASE_URL}/api/roles/{system_role['id']}",
                json={"permissions": ["board.view"]}
            )
            assert response.status_code == 400

    def test_delete_custom_role(self, admin_session):
        """Admin should be able to delete a custom role."""
        # First create a role
        response = admin_session.post(
            f"{API_BASE_URL}/api/roles",
            json={
                "name": "test_delete_role",
                "description": "Test role for deletion",
                "permissions": ["board.view"]
            }
        )
        assert response.status_code == 201
        role_id = response.json()['role']['id']
        
        # Now delete it
        response = admin_session.delete(f"{API_BASE_URL}/api/roles/{role_id}")
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True

    def test_delete_system_role_fails(self, admin_session):
        """Deleting a system role should fail."""
        # Get list of roles and find a system role
        response = admin_session.get(f"{API_BASE_URL}/api/roles")
        roles = response.json()['roles']
        
        system_role = next((r for r in roles if r['is_system_role']), None)
        if system_role:
            response = admin_session.delete(f"{API_BASE_URL}/api/roles/{system_role['id']}")
            assert response.status_code == 400


class TestAdminPermissions:
    """Test that only admins can access user management."""
    
    def test_non_admin_cannot_list_users(self, setup_test_environment):
        """Non-admin users should not be able to list users."""
        # First approve a user
        admin_session = requests.Session()
        admin_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        
        response = admin_session.get(f"{API_BASE_URL}/api/users/pending")
        pending = response.json()['users']
        
        if len(pending) > 0:
            user_id = pending[0]['id']
            user_email = pending[0]['email']
            user_num = user_email.split('@')[0].replace('user', '')
            password = f"UserPass{user_num}123!"
            
            # Approve and assign read_only role (not admin)
            admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/approve")
            admin_session.post(f"{API_BASE_URL}/api/users/{user_id}/roles/4", json={})  # read_only
            
            # Login as regular user
            user_session = requests.Session()
            user_session.post(f"{API_BASE_URL}/api/auth/login", json={
                "email": user_email,
                "password": password
            })
            
            # Try to list users (should fail)
            response = user_session.get(f"{API_BASE_URL}/api/users")
            assert response.status_code == 403  # Forbidden
    
    def test_non_admin_cannot_approve_users(self, setup_test_environment):
        """Non-admin users should not be able to approve other users."""
        # Setup admin and regular user (reuse previous test pattern)
        admin_session = requests.Session()
        admin_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        
        response = admin_session.get(f"{API_BASE_URL}/api/users/pending")
        pending = response.json()['users']
        
        if len(pending) >= 2:
            # Approve first user as non-admin
            user1_id = pending[0]['id']
            user1_email = pending[0]['email']
            user1_num = user1_email.split('@')[0].replace('user', '')
            
            admin_session.post(f"{API_BASE_URL}/api/users/{user1_id}/approve")
            
            # Login as that user
            user_session = requests.Session()
            user_session.post(f"{API_BASE_URL}/api/auth/login", json={
                "email": user1_email,
                "password": f"UserPass{user1_num}123!"
            })
            
            # Try to approve another user (should fail)
            user2_id = pending[1]['id']
            response = user_session.post(f"{API_BASE_URL}/api/users/{user2_id}/approve")
            assert response.status_code == 403


class TestCompleteUserManagementFlow:
    """Test complete user management workflow."""
    
    def test_full_user_management_cycle(self, setup_test_environment):
        """Test complete lifecycle of user management."""
        admin = requests.Session()
        admin.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": "admin@localhost",
            "password": "AdminPass123!"
        })
        
        # 1. Check pending users
        response = admin.get(f"{API_BASE_URL}/api/users/pending")
        initial_pending = len(response.json()['users'])
        assert initial_pending >= 3
        
        # 2. Register new user
        new_user_email = "lifecycle@test.com"
        requests.post(f"{API_BASE_URL}/api/auth/register", json={
            "email": new_user_email,
            "username": "lifecycle",
            "password": "LifecyclePass123!"
        })
        
        # 3. Verify in pending list
        response = admin.get(f"{API_BASE_URL}/api/users/pending")
        assert len(response.json()['users']) == initial_pending + 1
        
        # 4. Get user ID
        new_user = [u for u in response.json()['users'] if u['email'] == new_user_email][0]
        user_id = new_user['id']
        
        # 5. Approve user
        response = admin.post(f"{API_BASE_URL}/api/users/{user_id}/approve")
        assert response.status_code == 200
        
        # 6. Assign role
        response = admin.post(f"{API_BASE_URL}/api/users/{user_id}/roles/3", json={})  # editor
        assert response.status_code == 200
        
        # 7. Verify user can login
        user_session = requests.Session()
        response = user_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": new_user_email,
            "password": "LifecyclePass123!"
        })
        assert response.status_code == 200
        
        # 8. Check user has editor role
        response = user_session.get(f"{API_BASE_URL}/api/auth/me")
        roles = [r['name'] for r in response.json()['user']['roles']]
        assert 'editor' in roles
        
        # 9. Deactivate user
        response = admin.post(f"{API_BASE_URL}/api/users/{user_id}/deactivate")
        assert response.status_code == 200
        
        # 10. Verify user cannot login
        new_session = requests.Session()
        response = new_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": new_user_email,
            "password": "LifecyclePass123!"
        })
        assert response.status_code == 403
        
        # 11. Reactivate user
        response = admin.post(f"{API_BASE_URL}/api/users/{user_id}/activate")
        assert response.status_code == 200
        
        # 12. Verify user can login again
        final_session = requests.Session()
        response = final_session.post(f"{API_BASE_URL}/api/auth/login", json={
            "email": new_user_email,
            "password": "LifecyclePass123!"
        })
        assert response.status_code == 200


class TestSelfRoleModificationPrevention:
    """Test that users cannot modify their own roles."""
    
    def test_cannot_assign_role_to_self_via_roles_endpoint(self, admin_session):
        """Admin should not be able to assign roles to themselves via /api/roles/assign."""
        # Get current user info
        response = admin_session.get(f"{API_BASE_URL}/api/auth/me")
        assert response.status_code == 200
        current_user_id = response.json()['user']['id']
        
        # Try to assign a role to self - should fail
        response = admin_session.post(
            f"{API_BASE_URL}/api/roles/assign",
            json={
                "user_id": current_user_id,
                "role_id": 3  # editor role
            }
        )
        assert response.status_code == 403
        data = response.json()
        assert data['success'] is False
        assert "cannot modify your own roles" in data['message'].lower()
    
    def test_cannot_remove_role_from_self_via_roles_endpoint(self, admin_session):
        """Admin should not be able to remove roles from themselves via /api/roles/remove."""
        # Get current user info
        response = admin_session.get(f"{API_BASE_URL}/api/auth/me")
        assert response.status_code == 200
        current_user = response.json()['user']
        current_user_id = current_user['id']
        
        # Get one of the admin's roles
        if len(current_user['roles']) > 0:
            role_id = current_user['roles'][0]['id']
            
            # Try to remove role from self - should fail
            response = admin_session.post(
                f"{API_BASE_URL}/api/roles/remove",
                json={
                    "user_id": current_user_id,
                    "role_id": role_id
                }
            )
            assert response.status_code == 403
            data = response.json()
            assert data['success'] is False
            assert "cannot modify your own roles" in data['message'].lower()
    
    def test_cannot_assign_role_to_self_via_users_endpoint(self, admin_session):
        """Admin should not be able to assign roles to themselves via /api/users/:id/roles."""
        # Get current user info
        response = admin_session.get(f"{API_BASE_URL}/api/auth/me")
        assert response.status_code == 200
        current_user_id = response.json()['user']['id']
        
        # Try to assign a role to self - should fail
        response = admin_session.post(
            f"{API_BASE_URL}/api/users/{current_user_id}/roles",
            json={"role_name": "editor"}
        )
        assert response.status_code == 403
        data = response.json()
        assert data['success'] is False
        assert "cannot modify your own roles" in data['message'].lower()
    
    def test_cannot_remove_role_from_self_via_users_endpoint(self, admin_session):
        """Admin should not be able to remove roles from themselves via /api/users/:id/roles/:role_id."""
        # Get current user info
        response = admin_session.get(f"{API_BASE_URL}/api/auth/me")
        assert response.status_code == 200
        current_user = response.json()['user']
        current_user_id = current_user['id']
        
        # Get one of the admin's roles
        if len(current_user['roles']) > 0:
            role_id = current_user['roles'][0]['id']
            
            # Try to remove role from self - should fail
            response = admin_session.delete(
                f"{API_BASE_URL}/api/users/{current_user_id}/roles/{role_id}"
            )
            assert response.status_code == 403
            data = response.json()
            assert data['success'] is False
            assert "cannot modify your own roles" in data['message'].lower()
    
    def test_can_assign_role_to_other_user(self, admin_session, setup_test_environment):
        """Admin should still be able to assign roles to other users."""
        # Get a different user
        response = admin_session.get(f"{API_BASE_URL}/api/users")
        users = response.json()['users']
        
        # Get current user ID
        me_response = admin_session.get(f"{API_BASE_URL}/api/auth/me")
        current_user_id = me_response.json()['user']['id']
        
        # Find a different user
        other_user = next((u for u in users if u['id'] != current_user_id), None)
        
        if other_user:
            # Should succeed in assigning role to other user
            response = admin_session.post(
                f"{API_BASE_URL}/api/roles/assign",
                json={
                    "user_id": other_user['id'],
                    "role_id": 3  # editor role
                }
            )
            # Should either succeed (200) or indicate role already exists (409)
            assert response.status_code in [200, 409]

