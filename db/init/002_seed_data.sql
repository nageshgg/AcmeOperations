-- Seed data for Acme Operations.
-- 5 customers, 16 issues (10 open/in_progress, 6 resolved/closed), several
-- issues with multi-entry update histories (including two escalation-worthy
-- ones) so every agent capability has real material to work against:
--   - retrieve customer profile by name
--   - retrieve all open issues for a customer
--   - summarise the history of a specific issue
--   - recommend a next action for a specific issue

-- =========================================================================
-- customers (ids assigned 1-5 in insertion order)
-- =========================================================================
INSERT INTO customers (name, industry, account_tier, primary_contact_name, primary_contact_email) VALUES
('Globex Corporation', 'Manufacturing', 'Enterprise', 'Dana Whitfield', 'dana.whitfield@globex.example'),
('Initech',             'Finance',       'Standard',   'Peter Gibbons',   'peter.gibbons@initech.example'),
('Umbrella Corp',       'Pharmaceuticals','Enterprise','Alice Marlow',    'alice.marlow@umbrella.example'),
('Wayne Enterprises',   'Technology',    'Premium',    'Lucius Fox',      'lucius.fox@wayne.example'),
('Stark Industries',    'Defense & Technology','Enterprise','Pepper Potts','pepper.potts@stark.example');

-- =========================================================================
-- issues (ids assigned 1-16 in insertion order)
-- =========================================================================

-- Globex Corporation (customer_id = 1)
INSERT INTO issues (customer_id, title, description, status, priority, created_at, updated_at, closed_at) VALUES
(1, 'ERP integration sync failures',
    'Nightly batch sync between Acme platform and customer ERP is failing intermittently, causing stale inventory data.',
    'open', 'high', '2026-05-02 08:12:00+00', '2026-05-14 16:40:00+00', NULL),
(1, 'Invoice export formatting bug',
    'Exported invoice PDFs show misaligned line-item totals when more than 20 line items are present.',
    'open', 'medium', '2026-06-01 10:05:00+00', '2026-06-03 09:15:00+00', NULL),
(1, 'Login SSO intermittent failures',
    'A subset of users reported being unable to log in via SAML SSO during a ~2 hour window.',
    'resolved', 'medium', '2026-04-10 14:22:00+00', '2026-04-11 11:00:00+00', '2026-04-11 11:00:00+00'),
(1, 'Feature request: bulk export',
    'Customer requested a bulk CSV export option for the reporting dashboard.',
    'closed', 'low', '2026-03-15 09:00:00+00', '2026-03-28 17:30:00+00', '2026-03-28 17:30:00+00');

-- Initech (customer_id = 2)
INSERT INTO issues (customer_id, title, description, status, priority, created_at, updated_at, closed_at) VALUES
(2, 'Data discrepancy in monthly reconciliation report',
    'Monthly reconciliation totals do not match the customer''s source ledger; discrepancy is material for their close process.',
    'open', 'critical', '2026-06-10 07:45:00+00', '2026-06-20 15:10:00+00', NULL),
(2, 'Slow report generation for Q-end close',
    'Quarter-end financial reports are taking 15+ minutes to generate, up from under 2 minutes previously.',
    'open', 'medium', '2026-06-25 13:00:00+00', '2026-06-26 09:00:00+00', NULL),
(2, 'Password reset emails delayed',
    'Password reset emails were arriving 20-30 minutes late due to an email queue backlog.',
    'closed', 'low', '2026-05-05 11:20:00+00', '2026-05-06 10:00:00+00', '2026-05-06 10:00:00+00');

-- Umbrella Corp (customer_id = 3)
INSERT INTO issues (customer_id, title, description, status, priority, created_at, updated_at, closed_at) VALUES
(3, 'Compliance audit trail missing entries',
    'Internal compliance audit found gaps in the audit log for March, ahead of an upcoming regulatory audit.',
    'open', 'high', '2026-06-15 09:30:00+00', '2026-06-22 14:00:00+00', NULL),
(3, 'UI rendering issue on Safari',
    'Dashboard charts render incorrectly on Safari 17 due to a CSS grid fallback issue.',
    'closed', 'low', '2026-04-20 08:00:00+00', '2026-04-25 12:00:00+00', '2026-04-25 12:00:00+00'),
