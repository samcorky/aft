# Accessibility Guidelines

This document outlines accessibility best practices for the AFT application to ensure all features are usable by everyone, including users with disabilities.

## General Principles

1. **Semantic HTML**: Use appropriate HTML elements for their intended purpose (e.g., `<button>` for buttons, `<nav>` for navigation)
2. **Keyboard Navigation**: All interactive elements must be keyboard accessible
3. **Screen Reader Support**: Provide appropriate ARIA attributes and alternative text
4. **Color Contrast**: Ensure sufficient contrast ratios for text and interactive elements
5. **Focus Management**: Visible focus indicators and logical tab order

## Modal Dialogs

All modal dialogs MUST include the following ARIA attributes:

```html
<div id="myModal" class="modal" 
     role="dialog" 
     aria-modal="true" 
     aria-labelledby="modal-title" 
     aria-describedby="modal-description">
  <div class="modal-content">
    <div class="modal-header">
      <h2 id="modal-title">Modal Title</h2>
    </div>
    <div class="modal-body">
      <p id="modal-description">Modal description text</p>
    </div>
    <div class="modal-actions">
      <button class="btn btn-secondary">Cancel</button>
      <button class="btn btn-primary">Confirm</button>
    </div>
  </div>
</div>
```

### Required Attributes:
- `role="dialog"` - Identifies the element as a dialog
- `aria-modal="true"` - Indicates this is a modal dialog that blocks interaction with the rest of the page
- `aria-labelledby` - References the ID of the element containing the modal's title
- `aria-describedby` - References the ID of the element containing the modal's description

### JavaScript Considerations:
- Trap focus within the modal when open
- Return focus to the triggering element when closed
- Allow ESC key to close the modal
- Disable background scrolling when modal is open

## Forms

### Labels
Every form input MUST have an associated label:

```html
<label for="inputId">Field Name</label>
<input type="text" id="inputId" name="fieldName">
```

### Required Fields
Indicate required fields both visually and programmatically:

```html
<label for="email">Email <span aria-label="required">*</span></label>
<input type="email" id="email" required aria-required="true">
```

### Error Messages
Associate error messages with their inputs:

```html
<label for="username">Username</label>
<input type="text" id="username" aria-describedby="username-error" aria-invalid="true">
<div id="username-error" role="alert">Username is required</div>
```

## Buttons and Links

### Icons
Provide text alternatives for icon-only buttons:

```html
<!-- Option 1: aria-label -->
<button aria-label="Delete item">🗑️</button>

<!-- Option 2: Visually hidden text -->
<button>
  <span class="sr-only">Delete item</span>
  <span aria-hidden="true">🗑️</span>
</button>
```

### Toggle Buttons
Indicate state for toggle buttons:

```html
<button type="button" 
        aria-pressed="false" 
        id="backupToggle">
  Enable Backups
</button>
```

## Status Messages

Use ARIA live regions for dynamic status updates:

```html
<!-- Polite: Announces when user is idle -->
<div role="status" aria-live="polite" aria-atomic="true" id="status-message">
  Settings saved successfully
</div>

<!-- Assertive: Announces immediately (errors) -->
<div role="alert" aria-live="assertive" aria-atomic="true" id="error-message">
  Failed to save settings
</div>
```

## Loading States

Indicate loading states to screen readers:

```html
<button aria-busy="true" disabled>
  <span role="status">Loading...</span>
</button>
```

## Images

All images must have appropriate alt text:

```html
<!-- Decorative images -->
<img src="decoration.png" alt="" role="presentation">

<!-- Informative images -->
<img src="chart.png" alt="Bar chart showing 25% increase in sales">
```

## Tables

Use proper table structure with headers:

```html
<table>
  <thead>
    <tr>
      <th scope="col">Name</th>
      <th scope="col">Date</th>
      <th scope="col">Size</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>backup.sql</td>
      <td>2025-11-30</td>
      <td>2.5 MB</td>
    </tr>
  </tbody>
</table>
```

## Navigation

### Skip Links
Provide skip navigation links:

```html
<a href="#main-content" class="skip-link">Skip to main content</a>
<main id="main-content">
  <!-- Page content -->
</main>
```

### Landmarks
Use semantic landmarks or ARIA roles:

```html
<header role="banner">
<nav role="navigation" aria-label="Main navigation">
<main role="main">
<aside role="complementary">
<footer role="contentinfo">
```

## Testing

### Manual Testing Checklist
- [ ] Keyboard navigation (Tab, Shift+Tab, Enter, Escape, Arrow keys)
- [ ] Screen reader testing (NVDA, JAWS, or VoiceOver)
- [ ] Focus indicators visible
- [ ] Color contrast ratios pass WCAG AA (4.5:1 for normal text)
- [ ] Zoom to 200% without loss of functionality
- [ ] No reliance on color alone for information

### Tools
- **axe DevTools**: Browser extension for automated accessibility testing
- **WAVE**: Web accessibility evaluation tool
- **Lighthouse**: Built into Chrome DevTools
- **Screen Readers**: 
  - Windows: NVDA (free) or JAWS
  - macOS: VoiceOver (built-in)
  - Linux: Orca

## Resources

- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [MDN Accessibility](https://developer.mozilla.org/en-US/docs/Web/Accessibility)
- [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/)
- [WebAIM](https://webaim.org/)

## Implementation Checklist for New Features

When adding new features, ensure:

- [ ] All interactive elements are keyboard accessible
- [ ] All images have appropriate alt text
- [ ] All forms have proper labels and error handling
- [ ] All modals have proper ARIA attributes
- [ ] All status messages use live regions
- [ ] Color contrast meets WCAG AA standards
- [ ] Focus management is handled correctly
- [ ] Screen reader testing completed
- [ ] Documentation updated if needed
