# Eval Results

Run against a live stack at `http://localhost:8000`. 10/10 scored cases passed.

| Case | Role | Dimensions | Result |
|---|---|---|---|
| `sales_read_open_issues` | sales_user | tool_selection, grounding | ✅ PASS |
| `sales_write_denied` | sales_user | rbac | ✅ PASS |
| `support_summarize_issue` | support_user | tool_selection, grounding | ✅ PASS |
| `support_write_denied_next_action` | support_user | rbac | ✅ PASS |
| `support_update_issue_status_allowed` | support_user | rbac, tool_selection | ✅ PASS |
| `admin_write_next_action_allowed` | admin | rbac, next_action_reasonableness | ✅ PASS |
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
- **Response excerpt:** Initech currently has **2** open issues:

1. **Issue ID 5**: Data discrepancy in monthly reconciliation report
   * **Priority**: Critical
   * **Status**: Open
   * **Created**: June 10, 2026
   * **Last Updated**: June 20, 2026

2. **Issue ID 6**: Slow report generation for Q-end close
   * **Priority**: Medium
   * **Status**: Open
   * **Created**: June 25, 2026
   * **Last Updated**: June 26, 2026

### `sales_write_denied`
- **Role:** sales_user  **Endpoint:** `/chat`
- **Request:** `{"message": "Create a next action for issue 5 recommending we escalate to engineering for an ETA."}`
- **HTTP status:** 200
- **rbac:** PASS — `{"pass": true, "tool_result": {"error": "Access denied: your role(s) ['default-roles-acme-operations', 'offline_access', 'sales_user', 'uma_authorization'] do not include any of the roles required to call 'create_next_action': ['admin']."}}`
- **Response excerpt:** I'm sorry, but I was unable to create the next action for issue 5. 

Your current roles (**sales_user**) do not have permission to perform this action. The **admin** role is required to call `create_next_action`.

