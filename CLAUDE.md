# Dinobase Development Guidelines

## Environment Variables

Whenever you add, remove, or rename an environment variable in any service (API, proxy, web frontend), update `ee/cloud/.env.example` to reflect the change.

## Documentation

Whenever you add or change a user-facing feature, update the relevant page(s) under `ee/website/src/content/docs/`. If no existing page covers the feature, create one in the appropriate subdirectory (guides/, reference/, sources/, integrations/).
