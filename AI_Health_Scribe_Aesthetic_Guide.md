# Mya View Design System & Aesthetic Guide

> A comprehensive design system for Mya View - your private, local health companion that helps families prepare for doctor visits, track conditions, and understand medical documents.

---

## 1. Design Philosophy

### Core Principles

| Principle | Description |
|-----------|-------------|
| **Warm Professionalism** | Like One Medical or Carbon Health - approachable yet trustworthy |
| **Calm Reassurance** | Like Oura or Headspace - reduces anxiety, promotes clarity |
| **Zero Judgment** | No clinical coldness or fear-based medical cues |
| **Privacy First** | Every element reinforces "your data stays local" |

### Emotional Goals
- Users feel **supported, safe, and understood**
- Interface **lowers cognitive load** during stressful health moments
- Design conveys **"a knowledgeable friend who genuinely cares"**

---

## 2. Color System

### Light Theme (Default)

```css
:root {
    /* Backgrounds - warm, not sterile white */
    --bg-primary: #FAF9F7;      /* Main background - warm off-white */
    --bg-secondary: #FFFFFF;     /* Cards, sidebar, inputs */
    --bg-tertiary: #F5F3F0;      /* Subtle sections, hover states */
    --bg-warm: #FDF8F3;          /* Accent backgrounds */

    /* Text - soft charcoal, not harsh black */
    --text-primary: #2D3142;     /* Headlines, body text */
    --text-secondary: #6B7280;   /* Supporting text */
    --text-muted: #9CA3AF;       /* Timestamps, hints */

    /* Accent - sage green (calming, health-positive) */
    --accent: #5B8A72;           /* Primary actions, links */
    --accent-light: #E8F2ED;     /* Hover states, highlights */
    --accent-hover: #4A7461;     /* Button hover */
    --accent-warm: #D4A574;      /* Secondary accent (warm gold) */

    /* Semantic */
    --success: #5B8A72;          /* Same as accent */
    --warning: #E9B872;          /* Gentle amber */
    --error: #C97064;            /* Soft coral, not alarming red */

    /* Borders & Shadows */
    --border: #E8E6E3;
    --border-light: #F0EEEB;
    --shadow-soft: 0 2px 8px rgba(45, 49, 66, 0.06);
    --shadow-medium: 0 4px 20px rgba(45, 49, 66, 0.08);
}
```

### Dark Theme

```css
[data-theme="dark"] {
    --bg-primary: #1C1E26;
    --bg-secondary: #252830;
    --bg-tertiary: #2D3142;
    --bg-warm: #2A2D38;
    --text-primary: #F5F4F2;
    --text-secondary: #A8A9AD;
    --text-muted: #6B7280;
    --accent: #7BA896;           /* Lighter sage for dark mode */
    --accent-light: rgba(123, 168, 150, 0.15);
    --accent-hover: #8FBAA8;
    --border: #3D4152;
    --border-light: #353845;
    --shadow-soft: 0 2px 8px rgba(0, 0, 0, 0.2);
    --shadow-medium: 0 4px 20px rgba(0, 0, 0, 0.25);
}
```

### Color Usage Guidelines

| Element | Color Variable | Notes |
|---------|---------------|-------|
| Page background | `--bg-primary` | Warm off-white, never pure white |
| Cards & panels | `--bg-secondary` | Clean white with soft shadows |
| User message bubbles | `--accent` | Sage green with white text |
| Assistant message bubbles | `--bg-secondary` | White with soft border |
| Primary buttons | `--accent` | Sage green, hover to `--accent-hover` |
| Links in text | `--accent` | Bold when in assistant messages |
| Error states | `--error` | Soft coral, not alarming |

---

## 3. Typography

### Font Stack

```css
font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
```

**DM Sans** was chosen for:
- Friendly, humanist letterforms
- Excellent readability at all sizes
- Distinctive without being distracting
- Good weight range for hierarchy

### Type Scale

