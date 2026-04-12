# Front-end Callbacks (`callbacks/`)

This directory houses the Dash callback functions, acting as the controller layer bridging the frontend UI interactivity and the backend processing/DB/Agent layers.

## Modules
- **`chat_callbacks.py`**: Manages the chat functionality, triggering the `Invoke` logic for the LangGraph agent, managing loading spinners, tracking conversation history, and handling frontend resumption of human-in-the-loop triggers (`hil-accept-btn`, `hil-reject-btn`, etc.).
- **`citation_callbacks.py`**: Controls the Citation Panel states. Filters the list of citations by active tabs and statuses, drives DB updates when humans accept/reject citations, and builds out the Human Verification dynamic UI cards natively in Dash.
- **`selection_callbacks.py`**: Hooks into the Javascript-layer interactions (Clicking bounding box shape overlays, Canvas Drag rectangles, HTML text selections) computing server-side hit testing to determine which PowerPoint shape was intentionally picked and updates DB & context tracking.
- **`slide_callbacks.py`**: Coordinates the slide viewer iframe. Handles form inputs (Uploading the `PPTX` and `XLSX`), instantiating backend parsers rapidly, parsing data files into SQLite, and iterating via arrow buttons.
