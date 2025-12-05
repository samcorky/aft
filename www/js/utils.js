/**
 * Shared utility functions for the AFT application
 */

/**
 * Format a date/timestamp for display in tooltips.
 * Returns a consistent format across the application: "4 Dec 2025 14:30"
 * 
 * @param {Date|string} date - Date object or ISO date string
 * @returns {string} Formatted date string
 */
function formatTooltipDateTime(date) {
  const dateObj = date instanceof Date ? date : new Date(date);
  return `${dateObj.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })} ${dateObj.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;
}