| Element | Size | Weight | Letter-spacing |
|---------|------|--------|----------------|
| App title | 20px | 600 | -0.02em |
| Section headers | 18px | 600 | - |
| Body text | 15px | 400 | - |
| Message text | 15px | 400 | line-height: 1.7 |
| Labels | 12px | 500 | 0.05em (uppercase) |
| Timestamps | 12px | 400 | - |
| Hints | 13px | 400 | - |

### Typography Guidelines
- **Never** use generic fonts: Inter, Roboto, Arial
- Line height for chat messages: 1.7 (generous for readability)
- Use `-webkit-font-smoothing: antialiased` for crisp text
- Bold text in assistant messages uses `--accent` color

---

## 4. Spacing & Layout

### Spacing Scale

```css
--radius: 16px;      /* Cards, modals, large buttons */
--radius-sm: 12px;   /* Inputs, small buttons, tags */
```

### Common Spacing Values

| Context | Value |
|---------|-------|
| Page padding | 32px |
| Card padding | 24px |
| Input padding | 16px 20px |
| Section gap | 28px |
| Element gap | 12px |
| Tight gap | 6px |

### Layout Principles
- **800px max-width** for message content
- Sidebar width: 300px (collapsible)
- Mobile breakpoint: 768px
- Use flexbox for all layouts
- Generous whitespace reduces cognitive load

---

## 5. Components

### Buttons

```css
/* Primary Button */
.primary-btn {
    padding: 14px 16px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-weight: 500;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.primary-btn:hover {
    background: var(--accent-hover);
    transform: translateY(-1px);
    box-shadow: var(--shadow-medium);
}

/* Secondary Button */
.secondary-btn {
    padding: 12px 14px;
    background: var(--bg-tertiary);
    color: var(--text-secondary);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
}

.secondary-btn:hover {
    background: var(--accent-light);
    border-color: var(--accent);
    color: var(--accent);
}
```

### Input Fields

```css
.input-wrapper {
    background: var(--bg-primary);
    border: 2px solid var(--border);
    border-radius: var(--radius);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.input-wrapper:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 4px var(--accent-light);
}
```

### Cards & Panels

```css
.card {
    background: var(--bg-secondary);
    border-radius: var(--radius);
    border: 1px solid var(--border-light);
    box-shadow: var(--shadow-soft);
    padding: 24px;
}
```

### Message Bubbles

```css
/* Assistant messages */
.message.assistant .message-bubble {
    background: var(--bg-secondary);
    border: 1px solid var(--border-light);
    border-radius: var(--radius);
    box-shadow: var(--shadow-soft);
}

/* User messages */
.message.user .message-bubble {
    background: var(--accent);
    color: white;
    border: none;
}
```

---

## 6. Motion & Animation

### Transition Standard

```css
--transition-gentle: 0.3s cubic-bezier(0.4, 0, 0.2, 1);
```

### Animation Principles
- Animations feel like **"a breath"**, not a nightclub
- Use **slow easing** for reassurance
- Message entry: gentle fade + slide up
- Loading: breathing dots, not spinning

### Message Entry Animation

```css
@keyframes messageIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.message {
    animation: messageIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}
```

### Loading Indicator (Breathing Dots)

```css
@keyframes breathing {
    0%, 100% {
        transform: scale(1);
        opacity: 0.4;
    }
    50% {
        transform: scale(1.15);
        opacity: 1;
    }
}

.typing-indicator span {
    animation: breathing 1.8s infinite ease-in-out;
}
```

---

## 7. Atmospheric Backgrounds

Soft, blurred gradients create warmth without distraction:

```css
/* Top-right sage gradient */
body::before {
    content: '';
    position: fixed;
    top: -50%;
    right: -20%;
    width: 80%;
    height: 80%;
    background: radial-gradient(
        ellipse,
        rgba(91, 138, 114, 0.08) 0%,
        transparent 70%
    );
    pointer-events: none;
}

/* Bottom-left warm gradient */
body::after {
    content: '';
    position: fixed;
    bottom: -30%;
    left: -10%;
    width: 60%;
    height: 60%;
    background: radial-gradient(
        ellipse,
        rgba(212, 165, 116, 0.06) 0%,
        transparent 70%
    );
    pointer-events: none;
}
```

