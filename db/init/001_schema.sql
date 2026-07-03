-- Acme Operations schema.
-- Auto-run by the official postgres:16 image on first container start
-- (every .sql/.sh file in /docker-entrypoint-initdb.d runs once, in
-- filename order, only when the data volume is empty).

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    industry TEXT NOT NULL,
    account_tier TEXT NOT NULL CHECK (account_tier IN ('Standard', 'Premium', 'Enterprise')),
    primary_contact_name TEXT NOT NULL,
    primary_contact_email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE issues (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'resolved', 'closed')),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);

CREATE INDEX idx_issues_customer_id ON issues(customer_id);
CREATE INDEX idx_issues_status ON issues(status);

-- Append-only history of an issue. This is what the "summarise the history
-- of a specific issue" tool reads: one row per status change / support note.
CREATE TABLE issue_updates (
    id SERIAL PRIMARY KEY,
    issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    author TEXT NOT NULL,
    update_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_issue_updates_issue_id ON issue_updates(issue_id);

-- Recommended next actions. The agent's "create a recommended next action
-- for a specific issue" tool writes here; admin/support roles can update
-- `status` as the recommendation is acted on or dismissed.
CREATE TABLE next_actions (
    id SERIAL PRIMARY KEY,
    issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    recommended_action TEXT NOT NULL,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'accepted', 'dismissed')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_next_actions_issue_id ON next_actions(issue_id);

-- Local mirror of the Keycloak identities created in Step 3. Keycloak's JWT
-- (realm roles) remains the actual source of truth for authorization
-- decisions at request time; this table exists for auditability and joins
-- (e.g. "who created this next action") without a round trip to Keycloak.
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('sales_user', 'support_user', 'admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
