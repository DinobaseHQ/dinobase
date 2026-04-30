# Dinobase Development Guidelines

## Environment Variables

Whenever you add, remove, or rename an environment variable in a service, update the relevant example file:
- API (`ee/cloud/api/`): update `ee/cloud/api/.env.example`
- Web frontend (`ee/cloud/web/`): update `ee/cloud/web/.env.local.example`

## Documentation

User-facing docs and the marketing site live in a separate repo: `git@github.com:DinobaseHQ/dinobase-website.git`. When you add or change a user-facing feature here, flag the docs update needed there in your PR description — don't try to land it in this repo.
