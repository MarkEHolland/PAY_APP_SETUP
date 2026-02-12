# Question Bank Reference

Detailed question templates organized by domain. Use these as a starting point — adapt wording to match the specific project context from the bootstrap.md.

## Technology Stack

- What programming language(s) and version(s) should be used? Why?
- Which web framework (if applicable)? Any constraints on version?
- What database engine — relational (PostgreSQL, MySQL, SQLite), NoSQL (MongoDB, DynamoDB), or both?
- Are there required libraries or SDKs (e.g., for payment processing, mapping, ML)?
- What package manager should be used (npm, yarn, pnpm, pip, cargo, etc.)?
- Should the project use TypeScript or plain JavaScript? (for JS projects)
- Are there any language or framework constraints imposed by the team or hosting environment?

## Architecture

- Monolith or microservices? If microservices, how many services initially?
- Is this a single-page app (SPA), server-rendered (SSR), static site (SSG), or hybrid?
- Should the frontend and backend live in the same repo (monorepo) or separate?
- What is the API style — REST, GraphQL, gRPC, or tRPC?
- How does data flow between components? Any event-driven patterns (pub/sub, message queues)?
- Is there a need for real-time features (WebSockets, SSE)?
- Will there be a mobile app? If so, native, React Native, Flutter, or responsive web?

## Security

- How do users authenticate — email/password, OAuth/SSO, magic links, API keys?
- What authorization model — role-based (RBAC), attribute-based (ABAC), simple admin/user?
- Should passwords be hashed? (always yes — but confirm algorithm: bcrypt, argon2, scrypt)
- Is there sensitive/PII data that needs encryption at rest?
- How should API keys and secrets be managed — environment variables, vault, cloud secrets manager?
- Are there CORS requirements? What origins should be allowed?
- Should there be rate limiting on authentication endpoints?
- Is HTTPS required in all environments? (yes for production — clarify for dev)
- Any specific security headers required (CSP, HSTS, etc.)?
- Will there be audit logging for sensitive operations?

## Deployment

- Where will this be hosted — AWS, GCP, Azure, Vercel, Railway, Fly.io, self-hosted?
- How many environments — local, dev, staging, production?
- Should the app be containerized with Docker?
- What CI/CD tool — GitHub Actions, GitLab CI, CircleCI, Jenkins?
- What triggers a deployment — push to main, manual approval, tag-based?
- Is infrastructure-as-code needed (Terraform, Pulumi, CDK)?
- Is there a custom domain? Who manages DNS?
- Any requirements around blue-green or canary deployments?
- What's the rollback strategy?

## Testing

- What test runner / framework — Jest, Vitest, pytest, Go test, etc.?
- What's the target code coverage percentage (if any)?
- Which critical user flows need end-to-end tests?
- Should there be integration tests against a real database or mocked?
- Is there a preference for TDD or test-after?
- Should there be snapshot tests for UI components?
- Any performance testing requirements (load tests, benchmarks)?
- E2E framework preference — Playwright, Cypress, Selenium?
- Should tests run in CI? Blocking or non-blocking?

## Data

- What data needs to be stored? Rough schema or entity list?
- What ORM or query builder (if any) — Prisma, Drizzle, SQLAlchemy, TypeORM?
- How should schema migrations be managed — ORM migrations, raw SQL, tool like Flyway?
- Is seed data needed for development? What does it look like?
- Are there external data sources to ingest (APIs, CSV imports, webhooks)?
- What's the backup strategy and frequency?
- Is there a data retention policy or data deletion requirement?
- Any multi-tenancy requirements?

## Integrations

- What third-party services will the project use (list each)?
- For each: what's the auth method (API key, OAuth, webhook secret)?
- Are there webhook endpoints to receive? What events?
- Any email service needed (SendGrid, SES, Resend, Postmark)?
- Payment processing (Stripe, PayPal, etc.)?
- File storage (S3, Cloudflare R2, local filesystem)?
- Search (Elasticsearch, Algolia, Meilisearch, built-in)?
- Any AI/ML services (OpenAI, Anthropic, Hugging Face)?

## Scalability & Performance

- How many concurrent users are expected at launch? At peak?
- What's the expected data volume (rows, documents, file storage)?
- Is caching needed? What layer — CDN, application-level (Redis), database query cache?
- Should there be a background job queue (BullMQ, Celery, Sidekiq)?
- Any heavy computation that should be async?
- Are there specific latency targets (e.g., API responses under 200ms)?
- Is auto-scaling needed?

## Observability

- What logging framework — structured JSON logs, or plain text?
- Where do logs go — stdout, file, centralized service (Datadog, Grafana, CloudWatch)?
- Should there be application performance monitoring (APM)?
- Error tracking service — Sentry, Bugsnag, Rollbar, or built-in?
- What key metrics should be tracked (response times, error rates, queue depth)?
- Should there be health check endpoints?
- Any alerting requirements — what conditions trigger alerts?

## Developer Experience

- How should a new developer set up the project locally? Docker Compose, manual, or devcontainer?
- Code style enforcement — ESLint, Prettier, Ruff, Black, gofmt?
- Git workflow — trunk-based, GitFlow, feature branches + PRs?
- Commit message convention — Conventional Commits, free-form?
- Should there be pre-commit hooks (Husky, pre-commit)?
- Is there an existing monorepo tool (Turborepo, Nx, Lerna)?
- Documentation approach — README, inline JSDoc/docstrings, separate docs site, ADRs?

## Compliance & Constraints

- What browser versions must be supported?
- Accessibility standard — WCAG 2.1 AA, Section 508, none?
- Is internationalization (i18n) needed? Which languages?
- Any regulatory requirements — GDPR, HIPAA, SOC 2, PCI DSS?
- Project license — MIT, Apache 2.0, proprietary?
- Are there dependency license restrictions (no GPL, etc.)?
- Any corporate or team coding standards to follow?
- Minimum device/screen sizes to support?