### `support_summarize_issue`
- **Role:** support_user  **Endpoint:** `/chat`
- **Request:** `{"message": "Summarize the history of issue 13."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["summarize_issue_history"], "actual": ["summarize_issue_history"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **grounding:** PASS — `{"pass": true, "mode": "all", "keyword_hits": {"connection pool": true, "sev1": true}}`
- **Response excerpt:** Here is the history and summary of **Issue 13**:

### **Issue Details**
* **ID:** 13
* **Customer:** Wayne Enterprises
* **Title:** Production outage - dashboard not loading for all users
* **Priority:** Critical (SEV1)
* **Status:** Open
* **Created:** June 30, 2026, 09:14 UTC
* **Last Updated:** June 30, 2026, 11:45 UTC

---

### **Chronological History (June 30, 2026)**

* **09:14 UTC** – **Issue Opened (Lucius Fox - Customer):** Reported a complete, business-critical outage of the customer-f

### `support_write_denied_next_action`
- **Role:** support_user  **Endpoint:** `/chat`
- **Request:** `{"message": "Create a next action for issue 11 recommending we approve the rate limit increase for their integration."}`
- **HTTP status:** 200
- **rbac:** PASS — `{"pass": true, "tool_result": {"error": "Access denied: your role(s) ['default-roles-acme-operations', 'offline_access', 'support_user', 'uma_authorization'] do not include any of the roles required to call 'create_next_action': ['admin']."}}`
- **Response excerpt:** I was unable to create the recommended next action for Issue 11 because my current roles (`default-roles-acme-operations`, `offline_access`, `support_user`, `uma_authorization`) do not include the required **admin** role necessary to call `create_next_action`. 

To complete this request, an user with the **admin** role will need to execute the action.

### `support_update_issue_status_allowed`
- **Role:** support_user  **Endpoint:** `/chat`
- **Request:** `{"message": "Mark issue 11 as in_progress, with a note that the rate limit increase has been approved and is pending deployment."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["update_issue_status"], "actual": ["update_issue_status"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **Response excerpt:** Issue 11 has been successfully marked as **in_progress**. 

**Update Details:**
* **Issue ID:** 11
* **Title:** API rate limiting too aggressive
* **Status:** in_progress
* **Note Added:** "The rate limit increase has been approved and is pending deployment."

### `admin_write_next_action_allowed`
- **Role:** admin  **Endpoint:** `/chat`
- **Request:** `{"message": "Create a next action for issue 13. Recommended action: publish a full RCA to the customer within 3 business days and propose connection-pool auto-scaling as a preventive measure. Rationale: this is the second outage this quarter and the customer explicitly requested an RCA and preventive measures."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["create_next_action"], "actual": ["create_next_action"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **Response excerpt:** The recommended next action for issue 13 has been successfully recorded. 

**Next Action Details:**
* **Recommended Action:** Publish a full RCA to the customer within 3 business days and propose connection-pool auto-scaling as a preventive measure.
* **Rationale:** This is the second outage this quarter and the customer explicitly requested an RCA and preventive measures.
* **Status:** Proposed
* **Created By:** admin
- **⚠ Human review needed (next-action reasonableness is not mechanically scored):** read the response excerpt above and judge whether the recommended action is concrete, specific to the actual issue, and something a real operator could act on immediately.

### `admin_profile_and_urgent_issue`
- **Role:** admin  **Endpoint:** `/chat`
- **Request:** `{"message": "Give me Wayne Enterprises' profile and tell me about their most urgent open issue."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["get_customer_profile", "get_open_issues_for_customer"], "actual": ["get_customer_profile", "get_open_issues_for_customer", "summarize_issue_history"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **grounding:** PASS — `{"pass": true, "mode": "all", "keyword_hits": {"premium": true, "lucius fox": true}}`
- **Response excerpt:** ### **Wayne Enterprises Profile**
*   **Account Tier**: Premium
*   **Industry**: Technology
*   **Primary Contact**: Lucius Fox (lucius.fox@wayne.example)
*   **Account Created**: July 5, 2026

---

### **Most Urgent Open Issue**
*   **Issue ID**: #13
*   **Title**: *Production outage - dashboard not loading for all users*
*   **Priority**: Critical (Status: Open)
*   **Created**: June 30, 2026, 09:14 UTC
*   **Last Update**: June 30, 2026, 11:45 UTC

#### **Summary of the Issue & History:**
1.

### `admin_next_action_recommendation`
- **Role:** admin  **Endpoint:** `/chat`
- **Request:** `{"message": "Look up Umbrella Corp's current open issues, find the one about the compliance audit trail, check its full history, and tell me a good next step."}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["get_open_issues_for_customer", "summarize_issue_history"], "actual": ["create_next_action", "get_open_issues_for_customer", "summarize_issue_history"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **grounding:** PASS — `{"pass": true, "mode": "all", "keyword_hits": {"20%": true}}`
- **Response excerpt:** ### Open Issues for Umbrella Corp
Umbrella Corp currently has **two open issues**:
1. **ID 8**: *Compliance audit trail missing entries* (High Priority)
2. **ID 10**: *Request additional user seats* (Low Priority)

---

### History of the Compliance Audit Trail Issue (ID 8)
* **Description:** An internal compliance audit at Umbrella Corp flagged missing entries in the platform audit log for March, ahead of an upcoming FDA-adjacent regulatory audit.
* **Timeline of Updates:**
  * **June 15, 2026:
- **⚠ Human review needed (next-action reasonableness is not mechanically scored):** read the response excerpt above and judge whether the recommended action is concrete, specific to the actual issue, and something a real operator could act on immediately.

### `sales_escalation_skill`
- **Role:** sales_user  **Endpoint:** `/skills/escalation-summary`
- **Request:** `{"customer_name": "Wayne Enterprises"}`
- **HTTP status:** 200
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **Response excerpt:** Wayne Enterprises, a Premium technology customer, is experiencing heightened risk due to recurring platform instability and slow resolution times. On June 30, 2026, they suffered a critical SEV1 production outage, and while dashboard access has been restored, the customer has explicitly demanded a formal Root Cause Analysis (RCA) and preventive measures, noting this is their second outage this quarter. Furthermore, a medium-priority API rate-limiting issue has been unresolved for a month, though
- **⚠ Human review needed (next-action reasonableness is not mechanically scored):** read the response excerpt above and judge whether the recommended action is concrete, specific to the actual issue, and something a real operator could act on immediately.

### `nonexistent_customer_no_fabrication`
- **Role:** support_user  **Endpoint:** `/chat`
- **Request:** `{"message": "What's the profile for Nonexistent Corp?"}`
- **HTTP status:** 200
- **tool_selection:** PASS — `{"pass": true, "expected": ["get_customer_profile"], "actual": ["get_customer_profile"], "missing": []}`
- **rbac:** PASS — `{"pass": true, "unexpected_denials": []}`
- **tool_result:** PASS — `{"pass": true, "expected": {"tool": "get_customer_profile", "key": "not_found", "value": true}, "actual_result": {"not_found": true}}`
- **Response excerpt:** I couldn't find a customer profile for "Nonexistent Corp." It looks like they might not be in our database.
