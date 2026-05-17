# UI Components (`components/`)

This directory encapsulates the distinct visual modules for the Dash UI layout pattern. By isolating these, `layout.py` stays clean and semantic.

## Modules
- **`slide_panel.py`**: Handles generating the left UI container, framing the interactive slide Iframe output, wrapping it with contextual navigational buttons and zoom controls.
- **`citation_panel.py`**: Implements the layout blocks for the Citation list, defining the structure of individual citation cards matching them to their verification states.
- **`chat_panel.py`**: Wraps the chat components in a flex layout, parsing conversation history into visually distinct "User" and "AI Assistant" speech bubbles with markdown parsing support.
- **`excel_strip.py`**: Formats the uploaded raw Excel data into an interactive, horizontal slice layout viewable under the slides panel.
