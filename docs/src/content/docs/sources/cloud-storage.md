---
title: Cloud Storage Sources
description: Sync files incrementally from S3, GCS, Azure Blob Storage, and SFTP.
---

Cloud storage sources use dlt's filesystem connector to sync files incrementally. Unlike [file sources](/sources/files/) which read at query time, these copy data locally and support incremental loading.

## Amazon S3

```bash
dinobase add s3 --bucket-url s3://my-bucket/data/ --access-key AKIA... --secret-key ...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--bucket-url` | `S3_BUCKET_URL` | S3 URL (`s3://bucket/prefix/`) |
| `--access-key` | `AWS_ACCESS_KEY_ID` | AWS access key ID |
| `--secret-key` | `AWS_SECRET_ACCESS_KEY` | AWS secret key |

## Google Cloud Storage

```bash
dinobase add gcs --bucket-url gs://my-bucket/data/ --credentials-file ./sa.json
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--bucket-url` | `GCS_BUCKET_URL` | GCS URL (`gs://bucket/prefix/`) |
| `--credentials-file` | `GOOGLE_APPLICATION_CREDENTIALS` | Service account JSON path |

## Azure Blob Storage

```bash
dinobase add azure --container-url az://mycontainer/ --account-name myaccount --account-key ...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--container-url` | `AZURE_STORAGE_URL` | Azure URL (`az://container/`) |
| `--account-name` | `AZURE_STORAGE_ACCOUNT_NAME` | Storage account name |
| `--account-key` | `AZURE_STORAGE_ACCOUNT_KEY` | Storage account key |

## SFTP

```bash
dinobase add sftp --url sftp://host/path/ --username user --password ...
```

| Option | Env var | Description |
|--------|---------|-------------|
| `--url` | `SFTP_URL` | SFTP URL (`sftp://host/path/`) |
| `--username` | `SFTP_USERNAME` | Username |
| `--password` | `SFTP_PASSWORD` | Password |

## Syncing

Cloud storage sources require syncing:

```bash
dinobase sync          # sync all
dinobase sync s3       # sync just S3
```

dlt handles incremental loading -- only new or changed files are downloaded on subsequent syncs.

## When to use cloud storage vs file sources

Use **cloud storage sources** when:

- Files are added incrementally (new files appear over time)
- You want data cached locally for faster queries
- You need sync scheduling

Use **file sources** (`dinobase add parquet --path s3://...`) when:

- You want zero-copy reads (data stays in cloud)
- Files don't change often
- You want instant setup with no sync step