(3, 'Request additional user seats',
    'Customer requested 15 additional user seats under their Enterprise agreement.',
    'open', 'low', '2026-06-28 16:00:00+00', '2026-06-28 16:00:00+00', NULL);

-- Wayne Enterprises (customer_id = 4)
INSERT INTO issues (customer_id, title, description, status, priority, created_at, updated_at, closed_at) VALUES
(4, 'API rate limiting too aggressive',
    'Customer''s integration is being rate-limited during legitimate burst traffic, causing dropped webhook deliveries.',
    'open', 'medium', '2026-06-05 10:00:00+00', '2026-06-08 11:30:00+00', NULL),
(4, 'Onboarding training request',
    'Customer requested a training session for their new support team members.',
    'closed', 'low', '2026-05-01 09:00:00+00', '2026-05-10 15:00:00+00', '2026-05-10 15:00:00+00'),
(4, 'Production outage - dashboard not loading for all users',
    'Full outage of the customer-facing dashboard starting 09:14 UTC; all users affected.',
    'open', 'critical', '2026-06-30 09:14:00+00', '2026-06-30 11:45:00+00', NULL);

-- Stark Industries (customer_id = 5)
INSERT INTO issues (customer_id, title, description, status, priority, created_at, updated_at, closed_at) VALUES
(5, 'Security review completed',
    'Annual third-party security review of Acme''s platform, requested by Stark''s security team.',
    'closed', 'medium', '2026-04-01 09:00:00+00', '2026-04-18 17:00:00+00', '2026-04-18 17:00:00+00'),
(5, 'Custom integration failing after latest release',
    'Customer''s custom-built integration began failing authentication after the June platform release.',
    'open', 'high', '2026-07-01 08:20:00+00', '2026-07-02 10:00:00+00', NULL),
(5, 'Billing discrepancy for last quarter',
    'Customer reports being billed for 200 more API calls than their own usage logs show for June.',
    'open', 'medium', '2026-07-02 13:00:00+00', '2026-07-02 13:00:00+00', NULL);

-- =========================================================================
-- issue_updates (multi-entry histories; issue_id references are stable
-- because this runs once against an empty, freshly-created table)
-- =========================================================================

-- Issue 1: Globex ERP integration sync failures (rich history)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(1, 'Dana Whitfield (Customer)', 'Reported that overnight inventory sync has failed 3 nights in a row; downstream reports show stale stock levels.', '2026-05-02 08:12:00+00'),
(1, 'Priya Nair (Support)', 'Reproduced the failure in staging. Sync job logs show repeated HTTP 429 responses from the customer''s ERP API endpoint.', '2026-05-05 13:00:00+00'),
(1, 'Priya Nair (Support)', 'Escalated to engineering. Root cause appears to be our sync job exceeding the ERP vendor''s undocumented rate limit after a recent batch-size increase.', '2026-05-09 09:45:00+00'),
(1, 'Engineering (Jordan Lee)', 'Reduced batch size and added exponential backoff on 429 responses. Fix deployed to staging; awaiting customer validation window before production rollout.', '2026-05-14 16:40:00+00');

-- Issue 2: Globex invoice export formatting bug
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(2, 'Dana Whitfield (Customer)', 'Invoices with 20+ line items show totals column overlapping the description column in exported PDFs.', '2026-06-01 10:05:00+00'),
(2, 'Priya Nair (Support)', 'Confirmed the bug; PDF template does not wrap correctly past 20 rows. Filed as a template rendering defect.', '2026-06-03 09:15:00+00');

-- Issue 3: Globex SSO (resolved)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(3, 'Dana Whitfield (Customer)', 'Multiple users unable to complete SSO login between 13:00-15:00 UTC; getting a generic "authentication failed" error.', '2026-04-10 14:22:00+00'),
(3, 'Support (Sam Rivera)', 'Identified an expired SAML signing certificate on our identity provider integration. Certificate rotated and login restored for all affected users.', '2026-04-11 11:00:00+00');

-- Issue 4: Globex bulk export feature request (closed)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(4, 'Dana Whitfield (Customer)', 'Requested a bulk CSV export option for the reporting dashboard to replace manual per-report exports.', '2026-03-15 09:00:00+00'),
(4, 'Product (Morgan Ellis)', 'Shipped bulk CSV export in the March release. Customer confirmed the feature meets their needs; closing.', '2026-03-28 17:30:00+00');

