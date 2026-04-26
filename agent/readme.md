# Checkmate Agent Architecture

This directory houses the intelligence layer of the application. The Checkmate agent is orchestrated via **LangGraph**, providing a predictable state machine for AI interactions that handles context isolation, deterministic routing, explicit validations, and Human-in-The-Loop (HIL) checkpoints.

## Core Components
- **`graph.py`**: Defines the LangGraph state schema (`CitationState`), node topology, conditional edges, and handles app-level singleton caching.
- **`nodes.py`**: Contains the pure Python function logic mapping to each graph node. These interact with the LLM and the local environment.
- **`prompts.py`**: Central repository for all LLM prompts used throughout the application.
- **`llm_utils.py`**: Houses the base `llm_service` interacting with Anthropics AI (Claude), and robust retry-based code generation logic (`llm_exec_with_retry`) used for dynamic math transformations.

## Agent Flow

The typical flow for a user query executes the following path:

### 1. Context Resolution (`resolve_mentions`)
Every invocation hits the entry node. The LLM evaluates the user's query against available PPTX slides and Excel Sheets to tightly scope the active context payload.
- **Branch**: If the instruction is highly ambiguous, it halts at `hil_context` alerting the human to classify their intent before proceeding.

### 2. Intent Routing (`route_query`)
Classifies the user query into one of four actions, resolving the downstream path:
* **`suggest`** -> `suggest_citations`: Proposes mappings between slide text and excel data.
* **`verify`** -> `verify_consistency`: Cross-checks explicitly stated numbers in slides against excel source rows.
* **`format`** -> `format_citation`: Formats citation syntaxes.
* **`flag`** -> `flag_gaps`: Proactively flags assertions in slides lacking source backing.

### 3. Agentic Loop & Discrepancy Resolution (`find_relation`)
Triggered explicitly if `verify_consistency` hits a **gap** (no direct numeric match).
`find_relation` implements reasoning algorithms to detect alternate semantic formulations or derived formulas between the sheet and the claim.

* **Autonomous Code Execution**: If a math transformation is required (e.g. sums or fractions), `llm_exec_with_retry` creates, validates, and runs an inline Python extraction method dynamically.

### 4. Human Approval (`hil_verify`)
The graph halts, generating a payload containing the findings & generated code, effectively pushing the process to the frontend Dash HIL interface.
Only upon user validation (`accept`, `reject`, `transform (evaluate)`) will the graph resume and formalize the data onto the citation record.
