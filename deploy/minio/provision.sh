#!/bin/sh
set -eu

for name in MINIO_ROOT_USER MINIO_ROOT_PASSWORD APP_OBJECT_STORAGE_ACCESS_KEY \
  APP_OBJECT_STORAGE_SECRET_KEY OBJECT_STORAGE_BUCKET GOVERNANCE_DELETE_ACCESS_KEY \
  GOVERNANCE_DELETE_SECRET_KEY GOVERNANCE_RESUME_BUCKET GOVERNANCE_RESUME_PREFIX \
  GOVERNANCE_EXPORT_BUCKET GOVERNANCE_EXPORT_PREFIX GOVERNANCE_LEDGER_ACCESS_KEY \
  GOVERNANCE_LEDGER_SECRET_KEY GOVERNANCE_LEDGER_BUCKET GOVERNANCE_LEDGER_PREFIX
do
  eval "value=\${$name:-}"
  if [ -z "$value" ]; then
    echo "$name is required" >&2
    exit 1
  fi
done

if [ "$MINIO_ROOT_USER" = "$APP_OBJECT_STORAGE_ACCESS_KEY" ] ||
   [ "$MINIO_ROOT_USER" = "$GOVERNANCE_DELETE_ACCESS_KEY" ] ||
   [ "$MINIO_ROOT_USER" = "$GOVERNANCE_LEDGER_ACCESS_KEY" ] ||
   [ "$APP_OBJECT_STORAGE_ACCESS_KEY" = "$GOVERNANCE_DELETE_ACCESS_KEY" ] ||
   [ "$APP_OBJECT_STORAGE_ACCESS_KEY" = "$GOVERNANCE_LEDGER_ACCESS_KEY" ] ||
   [ "$GOVERNANCE_DELETE_ACCESS_KEY" = "$GOVERNANCE_LEDGER_ACCESS_KEY" ]; then
  echo "MinIO access keys must be pairwise distinct" >&2
  exit 1
fi
if [ "$MINIO_ROOT_PASSWORD" = "$APP_OBJECT_STORAGE_SECRET_KEY" ] ||
   [ "$MINIO_ROOT_PASSWORD" = "$GOVERNANCE_DELETE_SECRET_KEY" ] ||
   [ "$MINIO_ROOT_PASSWORD" = "$GOVERNANCE_LEDGER_SECRET_KEY" ] ||
   [ "$APP_OBJECT_STORAGE_SECRET_KEY" = "$GOVERNANCE_DELETE_SECRET_KEY" ] ||
   [ "$APP_OBJECT_STORAGE_SECRET_KEY" = "$GOVERNANCE_LEDGER_SECRET_KEY" ] ||
   [ "$GOVERNANCE_DELETE_SECRET_KEY" = "$GOVERNANCE_LEDGER_SECRET_KEY" ]; then
  echo "MinIO secret keys must be pairwise distinct" >&2
  exit 1
fi
if { [ -n "${PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY:-}" ] &&
     [ "$PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY" != "$GOVERNANCE_DELETE_ACCESS_KEY" ] &&
     { [ "$PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY" = "$MINIO_ROOT_USER" ] ||
       [ "$PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY" = "$APP_OBJECT_STORAGE_ACCESS_KEY" ] ||
       [ "$PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY" = "$GOVERNANCE_LEDGER_ACCESS_KEY" ]; }; } ||
   { [ -n "${PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY:-}" ] &&
     [ "$PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY" != "$GOVERNANCE_LEDGER_ACCESS_KEY" ] &&
     { [ "$PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY" = "$MINIO_ROOT_USER" ] ||
       [ "$PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY" = "$APP_OBJECT_STORAGE_ACCESS_KEY" ] ||
       [ "$PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY" = "$GOVERNANCE_DELETE_ACCESS_KEY" ]; }; }; then
  echo "retired MinIO access key conflicts with an active identity" >&2
  exit 1
fi

for bucket in "$OBJECT_STORAGE_BUCKET" "$GOVERNANCE_RESUME_BUCKET" \
  "$GOVERNANCE_EXPORT_BUCKET" "$GOVERNANCE_LEDGER_BUCKET"
do
  case "$bucket" in
    *[!A-Za-z0-9.-]*) echo "invalid bucket name" >&2; exit 1 ;;
  esac
done
for prefix in "$GOVERNANCE_RESUME_PREFIX" "$GOVERNANCE_EXPORT_PREFIX" \
  "$GOVERNANCE_LEDGER_PREFIX"
