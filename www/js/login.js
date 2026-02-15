/**
 * Login page functionality
 */

const form = document.getElementById('loginForm');
const errorMessage = document.getElementById('errorMessage');
const loginButton = document.getElementById('loginButton');

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const email = document.getElementById('email').value;
    const password = document.getElementById('password').value;
    const rememberMe = document.getElementById('rememberMe').checked;

    // Disable form
    loginButton.disabled = true;
    loginButton.innerHTML = '<span class="loading"></span>Signing in...';
    errorMessage.classList.remove('show');

    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ email, password, remember_me: rememberMe })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Redirect to main app
            window.location.href = '/';
        } else {
            // Show error
            errorMessage.textContent = data.message || 'Login failed. Please try again.';
            errorMessage.classList.add('show');
            
            // Re-enable form
            loginButton.disabled = false;
            loginButton.textContent = 'Sign In';
        }
    } catch (error) {
        console.error('Login error:', error);
        errorMessage.textContent = 'An error occurred. Please try again.';
        errorMessage.classList.add('show');
        
        // Re-enable form
        loginButton.disabled = false;
        loginButton.textContent = 'Sign In';
    }
});

// Check if already logged in
async function checkAuth() {
    try {
        // First check if setup is complete
        const setupResponse = await fetch('/api/auth/setup/status', {
            credentials: 'include'
        });
        
        if (setupResponse.ok) {
            const setupData = await setupResponse.json();
            
            // If setup not complete, redirect to setup
            if (!setupData.setup_complete) {
                window.location.href = '/setup.html';
                return;
            }
        }
        
        // Check if already authenticated
        const response = await fetch('/api/auth/check', {
            credentials: 'include'
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.authenticated) {
                // Already logged in, redirect to main app
                window.location.href = '/';
            }
        }
    } catch (error) {
        console.log('Not authenticated');
    }
}

checkAuth();
