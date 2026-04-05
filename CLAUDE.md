# Dinobase Development Guidelines

## Environment Variables

Whenever you add, remove, or rename an environment variable in a service, update the relevant example file:
- API (`ee/cloud/api/`): update `ee/cloud/api/.env.example`
- Web frontend (`ee/cloud/web/`): update `ee/cloud/web/.env.local.example`

## Documentation

Whenever you add or change a user-facing feature, update the relevant page(s) under `ee/website/src/content/docs/`. If no existing page covers the feature, create one in the appropriate subdirectory (guides/, reference/, sources/, integrations/).
