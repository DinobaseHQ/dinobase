# Dinobase OpenClaw Skill

OpenClaw skill that teaches agents to query business data across 100+ sources using Dinobase.

## For users

### Install from ClawHub

```bash
openclaw skills install dinobase
```

OpenClaw will auto-install Dinobase via `uv` if it's not already on your system.

### Manual install

```bash
# Install Dinobase
pip install dinobase
# or: uv pip install dinobase

# Copy the skill
mkdir -p ~/.openclaw/skills/dinobase
cp SKILL.md ~/.openclaw/skills/dinobase/SKILL.md
```

### Setup

Once installed, tell your OpenClaw agent to set up Dinobase:

> "Set up Dinobase with my Stripe account. My API key is sk_test_..."

Or run the commands directly:

```bash
dinobase init
dinobase add stripe --api-key sk_test_...
dinobase sync
```

Then ask cross-source questions naturally:

> "Which customers have overdue invoices but no recent support tickets?"

## For maintainers

### Publishing to ClawHub

```bash
npm install -g clawhub
clawhub login
cd integrations/openclaw
clawhub publish . --slug dinobase --name "Dinobase" --version 0.1.0
```

### Updating

1. Edit `SKILL.md`
2. Bump the `version` in frontmatter
3. `clawhub publish . --version <new-version>`
