# =============================================================================
# STORY FORGE ON GCP - INFRASTRUCTURE AS CODE
# =============================================================================
#
# A cost-optimized deployment of Story Forge on Google Cloud Platform using:
# - Cloud Run (serverless, scale-to-zero)
# - Cloud Storage (SQLite database storage, ~$0.05/month)
# - Secret Manager (secure credential storage)
# - No VPC, No Cloud SQL (cost savings)
#
# Story Forge is Ted's self-publishing dashboard, running locally on Mac Mini
# but deployable to Cloud Run for remote access.
#
# =============================================================================

terraform {
  required_version = ">= 1.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.1"
    }
  }

  backend "gcs" {
    bucket = "gcp-apps-web-minis-terraform-state"
    prefix = "gcp-apps/story-forge"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# =============================================================================
# GCP APIs
# =============================================================================

resource "google_project_service" "cloudresourcemanager" {
  project = var.project_id
  service = "cloudresourcemanager.googleapis.com"

  disable_dependent_services = false
}

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "serviceusage.googleapis.com",
    "storage.googleapis.com",
  ])

  project = var.project_id
  service = each.value

  disable_dependent_services = false
  disable_on_destroy         = false

  depends_on = [google_project_service.cloudresourcemanager]
}

# =============================================================================
# Service Account
# =============================================================================

# Reference existing Service Account for Web Minis Cloud Run (created via cloudshell)
# Shared across all apps in this project
data "google_service_account" "app_runner" {
  account_id = "web-minis-runner"
  depends_on = [google_project_service.apis, google_project_service.cloudresourcemanager]
}

# IAM bindings for the service account
resource "google_project_iam_member" "app_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${data.google_service_account.app_runner.email}"
}

resource "google_project_iam_member" "app_storage_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${data.google_service_account.app_runner.email}"
}

# =============================================================================
# Cloud Storage Bucket for Database Backups
# =============================================================================

resource "google_storage_bucket" "story_forge_backups" {
  count  = var.db_backup_bucket != "" ? 0 : 1
  name   = "${var.project_id}-story-forge-backups"
  location = var.region

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}

data "google_storage_bucket" "story_forge_backups" {
  count  = var.db_backup_bucket != "" ? 1 : 0
  name   = var.db_backup_bucket
}

# =============================================================================
# Cloud Run Service
# =============================================================================

resource "google_cloud_run_v2_service" "story_forge" {
  name     = "story-forge"
  location = var.region

  template {
    service_account = data.google_service_account.app_runner.email

    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }

    containers {
      image = var.story_forge_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        startup_cpu_boost = true
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get {
          path = "/"
          port = 8080
        }
        initial_delay_seconds = 10
        timeout_seconds       = 5
        period_seconds        = 10
        failure_threshold     = 10
      }

      liveness_probe {
        http_get {
          path = "/"
          port = 8080
        }
        initial_delay_seconds = 30
        timeout_seconds       = 5
        period_seconds        = 30
        failure_threshold     = 3
      }

      # Environment variables from Secret Manager
      env {
        name = "GOOGLE_CLIENT_ID"
        value_source {
          secret_key_ref {
            secret  = "story-forge-google-client-id"
            version = "latest"
          }
        }
      }

      env {
        name = "GOOGLE_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = "story-forge-google-client-secret"
            version = "latest"
          }
        }
      }

      env {
        name = "MINIMAX_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "story-forge-minimax-api-key"
            version = "latest"
          }
        }
      }

      env {
        name = "ELEVENLABS_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "story-forge-elevenlabs-api-key"
            version = "latest"
          }
        }
      }

      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
    }
  }

  traffic {
    percent = 100
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
  }

  depends_on = [
    google_project_service.apis
  ]
}

# =============================================================================
# Public Access
# =============================================================================

resource "google_cloud_run_v2_service_iam_member" "public_access" {
  name     = google_cloud_run_v2_service.story_forge.name
  location = google_cloud_run_v2_service.story_forge.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# =============================================================================
# Deployment Documentation
# =============================================================================

resource "local_file" "deployment_docs" {
  filename = "${path.module}/STORY_FORGE_DEPLOYMENT.md"
  content = <<-EOT
# Story Forge Deployment Guide

## 📚 Service Overview
Story Forge is Ted's self-publishing dashboard for managing books, chapters, and TTS narration.

## 🌐 Service URL
${google_cloud_run_v2_service.story_forge.uri}

## 🔒 Security Configuration
- **Network**: Public access for Ted's use
- **Secrets**: All sensitive data stored in Google Secret Manager
- **Authentication**: Google OAuth for single-user access

## 🎯 Application Features
- Book and chapter management
- Google OAuth authentication
- MiniMax TTS integration
- ElevenLabs TTS integration
- Local SQLite database with encrypted backups

## 💰 Estimated Monthly Costs
| Component | Cost | Description |
|-----------|------|-------------|
| **Cloud Run** | ~$1-3/month | Scale-to-zero serverless compute |
| **Storage** | ~$0.05/month | SQLite backup bucket |
| **Networking** | ~$1/month | Ingress/egress traffic |
| **Secrets** | ~$0.03/month | Secret Manager |
| **Total** | **~$2-4/month** | |

## 🚀 Deployment Commands
```bash
# Plan infrastructure changes
terraform plan

# Apply infrastructure
terraform apply

# Build and push Docker image
gcloud builds submit --tag gcr.io/PROJECT_ID/story-forge:latest

# Deploy to Cloud Run
gcloud run deploy story-forge --image gcr.io/PROJECT_ID/story-forge:latest
```

## 🔍 Monitoring
- Cloud Run Metrics: Request latency, instance count, memory usage
- Application Logs: Via Google Cloud Logging
- Backup verification: Check GCS bucket for encrypted backups

## 🛠️ Required Secrets
Create these secrets in Secret Manager before deployment:
- story-forge-google-client-id
- story-forge-google-client-secret
- story-forge-minimax-api-key
- story-forge-elevenlabs-api-key

## 📊 Backup Strategy
- Local backups stored in ./data/backups/ (Mac Mini)
- Cloud backups to GCS bucket (when deployed)
- Encrypted with Fernet (cryptography)
- Retention: 10 backups max, 30 days max age
EOT
}
