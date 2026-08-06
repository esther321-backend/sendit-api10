# SendIt Document Management & Enrichment API - Lab 9

A document management system built with FastAPI, PostgreSQL, SQLModel, file uploading, and external API integration (Open-Meteo Weather API).

---

## 📋 Exercise Questions & Answers

### Exercise 1: Document Search with Filters
1. **How would you make this search efficient with a large number of documents?**
   - Add database indexes on frequently queried columns (`city`, `status`, `uploaded_at`, `uploader_id`).
   - Implement pagination (e.g., `limit` and `offset`) so the API returns records in manageable pages rather than loading thousands of rows at once.

2. **Should managers see all documents while staff see only their own?**
   - Yes. Security and access control mandate that staff members can only search and filter within their own uploaded documents (`uploader_id == current_user.id`), whereas managers and admins have full visibility over all documents in the system.

---

### Exercise 2: Document Versioning
1. **How would you track changes between versions?**
   - Include a `version` field in the `Document` model and maintain a parent-child relationship via a `parent_id` foreign key referencing the original document ID.
2. **Should you store the old version or delete it?**
   - Old versions should be stored rather than deleted to maintain a complete audit trail and allow rollback in case of accidental overwrites or legal compliance auditing.

---

### Exercise 3: Webhook Notification
1. **How would you handle retries if the webhook fails?**
   - Use a background task or worker queue (such as Celery/Redis or FastAPI `BackgroundTasks`) with an exponential backoff retry policy (e.g., retrying after 5s, 15s, 1 minute, etc., up to 3-5 max attempts).

2. **What security measures would you put in place?**
   - Require HTTPS endpoints for webhooks.
   - Sign webhook payloads using an HMAC SHA-256 signature generated with a shared secret key so receivers can verify request authenticity.
   - Restrict webhook registration endpoints strictly to system administrators.
