/**
 * Setup page functionality
 */

const form = document.getElementById('setupForm');
const errorMessage = document.getElementById('errorMessage');
const setupButton = document.getElementById('setupButton');
const passwordInput = document.getElementById('password');
const passwordStrengthBar = document.getElementById('passwordStrengthBar');

// Check if setup is needed
async function checkSetupStatus() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        
        const response = await fetch('/api/auth/setup/status', {
            credentials: 'include',
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        if (response.ok) {
            const data = await response.json();
            
            // If setup is complete, redirect to login
            if (data.setup_complete) {
                window.location.href = '/login.html';
            }
        }
    } catch (error) {
        console.error('Setup status check failed:', error);
    }
}

checkSetupStatus();

// Password strength indicator
passwordInput.addEventListener('input', () => {
    const password = passwordInput.value;
    let strength = 0;

    if (password.length >= 8) strength++;
    if (password.length >= 12) strength++;
    if (password.match(/[a-z]/) && password.match(/[A-Z]/)) strength++;
    if (password.match(/\d/)) strength++;
    if (password.match(/[^a-zA-Z\d]/)) strength++;

    passwordStrengthBar.className = 'password-strength-bar';
    if (strength >= 4) {
        passwordStrengthBar.classList.add('strong');
    } else if (strength >= 3) {
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

    // Validate password strength
    if (password.length < 8) {
        errorMessage.textContent = 'Password must be at least 8 characters';
        errorMessage.classList.add('show');
        return;
    }

    // Disable form
    setupButton.disabled = true;
    setupButton.innerHTML = '<span class="loading"></span>Setting up...';
    errorMessage.classList.remove('show');

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        
        const response = await fetch('/api/auth/setup/admin', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            credentials: 'include',
            body: JSON.stringify({ 
                email, 
                username, 
                password,
                display_name: displayName
            }),
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);

        const data = await response.json();

        if (response.ok && data.success) {
            // Cache user data immediately from setup response
            // The setup response now includes permissions
            if (data.user) {
                sessionStorage.setItem('currentUser', JSON.stringify(data.user));
            }
            
            // Redirect to main app
            setupButton.innerHTML = '✓ Setup Complete! Redirecting...';
            setTimeout(() => {
                window.location.href = '/';
            }, 1500);
        } else {
            // Show error
            errorMessage.textContent = data.message || 'Setup failed. Please try again.';
            errorMessage.classList.add('show');
            
            // Re-enable form
            setupButton.disabled = false;
            setupButton.textContent = 'Complete Setup';
        }
    } catch (error) {
        console.error('Setup error:', error);
        
        if (error.name === 'AbortError') {
            errorMessage.textContent = 'Request timed out. Please check your connection and try again.';
        } else {
            errorMessage.textContent = 'An error occurred. Please try again.';
        }
        errorMessage.classList.add('show');
        
        // Re-enable form
        setupButton.disabled = false;
        setupButton.textContent = 'Complete Setup';
    }
});
