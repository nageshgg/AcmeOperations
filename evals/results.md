# Eval Results

Run against a live stack at `http://localhost:8000`. 8/8 scored cases passed.

| Case | Role | Dimensions | Result |
|---|---|---|---|
| `sales_read_open_issues` | sales_user | tool_selection, grounding | ✅ PASS |
| `sales_write_denied` | sales_user | rbac | ✅ PASS |
| `support_summarize_issue` | support_user | tool_selection, grounding | ✅ PASS |
| `support_write_allowed` | support_user | rbac, next_action_reasonableness | ✅ PASS |
| `admin_profile_and_urgent_issue` | admin | tool_selection, grounding | ✅ PASS |
| `admin_next_action_recommendation` | admin | grounding, next_action_reasonableness | ✅ PASS |
| `sales_escalation_skill` | sales_user | grounding, next_action_reasonableness | ✅ PASS |
| `nonexistent_customer_no_fabrication` | support_user | grounding | ✅ PASS |

## Case Detail

### `sales_read_open_issues`
- **Role:** sales_user  **Endpoint:** `/chat`
- **Request:** `{"message": "What open issues does Initech have?"}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["get_open_issues_for_customer"], "actual": ["get_open_issues_for_customer"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **grounding:** PASS — `{"pass": true, "mode": "all", "keyword_hits": {"reconcil": true, "report generation": true}}`
- **Response excerpt:** Initech has 2 open issues: 
1. **Data discrepancy in monthly reconciliation report** (ID: 5, Priority: critical, Created: 2026-06-10, Last updated: 2026-06-20)
2. **Slow report generation for Q-end close** (ID: 6, Priority: medium, Created: 2026-06-25, Last updated: 2026-06-26)

### `sales_write_denied`
- **Role:** sales_user  **Endpoint:** `/chat`
- **Request:** `{"message": "Create a next action for issue 5 recommending we escalate to engineering for an ETA."}`
- **HTTP status:** 200
- **rbac:** PASS — `{"pass": true, "tool_result": {"error": "Access denied: your role(s) ['default-roles-acme-operations', 'offline_access', 'sales_user', 'uma_authorization'] do not include any of the roles required to call 'create_next_action': ['admin', 'support_user']."}}`
- **Response excerpt:** I am unable to create a next action. It seems my role, 'sales_user', does not have the necessary permissions. Only 'admin' or 'support_user' roles can create next actions.

### `support_summarize_issue`
- **Role:** support_user  **Endpoint:** `/chat`
- **Request:** `{"message": "Summarize the history of issue 13."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["summarize_issue_history"], "actual": ["summarize_issue_history"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **grounding:** PASS — `{"pass": true, "mode": "all", "keyword_hits": {"connection pool": true, "sev1": true}}`
- **Response excerpt:** Here's a summary of the history for issue 13:

**Issue ID:** 13
**Title:** Production outage - dashboard not loading for all users
**Customer:** Wayne Enterprises
**Priority:** Critical
**Status:** Open

**Description:** Full outage of the customer-facing dashboard starting 09:14 UTC, affecting all users.

**Timeline of updates:**
*   **09:14 UTC (Customer):** Reported dashboard completely down for all users, emphasizing its business-critical nature.
*   **09:20 UTC (Support):** On-call engineer

### `support_write_allowed`
- **Role:** support_user  **Endpoint:** `/chat`
- **Request:** `{"message": "Create a next action for issue 13. Recommended action: publish a full RCA to the customer within 3 business days and propose connection-pool auto-scaling as a preventive measure. Rationale: this is the second outage this quarter and the customer explicitly requested an RCA and preventive measures."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["create_next_action"], "actual": ["create_next_action"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **Response excerpt:** I've recorded the recommended next action for issue 13: "publish a full RCA to the customer within 3 business days and propose connection-pool auto-scaling as a preventive measure." The rationale is that this is the second outage this quarter and the customer explicitly requested an RCA and preventive measures.
- **⚠ Human review needed (next-action reasonableness is not mechanically scored):** read the response excerpt above and judge whether the recommended action is concrete, specific to the actual issue, and something a real operator could act on immediately.

### `admin_profile_and_urgent_issue`
- **Role:** admin  **Endpoint:** `/chat`
- **Request:** `{"message": "Give me Wayne Enterprises' profile and tell me about their most urgent open issue."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["get_customer_profile", "get_open_issues_for_customer"], "actual": ["get_customer_profile", "get_open_issues_for_customer"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **grounding:** PASS — `{"pass": true, "mode": "all", "keyword_hits": {"premium": true, "lucius fox": true}}`
- **Response excerpt:** Wayne Enterprises is a **Premium** tier customer in the **Technology** industry. Their primary contact is Lucius Fox, whose email is lucius.fox@wayne.example.

Their most urgent open issue is a **critical production outage** where the dashboard is not loading for all users (ID: 13).

### `admin_next_action_recommendation`
- **Role:** admin  **Endpoint:** `/chat`
- **Request:** `{"message": "Look up Umbrella Corp's current open issues, find the one about the compliance audit trail, check its full history, and tell me a good next step."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["get_open_issues_for_customer", "summarize_issue_history"], "actual": ["get_open_issues_for_customer", "summarize_issue_history"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **grounding:** PASS — `{"pass": true, "mode": "all", "keyword_hits": {"20%": true}}`
- **Response excerpt:** Here's the summary of the "Compliance audit trail missing entries" issue for Umbrella Corp (ID: 8):

**Description:** Umbrella Corp's internal compliance audit found gaps in their platform audit log for March, which is critical ahead of an upcoming regulatory audit.

**History:**
*   **June 15:** Umbrella Corp reported the missing audit log entries.
*   **June 18:** Support confirmed that the logging service dropped a subset of audit events on March 18th during a deployment and began recovering 
- **⚠ Human review needed (next-action reasonableness is not mechanically scored):** read the response excerpt above and judge whether the recommended action is concrete, specific to the actual issue, and something a real operator could act on immediately.

### `sales_escalation_skill`
- **Role:** sales_user  **Endpoint:** `/skills/escalation-summary`
- **Request:** `{"customer_name": "Wayne Enterprises"}`
- **HTTP status:** 200
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **Response excerpt:** Wayne Enterprises, a Premium account, is currently facing critical operational challenges with two open issues. A recent production outage for their dashboard on June 30th, though mitigated, was the second such incident this quarter, prompting the customer to demand a full Root Cause Analysis (RCA) and preventive measures. Concurrently, a medium-priority API rate-limiting issue causing dropped webhooks has been open for over three weeks, with a proposed solution awaiting engineering sign-off. Th
- **⚠ Human review needed (next-action reasonableness is not mechanically scored):** read the response excerpt above and judge whether the recommended action is concrete, specific to the actual issue, and something a real operator could act on immediately.

### `nonexistent_customer_no_fabrication`
- **Role:** support_user  **Endpoint:** `/chat`
- **Request:** `{"message": "What's the profile for Nonexistent Corp?"}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["get_customer_profile"], "actual": ["get_customer_profile"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **tool_result:** PASS — `{"pass": true, "expected": {"tool": "get_customer_profile", "key": "not_found", "value": true}, "actual_result": {"not_found": true}}`
- **Response excerpt:** I can't find a customer named "Nonexistent Corp". Did you spell it correctly?
