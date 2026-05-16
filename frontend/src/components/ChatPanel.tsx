

const QUICK_CHIPS = [
  "Find unsupported claims across all slides",
  "Verify numbers on the current slide",
  "Which rows support this slide?",
  "Format citation for selected data",
  "Show me all ⚠️ gaps",
  "Summarize the Excel data",
];

export default function ChatPanel() {
  return (
    <div className="chat-panel" style={{ flex: '0 0 380px' }}>
      {/* Messages area */}
      <div id="chat-messages" className="chat-scroll">
        <div className="chat-welcome">
          <div className="chat-welcome-icon">🔬</div>
          <h3>Welcome to CiteMind</h3>
          <p>
            Upload your PowerPoint and Excel files, then ask me to find citations, verify numbers, or identify unsupported claims.
          </p>
        </div>
      </div>

      {/* Quick chips */}
      <div className="quick-chips" id="quick-chips-bar">
        {QUICK_CHIPS.map((chip, i) => (
          <button key={i} className="quick-chip">
            {chip}
          </button>
        ))}
      </div>

      {/* Input row */}
      <div className="input-row">
        <textarea
          id="chat-input"
          className="chat-input"
          placeholder="Ask about citations, data verification, or gaps..."
          style={{ height: "44px" }}
        />
        <button id="send-btn" className="send-btn">
          ↑
        </button>
      </div>
    </div>
  );
}
