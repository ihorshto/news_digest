# NewsDigest MVP — Plan

- [x] 1. Repository skeleton, docker-compose, healthchecks, empty services that start
- [x] 2. Backend: models, migrations, auth + tests
- [x] 3. Frontend: design system, login/register, protected routes
- [x] 4. Topics CRUD + LLM topic expansion + tests
- [x] 5. News collectors (Google News RSS, Tavily) with fixture-based tests
- [x] 6. Embeddings, relevance filter, clustering + tests
- [ ] 7. Digest generation + delivery + fakes
- [ ] 8. Scheduling (arq cron), idempotency, timezones + `next_run_at` tests
- [ ] 9. Telegram bot and account linking
- [ ] 10. Remaining frontend pages, history, settings, dark theme
- [ ] 11. E2E smoke test `scripts/smoke_test.sh`
- [ ] 12. README.md