-- Issue 5: Initech reconciliation discrepancy (escalation-worthy, rich history)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(5, 'Peter Gibbons (Customer)', 'Monthly reconciliation report totals are off by roughly $4,200 versus our internal ledger. This is blocking our close.', '2026-06-10 07:45:00+00'),
(5, 'Support (Sam Rivera)', 'Reproduced the discrepancy. Traced to currency conversion rounding differences on a small number of multi-currency transactions.', '2026-06-12 12:00:00+00'),
(5, 'Support (Sam Rivera)', 'Escalated to the finance engineering team given the compliance sensitivity of reconciliation data for this customer.', '2026-06-14 09:00:00+00'),
(5, 'Support (Sam Rivera)', 'Provided customer a manual reconciliation workaround (corrected spreadsheet) so their close is not blocked while the permanent fix is in progress.', '2026-06-17 15:30:00+00'),
(5, 'Engineering (Jordan Lee)', 'Confirmed root cause: FX rate cache was serving a stale rate for one currency pair for ~36 hours. Cache invalidation fix is in code review; no ETA committed yet.', '2026-06-20 15:10:00+00');

-- Issue 6: Initech slow report generation
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(6, 'Peter Gibbons (Customer)', 'Q-end financial reports now take 15+ minutes to generate; used to take under 2 minutes.', '2026-06-25 13:00:00+00'),
(6, 'Support (Sam Rivera)', 'Confirmed regression; likely tied to a recent increase in the customer''s transaction volume outpacing report query indexing. Investigating with engineering.', '2026-06-26 09:00:00+00');

-- Issue 7: Initech password reset delay (closed)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(7, 'Peter Gibbons (Customer)', 'Password reset emails are arriving 20-30 minutes late.', '2026-05-05 11:20:00+00'),
(7, 'Support (Priya Nair)', 'Identified a backlog in the transactional email queue caused by a provider-side rate limit. Increased throughput allocation and cleared the backlog; monitoring confirms emails now arrive within 1 minute.', '2026-05-06 10:00:00+00');

-- Issue 8: Umbrella compliance audit trail gaps (escalation-worthy, rich history)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(8, 'Alice Marlow (Customer)', 'Our internal compliance audit found gaps in the platform audit log for the month of March, ahead of an upcoming FDA-adjacent regulatory audit.', '2026-06-15 09:30:00+00'),
(8, 'Support (Priya Nair)', 'Confirmed the logging service dropped a subset of audit events during a deployment window on March 18. Beginning recovery from backup logs.', '2026-06-18 10:00:00+00'),
(8, 'Engineering (Jordan Lee)', 'Recovered approximately 80% of the missing entries from backups. Remaining entries appear to have been generated during a brief window where backup capture itself was also affected.', '2026-06-20 16:00:00+00'),
(8, 'Support (Priya Nair)', 'Customer needs written confirmation of full recovery status before their audit date; awaiting engineering''s final assessment on the remaining 20%.', '2026-06-22 14:00:00+00');

-- Issue 9: Umbrella Safari rendering (closed)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(9, 'Alice Marlow (Customer)', 'Dashboard charts render incorrectly on Safari 17 - legend overlaps the chart area.', '2026-04-20 08:00:00+00'),
(9, 'Engineering (Morgan Ellis)', 'Fixed a CSS grid fallback that only affected Safari''s older grid implementation. Deployed and confirmed with customer on Safari 17.', '2026-04-25 12:00:00+00');

-- Issue 10: Umbrella additional seats request
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(10, 'Alice Marlow (Customer)', 'Requesting 15 additional user seats under our current Enterprise agreement ahead of a team expansion.', '2026-06-28 16:00:00+00');

-- Issue 11: Wayne API rate limiting
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(11, 'Lucius Fox (Customer)', 'Our integration is being rate-limited during legitimate traffic bursts, causing dropped webhook deliveries.', '2026-06-05 10:00:00+00'),
(11, 'Support (Sam Rivera)', 'Reviewed rate limit configuration; current burst allowance appears too conservative for this customer''s traffic pattern. Recommending a limit increase, pending engineering sign-off.', '2026-06-08 11:30:00+00');