do
  case "$prefix" in
    *[!A-Za-z0-9_./-]*) echo "invalid object prefix" >&2; exit 1 ;;
  esac
done

mc alias set local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
mc mb --ignore-existing "local/$OBJECT_STORAGE_BUCKET"
mc mb --ignore-existing "local/$GOVERNANCE_RESUME_BUCKET"
mc mb --ignore-existing "local/$GOVERNANCE_EXPORT_BUCKET"
mc mb --ignore-existing "local/$GOVERNANCE_LEDGER_BUCKET"

printf '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:ListBucket","s3:GetBucketLocation"],"Resource":["arn:aws:s3:::%s"]},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject"],"Resource":["arn:aws:s3:::%s/*"]}]}' \
  "$OBJECT_STORAGE_BUCKET" "$OBJECT_STORAGE_BUCKET" >/tmp/app-policy.json
printf '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetBucketLocation"],"Resource":["arn:aws:s3:::%s","arn:aws:s3:::%s"]},{"Effect":"Allow","Action":["s3:ListBucket"],"Resource":["arn:aws:s3:::%s","arn:aws:s3:::%s"],"Condition":{"StringLike":{"s3:prefix":["%s*","%s*"]}}},{"Effect":"Allow","Action":["s3:DeleteObject"],"Resource":["arn:aws:s3:::%s/%s*","arn:aws:s3:::%s/%s*"]}]}' \
  "$GOVERNANCE_RESUME_BUCKET" "$GOVERNANCE_EXPORT_BUCKET" \
  "$GOVERNANCE_RESUME_BUCKET" "$GOVERNANCE_EXPORT_BUCKET" \
  "$GOVERNANCE_RESUME_PREFIX" "$GOVERNANCE_EXPORT_PREFIX" \
  "$GOVERNANCE_RESUME_BUCKET" "$GOVERNANCE_RESUME_PREFIX" \
  "$GOVERNANCE_EXPORT_BUCKET" "$GOVERNANCE_EXPORT_PREFIX" >/tmp/delete-policy.json
printf '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:GetBucketLocation"],"Resource":["arn:aws:s3:::%s"]},{"Effect":"Allow","Action":["s3:ListBucket"],"Resource":["arn:aws:s3:::%s"],"Condition":{"StringLike":{"s3:prefix":["%s*"]}}},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject"],"Resource":["arn:aws:s3:::%s/%s*"]}]}' \
  "$GOVERNANCE_LEDGER_BUCKET" \
  "$GOVERNANCE_LEDGER_BUCKET" "$GOVERNANCE_LEDGER_PREFIX" \
  "$GOVERNANCE_LEDGER_BUCKET" "$GOVERNANCE_LEDGER_PREFIX" >/tmp/ledger-policy.json

mc admin user add local "$APP_OBJECT_STORAGE_ACCESS_KEY" "$APP_OBJECT_STORAGE_SECRET_KEY"
mc admin user add local "$GOVERNANCE_DELETE_ACCESS_KEY" "$GOVERNANCE_DELETE_SECRET_KEY"
mc admin user add local "$GOVERNANCE_LEDGER_ACCESS_KEY" "$GOVERNANCE_LEDGER_SECRET_KEY"
mc admin policy create local ux09-app /tmp/app-policy.json
mc admin policy create local ux09-governance-delete /tmp/delete-policy.json
mc admin policy create local ux09-governance-ledger /tmp/ledger-policy.json
mc admin policy attach local ux09-app --user "$APP_OBJECT_STORAGE_ACCESS_KEY"
mc admin policy attach local ux09-governance-delete --user "$GOVERNANCE_DELETE_ACCESS_KEY"
mc admin policy attach local ux09-governance-ledger --user "$GOVERNANCE_LEDGER_ACCESS_KEY"

if [ -n "${PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY:-}" ] &&
   [ "$PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY" != "$GOVERNANCE_DELETE_ACCESS_KEY" ]; then
  if mc admin user info local "$PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY" >/dev/null 2>&1; then
    mc admin user remove local "$PREVIOUS_GOVERNANCE_DELETE_ACCESS_KEY"
  fi
fi
if [ -n "${PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY:-}" ] &&
   [ "$PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY" != "$GOVERNANCE_LEDGER_ACCESS_KEY" ]; then
  if mc admin user info local "$PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY" >/dev/null 2>&1; then
    mc admin user remove local "$PREVIOUS_GOVERNANCE_LEDGER_ACCESS_KEY"
  fi
fi