---

## 8. Page-Specific Guidelines

### Chat (index.html)
- Welcome message with feature cards
- Privacy note prominently displayed
- Supportive banner at top (not warning-style)
- Family member selector always accessible

### Voice (voice.html)
- Large, centered microphone button
- Pulsing animation during recording
- Clear status indicators
- Transcript display for transparency

### Stream/Camera (camera.html)
- Video feed with soft border radius
- Minimal UI during active streaming
- Clear capture/analyze actions
- Results appear in familiar message format

### Graph Explorer (graph.html)
- Interactive canvas visualization
- Node colors match accent palette
- Clear zoom/pan controls
- Query templates for common operations

### Settings (settings.html)
- Grouped sections with clear labels
- Toggle switches for boolean options
- Immediate visual feedback on changes
- Theme toggle with instant preview

---

## 9. Iconography

Use **Feather Icons** (stroke-based, 2px stroke width):

```html
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <!-- icon path -->
</svg>
```

### Common Icons

| Function | Icon |
|----------|------|
| Heart/Health | `heart` path |
| Voice | `mic` |
| Camera | `camera` |
| Settings | `settings` (gear) |
| Privacy | `lock` |
| Document | `file-text` |
| Upload | `upload` |
| Send | `send` |
| New conversation | `plus` |
| Graph | Custom node/edge |

---

## 10. Accessibility

### Color Contrast
- Text on backgrounds: minimum 4.5:1 ratio
- Interactive elements: clear focus states
- Don't rely on color alone for meaning

### Focus States

```css
:focus {
    outline: none;
    box-shadow: 0 0 0 3px var(--accent-light);
    border-color: var(--accent);
}
```

### Touch Targets
- Minimum 44x44px for interactive elements
- Adequate spacing between touch targets

---

## 11. Anti-Patterns (Avoid These)

| Don't | Why |
|-------|-----|
| Pure white (#FFFFFF) backgrounds | Too clinical, causes eye strain |
| Harsh red for errors | Induces anxiety in health context |
| Purple gradients | Generic "AI startup" aesthetic |
| Inter/Roboto fonts | Overused, lacks warmth |
| Fast, flashy animations | Increases cognitive load |
| Dashboard-style layouts | Too data-heavy for health companion |
| Generic chat skeletons | Feels impersonal |
| Clinical/hospital aesthetics | Creates distance, not comfort |

---

## 12. Brand Voice in UI

### Copy Guidelines

| Context | Tone | Example |
|---------|------|---------|
| Welcome | Warm, inviting | "Hello! I'm here to help you and your family..." |
| Privacy | Reassuring | "Everything stays completely private on your local network" |
| Errors | Supportive | "Let's try that again" not "Error occurred" |
| Loading | Patient | "Thinking..." with breathing animation |
| Success | Encouraging | "Got it!" not "Success" |

### Banner Messaging
- **Do**: "Your personal health companion - here to help you feel prepared and informed"
- **Don't**: "WARNING: This is not medical advice"

---

## 13. File Structure

```
frontend/
├── index.html      # Main chat interface
├── voice.html      # Voice assistant
├── camera.html     # Live vision streaming
├── graph.html      # Graph database explorer
├── settings.html   # App settings
└── app.js          # Shared JavaScript
```

All pages share:
- Same CSS variable definitions
- Same font imports
- Same theme toggle logic
- Consistent navigation in sidebar

---

## 14. Implementation Checklist

When building new features:

- [ ] Uses CSS variables (no hardcoded colors)
- [ ] Typography matches scale
- [ ] Animations are gentle (0.3s+)
- [ ] Focus states present
- [ ] Mobile responsive (768px breakpoint)
- [ ] Loading states use breathing animation
- [ ] Error messages are supportive
- [ ] Privacy messaging visible where relevant
- [ ] Theme toggle works correctly
- [ ] Atmospheric gradients preserved

---

*Last updated: November 2025*
*Design system version: 2.0*