-- Issue 12: Wayne onboarding training (closed)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(12, 'Lucius Fox (Customer)', 'Requested a training session for 4 new support team members joining next month.', '2026-05-01 09:00:00+00'),
(12, 'Customer Success (Morgan Ellis)', 'Delivered a 90-minute onboarding training session covering ticketing workflows and escalation paths. Customer confirmed the session met their needs.', '2026-05-10 15:00:00+00');

-- Issue 13: Wayne production outage (escalation-worthy, rich history)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(13, 'Lucius Fox (Customer)', 'Dashboard is completely down for all our users as of 09:14 UTC. This is business-critical for us right now.', '2026-06-30 09:14:00+00'),
(13, 'Support (Sam Rivera)', 'On-call engineer paged immediately; incident declared SEV1.', '2026-06-30 09:20:00+00'),
(13, 'Engineering (Jordan Lee)', 'Root cause identified: database connection pool exhaustion following an unexpected traffic spike from a third-party integration partner.', '2026-06-30 09:50:00+00'),
(13, 'Engineering (Jordan Lee)', 'Mitigation applied: connection pool size increased and affected service instances restarted.', '2026-06-30 10:15:00+00'),
(13, 'Support (Sam Rivera)', 'Dashboard access restored for the majority of users as of 10:02 UTC. Monitoring for residual errors.', '2026-06-30 10:20:00+00'),
(13, 'Lucius Fox (Customer)', 'Confirmed dashboard is back up on our end. We will need a full RCA document and details on preventive measures given this is the second outage this quarter.', '2026-06-30 11:45:00+00');

-- Issue 14: Stark security review (closed)
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(14, 'Pepper Potts (Customer)', 'Requesting Acme''s cooperation with our annual third-party security review, per contract terms.', '2026-04-01 09:00:00+00'),
(14, 'Security (Taylor Brooks)', 'Completed all requested documentation and access for the third-party reviewer. Review concluded with no critical findings; two low-severity recommendations accepted and scheduled.', '2026-04-18 17:00:00+00');

-- Issue 15: Stark custom integration auth failure
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(15, 'Pepper Potts (Customer)', 'Our custom-built integration has been failing authentication since the June 28 platform release.', '2026-07-01 08:20:00+00'),
(15, 'Support (Priya Nair)', 'Confirmed the June release tightened token expiry validation; customer''s integration is using a deprecated long-lived token pattern. Working with customer''s engineering team on a migration path.', '2026-07-02 10:00:00+00');

-- Issue 16: Stark billing discrepancy
INSERT INTO issue_updates (issue_id, author, update_text, created_at) VALUES
(16, 'Pepper Potts (Customer)', 'Our usage logs show approximately 200 fewer API calls in June than we were billed for. Requesting reconciliation.', '2026-07-02 13:00:00+00');

-- =========================================================================
-- next_actions (a few historical, already-acted-on examples so the table
-- and its relationships are demonstrably populated; created_by = 'system_seed'
-- distinguishes these from actions the agent creates at runtime)
-- =========================================================================
INSERT INTO next_actions (issue_id, recommended_action, rationale, status, created_by, created_at) VALUES
(5, 'Escalate to finance engineering with compliance priority and provide customer a manual reconciliation workaround immediately.',
    'Discrepancy affects the customer''s financial close and carries compliance risk; a temporary workaround unblocks them while the permanent fix is developed.',
    'accepted', 'system_seed', '2026-06-14 09:05:00+00'),
(13, 'Publish a full RCA to the customer within 3 business days and propose connection-pool auto-scaling as a preventive measure.',
    'Second SEV1 outage this quarter for an Enterprise account; customer explicitly requested RCA and preventive measures.',
    'proposed', 'system_seed', '2026-06-30 12:00:00+00');

-- =========================================================================
-- users (local mirror of the Keycloak identities created in Step 3)
-- =========================================================================
INSERT INTO users (username, email, full_name, role) VALUES
('sales_user',   'sam.rivera@acmeops.example',  'Sam Rivera',   'sales_user'),
('support_user', 'priya.nair@acmeops.example',  'Priya Nair',   'support_user'),
('admin',        'alex.kim@acmeops.example',    'Alex Kim',     'admin');
