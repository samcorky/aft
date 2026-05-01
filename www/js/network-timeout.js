/**
 * Shared request timeout helpers for auth/setup pages.
 */
(function () {
    function getNetworkTimeoutMultiplier() {
        const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
        if (!connection) {
            return 1;
        }

        let multiplier = 1;
        switch (connection.effectiveType) {
            case 'slow-2g':
                multiplier = 4;
                break;
            case '2g':
                multiplier = 3;
                break;
            case '3g':
                multiplier = 2;
                break;
            default:
                multiplier = 1;
                break;
        }

        if (connection.saveData) {
            multiplier = Math.max(multiplier, 2);
        }

        return multiplier;
    }

    function createTimeoutController(baseTimeoutMs = 5000, maxTimeoutMs = 25000) {
        const timeoutMs = Math.min(baseTimeoutMs * getNetworkTimeoutMultiplier(), maxTimeoutMs);
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
        return { controller, timeoutId, timeoutMs };
    }

    window.NetworkTimeoutUtils = {
        getNetworkTimeoutMultiplier,
        createTimeoutController
    };
})();
