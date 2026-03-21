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
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ email, password, remember_me: rememberMe }),
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);

        const data = await response.json();

        if (response.ok && data.success) {
            // Cache user data immediately from login response
            // The login response now includes permissions
            if (data.user) {
                sessionStorage.setItem('currentUser', JSON.stringify(data.user));
            }
            
            // Check if there's a redirect URL stored (from before logout)
            const redirectUrl = sessionStorage.getItem('redirectAfterLogin');
            sessionStorage.removeItem('redirectAfterLogin'); // Clean up
            
            // Validate redirect URL to prevent open redirect attacks
            // Only allow relative paths (no external URLs)
            let targetUrl = '/';
            if (redirectUrl && redirectUrl.startsWith('/') && !redirectUrl.startsWith('//')) {
                targetUrl = redirectUrl;
            }
            
            // Redirect to stored page or default to main app
            window.location.href = targetUrl;
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
        
        if (error.name === 'AbortError') {
            errorMessage.textContent = 'Request timed out. Please check your connection and try again.';
        } else {
            errorMessage.textContent = 'An error occurred. Please try again.';
        }
        errorMessage.classList.add('show');
        
        // Re-enable form
        loginButton.disabled = false;
        loginButton.textContent = 'Sign In';
    }
});

// Check if already logged in
async function checkAuth() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        
        // First check if setup is complete
        const setupResponse = await fetch('/api/auth/setup/status', {
            credentials: 'include',
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (setupResponse.ok) {
            const setupData = await setupResponse.json();
            
            // If setup not complete, redirect to setup
            if (!setupData.setup_complete) {
                window.location.href = '/setup.html';
                return;
            }
        }
        
        // Check if already authenticated
        const controller2 = new AbortController();
        const timeoutId2 = setTimeout(() => controller2.abort(), 5000);
        
        const response = await fetch('/api/auth/check', {
            credentials: 'include',
            signal: controller2.signal
        });
        
        clearTimeout(timeoutId2);
        
        if (response.ok) {
            const data = await response.json();
            if (data.authenticated) {
                // Already logged in, check for redirect URL or go to main app
                const redirectUrl = sessionStorage.getItem('redirectAfterLogin');
                sessionStorage.removeItem('redirectAfterLogin'); // Clean up
                
                // Validate redirect URL to prevent open redirect attacks
                // Only allow relative paths (no external URLs)
                let targetUrl = '/';
                if (redirectUrl && redirectUrl.startsWith('/') && !redirectUrl.startsWith('//')) {
                    targetUrl = redirectUrl;
                }
                
                window.location.href = targetUrl;
            }
        }
    } catch (error) {
        if (error.name !== 'AbortError') {
            console.log('Not authenticated');
        }
    }
}

checkAuth();
