/**
 * Register page functionality
 */

const form = document.getElementById('registerForm');
const errorMessage = document.getElementById('errorMessage');
const successMessage = document.getElementById('successMessage');
const registerButton = document.getElementById('registerButton');
const passwordInput = document.getElementById('password');
const passwordStrengthBar = document.getElementById('passwordStrengthBar');

// Password strength indicator
passwordInput.addEventListener('input', () => {
    const password = passwordInput.value;
    let strength = 0;

    if (password.length >= 8) strength++;
    if (password.match(/[a-z]/) && password.match(/[A-Z]/)) strength++;
    if (password.match(/\d/)) strength++;
    if (password.match(/[^a-zA-Z\d]/)) strength++;

    passwordStrengthBar.className = 'password-strength-bar';
    if (strength >= 3) {
        passwordStrengthBar.classList.add('strong');
    } else if (strength >= 2) {
        passwordStrengthBar.classList.add('medium');
    } else if (strength >= 1) {
        passwordStrengthBar.classList.add('weak');
    }
});

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const email = document.getElementById('email').value;
    const username = document.getElementById('username').value;
    const displayName = document.getElementById('displayName').value;
    const password = document.getElementById('password').value;
    const confirmPassword = document.getElementById('confirmPassword').value;

    // Validate passwords match
    if (password !== confirmPassword) {
        errorMessage.textContent = 'Passwords do not match';
        errorMessage.classList.add('show');
        return;
    }

    // Disable form
    registerButton.disabled = true;
    registerButton.innerHTML = '<span class="loading"></span>Creating account...';
    errorMessage.classList.remove('show');
    successMessage.classList.remove('show');

    try {
        const response = await fetch('/api/auth/register', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ 
                email, 
                username, 
                password,
                display_name: displayName || undefined
            })
        });

        const data = await response.json();

        if (response.ok && data.success) {
            // Check if approval is required
            if (data.user && data.user.requires_approval) {
                // Show success message with approval notice
                successMessage.textContent = data.message || 'Registration successful! Your account is pending administrator approval.';
                successMessage.classList.add('show');
                
                // Disable form
                registerButton.disabled = true;
                registerButton.textContent = 'Registration Complete';
                
                // Redirect to login after a delay
                setTimeout(() => {
                    window.location.href = '/login.html';
                }, 5000);
            } else {
                // Auto-logged in (shouldn't happen with approval system, but just in case)
                successMessage.textContent = 'Account created successfully! Redirecting...';
                successMessage.classList.add('show');
                
                setTimeout(() => {
                    window.location.href = '/';
                }, 1500);
            }
        } else {
            // Show error
            errorMessage.textContent = data.message || 'Registration failed. Please try again.';
            errorMessage.classList.add('show');
            
            // Re-enable form
            registerButton.disabled = false;
            registerButton.textContent = 'Create Account';
        }
    } catch (error) {
        console.error('Registration error:', error);
        errorMessage.textContent = 'An error occurred. Please try again.';
        errorMessage.classList.add('show');
        
        // Re-enable form
        registerButton.disabled = false;
        registerButton.textContent = 'Create Account';
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
