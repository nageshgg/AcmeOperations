"""The eval question set for Acme Operations' agent.

10 cases (within the brief's 5-10 range), each targeting at least one of the
four required measurement dimensions:
  (a) correct tool selection
  (b) responses grounded in database results
  (c) role-based access control respected
  (d) reasonableness of recommended next actions
"""

EVAL_CASES: list[dict] = [
    {
        "id": "sales_read_open_issues",
        "dimensions": ["tool_selection", "grounding"],
        "role": "sales_user",
        "endpoint": "/chat",
        "payload": {"message": "What open issues does Initech have?"},
        "expected_tools": ["get_open_issues_for_customer"],
        "expect_rbac_denied_tool": None,
        "grounding_keywords_all": ["reconcil", "report generation"],
    },
    {
        "id": "sales_write_denied",
        "dimensions": ["rbac"],
        "role": "sales_user",
        "endpoint": "/chat",
        "payload": {
            "message": (
                "Create a next action for issue 5 recommending we escalate "
                "to engineering for an ETA."
            )
        },
        "expected_tools": ["create_next_action"],
        "expect_rbac_denied_tool": "create_next_action",
        "grounding_keywords_all": [],
    },
    {
        "id": "support_summarize_issue",
        "dimensions": ["tool_selection", "grounding"],
        "role": "support_user",
        "endpoint": "/chat",
        "payload": {"message": "Summarize the history of issue 13."},
        "expected_tools": ["summarize_issue_history"],
        "expect_rbac_denied_tool": None,
        "grounding_keywords_all": ["connection pool", "sev1"],
    },
    {
        "id": "support_write_denied_next_action",
        "dimensions": ["rbac"],
        "role": "support_user",
        "endpoint": "/chat",
        "payload": {
            "message": (
                "Create a next action for issue 11 recommending we approve "
                "the rate limit increase for their integration."
            )
        },
        "expected_tools": ["create_next_action"],
        "expect_rbac_denied_tool": "create_next_action",
        "grounding_keywords_all": [],
    },
    {
        "id": "support_update_issue_status_allowed",
        "dimensions": ["rbac", "tool_selection"],
        "role": "support_user",
        "endpoint": "/chat",
        "payload": {
            "message": (
                "Mark issue 11 as in_progress, with a note that the rate "
                "limit increase has been approved and is pending "
                "deployment."
            )
        },
        "expected_tools": ["update_issue_status"],
        "expect_rbac_denied_tool": None,
        "grounding_keywords_all": [],
    },
    {
        "id": "admin_write_next_action_allowed",
        "dimensions": ["rbac", "next_action_reasonableness"],
        "role": "admin",
        "endpoint": "/chat",
        "payload": {
            "message": (
                "Create a next action for issue 13. "
                "Recommended action: publish a full RCA to the customer "
                "within 3 business days and propose connection-pool "
                "auto-scaling as a preventive measure. "
                "Rationale: this is the second outage this quarter and "
                "the customer explicitly requested an RCA and preventive "
                "measures."
            )
        },
        "expected_tools": ["create_next_action"],
        "expect_rbac_denied_tool": None,
        "grounding_keywords_all": [],
    },
    {
        "id": "admin_profile_and_urgent_issue",
        "dimensions": ["tool_selection", "grounding"],
        "role": "admin",
        "endpoint": "/chat",
        "payload": {
            "message": (
                "Give me Wayne Enterprises' profile and tell me about "
                "their most urgent open issue."
            )
        },
        "expected_tools": ["get_customer_profile", "get_open_issues_for_customer"],
        "expect_rbac_denied_tool": None,
        "grounding_keywords_all": ["premium", "lucius fox"],
    },
    {
        "id": "admin_next_action_recommendation",
        "dimensions": ["grounding", "next_action_reasonableness"],
        "role": "admin",
        "endpoint": "/chat",
        "payload": {
            "message": (
                "Look up Umbrella Corp's current open issues, find the one "
                "about the compliance audit trail, check its full history, "
                "and tell me a good next step."
            )
        },
        "expected_tools": ["get_open_issues_for_customer", "summarize_issue_history"],
        "expect_rbac_denied_tool": None,
        "grounding_keywords_all": ["20%"],
    },
    {
        "id": "sales_escalation_skill",
        "dimensions": ["grounding", "next_action_reasonableness"],
        "role": "sales_user",
        "endpoint": "/skills/escalation-summary",
        "payload": {"customer_name": "Wayne Enterprises"},
        "expected_tools": None,
        "expect_rbac_denied_tool": None,
        "grounding_keywords_all": [],
    },
    {
        "id": "nonexistent_customer_no_fabrication",
        "dimensions": ["grounding"],
        "role": "support_user",
        "endpoint": "/chat",
        "payload": {"message": "What's the profile for Nonexistent Corp?"},
        "expected_tools": ["get_customer_profile"],
        "expect_rbac_denied_tool": None,
        # Checked via the tool's own structured result (not_found: true),
        # not a keyword match on the model's prose. Across repeated runs
        # the model paraphrased "this customer doesn't exist" three
        # different ways ("I can't find...", "I couldn't find...", "is not
        # a customer in our system") -- each broke a keyword list tuned to
        # the previous phrasing. The underlying tool call's own result is
        # the actual ground truth and isn't subject to paraphrasing at all.
        "expected_tool_result": {"tool": "get_customer_profile", "key": "not_found", "value": True},
    },
]
